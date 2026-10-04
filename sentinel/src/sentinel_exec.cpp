#include "sentinel/execution_engine.hpp"
#include "sentinel/protocol.hpp"
#include "sentinel/runtime_profile.hpp"
#include <rigtorp/SPSCQueue.h>
#include <zmq.h>

#include <atomic>
#include <cstddef>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

namespace {
struct Command {
  sentinel::MessageType type{sentinel::MessageType::kShutdown};
  sentinel::TickMessage tick{};
  sentinel::OrderMessage order{};
};
struct Telemetry {
  sentinel::MessageType type{sentinel::MessageType::kTick};
  sentinel::TickMessage tick{};
  sentinel::ReportMessage report{};
};
void print_stats(const sentinel::EngineState& s) {
  std::cerr << "ticks=" << s.ticks << " orders=" << s.orders
            << " fills=" << s.fills << " stale_rejects=" << s.stale_rejects
            << " invalid_ticks=" << s.invalid_ticks
            << " stop_events=" << s.stop_events << "\n";
}
}

int main(int argc, char** argv) {
  const std::string endpoint = (argc > 1 && argv[1][0] != '-') ? argv[1] : "ipc:///tmp/sentinel_exec_in.ipc";
  sentinel::RuntimeProfile runtime{};
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--cpu" && i + 1 < argc) runtime.cpu = std::stoi(argv[++i]);
    else if (arg == "--mlock") runtime.lock_memory = true;
    else if (arg == "--fifo" && i + 1 < argc) { runtime.realtime = true; runtime.fifo_priority = std::stoi(argv[++i]); }
  }
  void* ctx = zmq_ctx_new();
  void* pull = zmq_socket(ctx, ZMQ_PULL);
  void* push = zmq_socket(ctx, ZMQ_PUSH);
  void* telemetry_pub = zmq_socket(ctx, ZMQ_PUB);
  if (!ctx || !pull || !push || !telemetry_pub) return 2;
  if (zmq_bind(pull, endpoint.c_str()) != 0) {
    std::cerr << "bind failed: " << std::strerror(errno) << "\n";
    return 3;
  }
  const std::string out = endpoint + ".reports";
  if (zmq_bind(push, out.c_str()) != 0) {
    std::cerr << "report bind failed: " << std::strerror(errno) << "\n";
    return 4;
  }
  const std::string telemetry_endpoint = endpoint + ".telemetry";
  if (zmq_bind(telemetry_pub, telemetry_endpoint.c_str()) != 0) {
    std::cerr << "telemetry bind failed: " << std::strerror(errno) << "\n";
    return 5;
  }

  int hwm = 1000000;
  zmq_setsockopt(telemetry_pub, ZMQ_SNDHWM, &hwm, sizeof(hwm));

  rigtorp::SPSCQueue<Command> input_queue(4096);
  rigtorp::SPSCQueue<sentinel::ReportMessage> output_queue(4096);
  rigtorp::SPSCQueue<Telemetry> telemetry_queue(1 << 16);
  std::atomic<bool> running{true};
  std::atomic<std::uint64_t> telemetry_drops{0};
  sentinel::ExecutionEngine engine;

  std::thread execution_thread([&] {
    sentinel::apply_runtime_profile(runtime);
    while (running.load(std::memory_order_acquire) || !input_queue.empty()) {
      auto* command = input_queue.front();
      if (!command) { std::this_thread::yield(); continue; }
      if (command->type == sentinel::MessageType::kShutdown) {
        input_queue.pop();
        running.store(false, std::memory_order_release);
        break;
      }
      if (command->type == sentinel::MessageType::kTick) {
        engine.on_tick(command->tick);
        Telemetry telemetry{};
        telemetry.type = sentinel::MessageType::kTick;
        telemetry.tick = command->tick;
        if (!telemetry_queue.try_push(telemetry)) ++telemetry_drops;
        sentinel::ReportMessage report{};
        if (engine.check_oco(report)) {
          while (!output_queue.try_push(report)) std::this_thread::yield();
          Telemetry rt{};
          rt.type = sentinel::MessageType::kReport;
          rt.report = report;
          if (!telemetry_queue.try_push(rt)) ++telemetry_drops;
        }
      } else if (command->type == sentinel::MessageType::kOrder) {
        sentinel::ReportMessage report{};
        engine.on_order(command->order, report);
        while (!output_queue.try_push(report)) std::this_thread::yield();
        Telemetry rt{};
        rt.type = sentinel::MessageType::kReport;
        rt.report = report;
        if (!telemetry_queue.try_push(rt)) ++telemetry_drops;
      }
      input_queue.pop();
    }
  });

  alignas(64) std::byte buf[256];
  while (running.load(std::memory_order_acquire)) {
    while (auto* report = output_queue.front()) {
      zmq_send(push, report, sizeof(*report), 0);
      output_queue.pop();
    }
    while (auto* telemetry = telemetry_queue.front()) {
      const void* data = nullptr;
      std::size_t size = 0;
      if (telemetry->type == sentinel::MessageType::kTick) {
        data = &telemetry->tick; size = sizeof(telemetry->tick);
      } else {
        data = &telemetry->report; size = sizeof(telemetry->report);
      }
      if (zmq_send(telemetry_pub, data, size, ZMQ_DONTWAIT) < 0) {
        ++telemetry_drops;
      }
      telemetry_queue.pop();
    }
    zmq_pollitem_t item{pull, 0, ZMQ_POLLIN, 0};
    const int ready = zmq_poll(&item, 1, 1);
    if (ready <= 0) continue;
    const int n = zmq_recv(pull, buf, sizeof(buf), ZMQ_DONTWAIT);
    if (n < 1) continue;
    const auto type = static_cast<sentinel::MessageType>(
        static_cast<std::uint8_t>(buf[0]));
    Command command{}; command.type = type;
    if (type == sentinel::MessageType::kTick &&
        n == static_cast<int>(sizeof(sentinel::TickMessage))) {
      std::memcpy(&command.tick, buf, sizeof(command.tick));
    } else if (type == sentinel::MessageType::kOrder &&
               n == static_cast<int>(sizeof(sentinel::OrderMessage))) {
      std::memcpy(&command.order, buf, sizeof(command.order));
    } else if (type == sentinel::MessageType::kShutdown) {
      while (!input_queue.try_push(command)) std::this_thread::yield();
      break;
    } else {
      continue;
    }
    while (!input_queue.try_push(command)) std::this_thread::yield();
  }

  execution_thread.join();
  while (auto* report = output_queue.front()) {
    zmq_send(push, report, sizeof(*report), 0); output_queue.pop();
  }
  while (auto* telemetry = telemetry_queue.front()) {
    const void* data = (telemetry->type == sentinel::MessageType::kTick)
        ? static_cast<const void*>(&telemetry->tick)
        : static_cast<const void*>(&telemetry->report);
    const std::size_t size = (telemetry->type == sentinel::MessageType::kTick)
        ? sizeof(telemetry->tick) : sizeof(telemetry->report);
    zmq_send(telemetry_pub, data, size, 0);
    telemetry_queue.pop();
  }
  print_stats(engine.state());
  std::cerr << "telemetry_drops=" << telemetry_drops.load() << "\n";
  zmq_close(telemetry_pub);
  zmq_close(push);
  zmq_close(pull);
  zmq_ctx_term(ctx);
  return 0;
}