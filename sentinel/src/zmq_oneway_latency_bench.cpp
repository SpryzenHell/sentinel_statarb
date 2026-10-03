#include <zmq.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <iomanip>
#include <iostream>
#include <sched.h>
#include <string>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

struct Wire { std::uint64_t seq; std::uint64_t ts_ns; };
struct Result { double median_us; double p99_us; double p99_9_us; };

static std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
}

static void pin_cpu(int cpu) {
  if (cpu < 0) return;
  cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
  if (sched_setaffinity(0, sizeof(set), &set) != 0)
    std::cerr << "cpu_affinity_error=" << std::strerror(errno) << "\n";
}

static Result summarize(std::vector<double>& us) {
  std::sort(us.begin(), us.end());
  const auto pct = [&](double p) { return us[static_cast<std::size_t>(p * (us.size() - 1))]; };
  return {pct(.50), pct(.99), pct(.999)};
}

int main(int argc, char** argv) {
  const int n = argc > 1 ? std::stoi(argv[1]) : 200000;
  const int cpu_tx = argc > 2 ? std::stoi(argv[2]) : -1;
  const int cpu_rx = argc > 3 ? std::stoi(argv[3]) : -1;
  const std::string endpoint = "ipc:///tmp/sentinel_oneway_" + std::to_string(getpid());
  int result_pipe[2];
  if (pipe(result_pipe) != 0) return 2;
  const pid_t child = fork();
  if (child < 0) return 3;

  if (child == 0) {
    close(result_pipe[0]);
    pin_cpu(cpu_rx);
    void* ctx = zmq_ctx_new();
    void* pull = zmq_socket(ctx, ZMQ_PULL);
    int hwm = n + 1000; zmq_setsockopt(pull, ZMQ_RCVHWM, &hwm, sizeof(hwm));
    if (zmq_bind(pull, endpoint.c_str()) != 0) _exit(4);
    Wire msg{};
    std::vector<double> us; us.reserve(n);
    for (int i = 0; i < n; ++i) {
      const int size = zmq_recv(pull, &msg, sizeof(msg), 0);
      if (size != static_cast<int>(sizeof(msg))) _exit(5);
      const auto end = now_ns();
      us.push_back(static_cast<double>(end - msg.ts_ns) / 1e3);
    }
    const Result r = summarize(us);
    (void)!write(result_pipe[1], &r, sizeof(r));
    close(result_pipe[1]);
    zmq_close(pull); zmq_ctx_term(ctx);
    _exit(0);
  }

  close(result_pipe[1]);
  pin_cpu(cpu_tx);
  void* ctx = zmq_ctx_new();
  void* push = zmq_socket(ctx, ZMQ_PUSH);
  int hwm = n + 1000; zmq_setsockopt(push, ZMQ_SNDHWM, &hwm, sizeof(hwm));
  if (zmq_connect(push, endpoint.c_str()) != 0) return 6;
  usleep(100000);
  Wire msg{};
  for (int i = 0; i < 1000; ++i) { msg.seq=i; msg.ts_ns=now_ns(); zmq_send(push, &msg, sizeof(msg), 0); }
  for (int i = 0; i < n; ++i) { msg.seq=static_cast<std::uint64_t>(i); msg.ts_ns=now_ns(); while (zmq_send(push, &msg, sizeof(msg), ZMQ_DONTWAIT) < 0) {} }
  zmq_close(push); zmq_ctx_term(ctx);

  Result r{}; const ssize_t got = read(result_pipe[0], &r, sizeof(r));
  close(result_pipe[0]); waitpid(child, nullptr, 0);
  std::cout << std::fixed << std::setprecision(3)
            << "samples=" << n
            << " median_us=" << r.median_us
            << " p99_us=" << r.p99_us
            << " p99_9_us=" << r.p99_9_us
            << " result_bytes=" << got << "\n";
}