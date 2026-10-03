#pragma once

#include <atomic>
#include <cstddef>
#include <memory>
#include <new>
#include <type_traits>
#include <utility>

namespace sentinel {

// Bounded SPSC ring with one slack slot, release/acquire publication,
// and cache-line separation for producer/consumer cursors.
template <typename T, std::size_t Capacity>
class alignas(64) SpscRing {
  static_assert(Capacity >= 2, "Capacity must be >= 2");

 public:
  SpscRing() = default;
  ~SpscRing() { clear(); }
  SpscRing(const SpscRing&) = delete;
  SpscRing& operator=(const SpscRing&) = delete;

  template <typename... Args>
  bool try_emplace(Args&&... args) noexcept(
      std::is_nothrow_constructible_v<T, Args&&...>) {
    const auto head = head_.load(std::memory_order_relaxed);
    const auto next = increment(head);
    if (next == tail_.load(std::memory_order_acquire)) return false;
    std::construct_at(ptr(head), std::forward<Args>(args)...);
    head_.store(next, std::memory_order_release);
    return true;
  }

  bool try_pop(T& out) noexcept(std::is_nothrow_move_assignable_v<T>) {
    const auto tail = tail_.load(std::memory_order_relaxed);
    if (tail == head_.load(std::memory_order_acquire)) return false;
    T* p = ptr(tail);
    out = std::move(*p);
    std::destroy_at(p);
    tail_.store(increment(tail), std::memory_order_release);
    return true;
  }

  std::size_t size() const noexcept {
    const auto h = head_.load(std::memory_order_acquire);
    const auto t = tail_.load(std::memory_order_acquire);
    return h >= t ? h - t : Capacity - (t - h);
  }

  constexpr std::size_t capacity() const noexcept { return Capacity - 1; }

  void clear() noexcept {
    const auto tail = tail_.load(std::memory_order_relaxed);
    const auto head = head_.load(std::memory_order_relaxed);
    auto i = tail;
    while (i != head) {
      std::destroy_at(ptr(i));
      i = increment(i);
    }
    tail_.store(head, std::memory_order_relaxed);
  }

 private:
  static std::size_t increment(std::size_t i) noexcept {
    return (i + 1 == Capacity) ? 0 : i + 1;
  }

  T* ptr(std::size_t i) noexcept {
    return std::launder(reinterpret_cast<T*>(&storage_[i]));
  }

  using Storage = std::aligned_storage_t<sizeof(T), alignof(T)>;
  alignas(64) std::atomic<std::size_t> head_{0};
  alignas(64) std::atomic<std::size_t> tail_{0};
  alignas(64) Storage storage_[Capacity];
};

} // namespace sentinel
