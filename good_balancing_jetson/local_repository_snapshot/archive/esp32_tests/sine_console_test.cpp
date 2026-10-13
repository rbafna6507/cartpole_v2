#include <cassert>
#include <cstdio>
#include "../cart_sine/cart_sine.ino"

void send(const char* text) {
  Serial.output.clear();
  char buffer[128];
  snprintf(buffer, sizeof(buffer), "%s", text);
  command(buffer);
}
int main() {
  setup();
  send("check 25 2.2");
  assert(!active && Serial.output.find("Rejected") != std::string::npos);
  for (const char* invalid : {"limits nan 5000", "limits 1250 inf", "limits 0 10",
                             "limits 4000 10000", "limits 1250", "limits 1250 7500 extra"}) {
    send(invalid);
    assert(limits.speedMmS == 1000 && limits.accelerationMmS2 == 5000);
  }
  send("limits 1250 7500");
  assert(limits.speedMmS == 1250 && limits.accelerationMmS2 == 7500);
  send("check 25 2.2");
  assert(!active && !cart->isRunning() && Serial.output.find("Accepted") != std::string::npos);
  send("run 25 2.2"); // Still needs a center reference.
  assert(!active);
  send("center");
  send("run 25 2.2");
  assert(active && cart->isRunning());
  send("limits 1500 10000");
  assert(limits.speedMmS == 1250 && limits.accelerationMmS2 == 7500);
  send("stop");
  for (int i = 0; active && i < 5000; ++i) { cart->consume(); loop(); }
  assert(!active && centered && cart->pos == 0);
  assert(pins[27] == LOW); // Normal stop retains holding torque.
  // Exercise faster accepted motion, then normal finish using the queue model.
  send("limits 3000 75000");
  send("run 100 4");
  assert(active);
  for (int i = 0; i < 3000; ++i) { cart->consume(); loop(); }
  send("stop");
  for (int i = 0; active && i < 3000; ++i) { cart->consume(); loop(); }
  assert(!active && centered && cart->pos == 0);
  // A slower backend must lower the allowable setting too.
  maxSegmentSteps = 20;
  send("limits 1000 5000");
  assert(limits.speedMmS == 3000); // Rejected atomically, not partially applied.
  send("run 100 4");
  assert(!active);
  puts("Sine limit commands, previews, queue completion and backend guard passed.");
}
