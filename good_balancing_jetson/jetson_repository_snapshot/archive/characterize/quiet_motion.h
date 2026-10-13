#pragma once
#include <stdint.h>

// A quiet interval contains no more than 1 degree of total encoder travel
// (peak-to-peak). Use unwrapped ticks, not differentiated angular speed:
// quantization at 500 Hz otherwise turns a one-tick change into a speed spike.
class QuietMotion {
 public:
  static constexpr int32_t kMaxRangeTicks = 11; // 11 * 360/4096 = 0.967 deg
  static constexpr uint32_t kDwellMs = 3000;
  static constexpr uint32_t kMaxSampleGapMs = 20;

  void reset() { valid_ = false; }

  bool update(int32_t ticks, uint32_t now) {
    if (!valid_ || (uint32_t)(now - last_) > kMaxSampleGapMs) {
      begin(ticks, now);
      return false;
    }
    last_ = now;
    if (ticks < low_) low_ = ticks;
    if (ticks > high_) high_ = ticks;
    if ((int64_t)high_ - low_ > kMaxRangeTicks) {
      // Start a new candidate interval at this sample. Retaining the range
      // throughout the dwell also prevents slow drift from looking still.
      begin(ticks, now);
      return false;
    }
    return (uint32_t)(now - since_) >= kDwellMs;
  }

 private:
  void begin(int32_t ticks, uint32_t now) {
    valid_ = true;
    low_ = high_ = ticks;
    since_ = last_ = now;
  }
  bool valid_ = false;
  int32_t low_ = 0, high_ = 0;
  uint32_t since_ = 0, last_ = 0;
};
