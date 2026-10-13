#pragma once
#include <cstdint>
#include <deque>
constexpr uint32_t TICKS_PER_S = 16000000;
enum MoveTimedResultCode { MOVE_TIMED_OK, MOVE_TIMED_BUSY, MOVE_TIMED_EMPTY };
// Queue model for command/state tests only; not an electrical timing model.
struct FastAccelStepper {
  struct Entry { int steps; uint32_t ticks; };
  std::deque<Entry> queue;
  int32_t pos = 0, target = 0;
  bool running = false, busy = false;
  uint16_t minTicks = 80;
  void setDirectionPin(uint8_t, bool) {}
  void setAutoEnable(bool) {}
  uint16_t getMaxSpeedInTicks() { return minTicks; }
  bool isRunning() { return running || !queue.empty(); }
  int32_t getCurrentPosition() { return pos; }
  int32_t getPositionAfterCommandsCompleted() { return target; }
  void setCurrentPosition(int32_t p) { pos = target = p; }
  void forceStopAndNewPosition(int32_t p) { queue.clear(); running = false; setCurrentPosition(p); }
  uint32_t ticksInQueue() {
    uint32_t ticks = 0;
    for (size_t i = 1; i < queue.size(); ++i) ticks += queue[i].ticks;
    return ticks;
  }
  MoveTimedResultCode moveTimed(int16_t steps, uint32_t ticks, uint32_t* actual, bool start) {
    if (busy) return MOVE_TIMED_BUSY;
    const auto result = queue.empty() ? MOVE_TIMED_EMPTY : MOVE_TIMED_OK;
    if (ticks) { queue.push_back({steps, ticks}); target += steps; }
    if (actual) *actual = ticks;
    if (start && !queue.empty()) running = true;
    return result;
  }
  void consume() {
    if (running && !queue.empty()) { pos += queue.front().steps; queue.pop_front(); }
    if (queue.empty()) running = false;
  }
};
struct FastAccelStepperEngine {
  FastAccelStepper channel;
  void init() {}
  FastAccelStepper* stepperConnectToPin(uint8_t) { return &channel; }
};
