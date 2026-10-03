#pragma once

#include <cerrno>
#include <cstring>
#include <iostream>
#include <pthread.h>
#include <sched.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>

namespace sentinel {

struct RuntimeProfile {
  int cpu{-1};
  bool lock_memory{false};
  bool realtime{false};
  int fifo_priority{10};
};

inline void apply_runtime_profile(const RuntimeProfile& profile) {
  if (profile.cpu >= 0) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(profile.cpu, &cpuset);
    const int rc = pthread_setaffinity_np(pthread_self(), sizeof(cpuset), &cpuset);
    std::cerr << "runtime.cpu_affinity=" << (rc == 0 ? "ok" : std::strerror(rc))
              << " cpu=" << profile.cpu << "\n";
  }

  if (profile.lock_memory) {
    const int rc = mlockall(MCL_CURRENT | MCL_FUTURE);
    std::cerr << "runtime.mlockall=" << (rc == 0 ? "ok" : std::strerror(errno)) << "\n";
  }

  if (profile.realtime) {
    sched_param param{};
    param.sched_priority = profile.fifo_priority;
    const int rc = pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    std::cerr << "runtime.sched_fifo=" << (rc == 0 ? "ok" : std::strerror(rc))
              << " priority=" << profile.fifo_priority << "\n";
  }
}

} // namespace sentinel