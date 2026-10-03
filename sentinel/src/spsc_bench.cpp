#include "sentinel/spsc_ring.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>

struct Item {
  std::uint64_t seq{};
  double value{};
};

int main() {
  sentinel::SpscRing<Item, 1 << 16> q;
  constexpr std::uint64_t N = 5'000'000;
  std::uint64_t checksum = 0;

  const auto t0 = std::chrono::steady_clock::now();
  std::thread consumer([&] {
    Item item{};
    for (std::uint64_t i = 0; i < N; ++i) {
      while (!q.try_pop(item)) {}
      checksum += item.seq;
    }
  });

  for (std::uint64_t i = 0; i < N; ++i) {
    Item item{i, 1.0};
    while (!q.try_emplace(item)) {}
  }

  consumer.join();
  const double sec = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - t0).count();

  std::cout << "items=" << N
            << " throughput_mops=" << (N / sec / 1e6)
            << " checksum=" << checksum
            << " capacity=" << q.capacity() << '\n';
}
