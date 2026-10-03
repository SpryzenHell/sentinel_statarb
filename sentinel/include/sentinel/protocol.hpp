#pragma once

#include <cstdint>
#include <type_traits>

namespace sentinel {

enum class MessageType : std::uint8_t {
  kTick = 1,
  kOrder = 2,
  kShutdown = 3,
  kReport = 4,
};

enum class Side : std::int8_t { kSell = -1, kBuy = 1 };

#pragma pack(push, 1)
struct TickMessage {
  MessageType type;
  std::uint64_t seq;
  std::uint64_t ts_ns;
  double bid_a;
  double ask_a;
  double bid_b;
  double ask_b;
  double volatility;
};

struct OrderMessage {
  MessageType type;
  Side side;
  std::uint16_t reserved;
  std::uint64_t id;
  std::uint64_t ts_ns;
  double qty;
};

struct ReportMessage {
  MessageType type;
  Side side;
  std::uint16_t status;
  std::uint64_t id;
  std::uint64_t recv_ts_ns;
  double fill_a;
  double fill_b;
  double qty;
  double spread;
  double oco_stop_spread;
  double oco_limit_spread;
};
#pragma pack(pop)

static_assert(std::is_trivially_copyable_v<TickMessage>);
static_assert(std::is_trivially_copyable_v<OrderMessage>);
static_assert(std::is_trivially_copyable_v<ReportMessage>);

} // namespace sentinel
