#include "sentinel/protocol.hpp"

#include <zmq.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <string>
#include <unistd.h>
#include <vector>

static std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
}

int main(int argc, char** argv) {
  const int n = argc > 1 ? std::stoi(argv[1]) : 100000;
  const std::string endpoint =
      "ipc:///tmp/sentinel_zmq_" + std::to_string(getpid());

  void* ctx = zmq_ctx_new();
  void* pull = zmq_socket(ctx, ZMQ_PULL);
  void* push = zmq_socket(ctx, ZMQ_PUSH);
  if (!ctx || !pull || !push) return 2;

  const int hwm = n;
  zmq_setsockopt(pull, ZMQ_RCVHWM, &hwm, sizeof(hwm));
  zmq_setsockopt(push, ZMQ_SNDHWM, &hwm, sizeof(hwm));
  if (zmq_bind(pull, endpoint.c_str()) != 0) return 3;
  if (zmq_connect(push, endpoint.c_str()) != 0) return 4;

  sentinel::ReportMessage warm{};
  for (int i = 0; i < 1000; ++i) {
    warm.type = sentinel::MessageType::kReport;
    warm.recv_ts_ns = now_ns();
    zmq_send(push, &warm, sizeof(warm), 0);
    zmq_recv(pull, &warm, sizeof(warm), 0);
  }

  std::vector<double> us;
  us.reserve(n);
  for (int i = 0; i < n; ++i) {
    sentinel::ReportMessage msg{};
    msg.type = sentinel::MessageType::kReport;
    msg.recv_ts_ns = now_ns();
    zmq_send(push, &msg, sizeof(msg), 0);
    sentinel::ReportMessage out{};
    zmq_recv(pull, &out, sizeof(out), 0);
    const auto end = now_ns();
    us.push_back(static_cast<double>(end - msg.recv_ts_ns) / 1e3);
  }

  std::sort(us.begin(), us.end());
  const auto pct = [&](double p) {
    return us[static_cast<std::size_t>(p * (us.size() - 1))];
  };
  std::cout << "samples=" << n
            << " median_us=" << pct(.50)
            << " p99_us=" << pct(.99)
            << " p99_9_us=" << pct(.999) << '\n';

  zmq_close(push);
  zmq_close(pull);
  zmq_ctx_term(ctx);
  std::remove(endpoint.c_str());
}
