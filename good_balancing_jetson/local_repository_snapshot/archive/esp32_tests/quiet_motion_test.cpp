#include "../characterize/quiet_motion.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

int main(int argc, char **argv) {
  QuietMotion detector;
  // A stationary encoder dithering by one tick must stop after 3 s.
  for (uint32_t ms=0; ms<=4000; ms+=2)
    assert(detector.update((ms/2)%2, ms) == (ms >= 3000));

  // Exact threshold: 11 ticks qualify; 12-tick oscillations do not.
  detector.reset();
  for (uint32_t ms=0; ms<=4000; ms+=2)
    assert(detector.update((ms/200)%2 ? 11 : 0, ms) == (ms >= 3000));
  detector.reset();
  for (uint32_t ms=0; ms<=10000; ms+=2)
    assert(!detector.update((ms/200)%2 ? 12 : 0, ms));

  // Turning points of a sustained 4-degree swing cannot end the capture.
  detector.reset();
  for (uint32_t ms=0; ms<=10000; ms+=2)
    assert(!detector.update(std::lround(23*std::sin(ms*0.001*2*3.141592653589793/0.85)), ms));

  // Sub-degree movement ends, irrespective of angular speed spikes.
  detector.reset();
  for (uint32_t ms=0; ms<=4000; ms+=2)
    assert(detector.update(std::lround(4*std::sin(ms*0.001*2*3.141592653589793/0.85)), ms) == (ms >= 3000));

  // Slow drift must not evade the peak-to-peak threshold.
  detector.reset();
  for (uint32_t ms=0; ms<=10000; ms+=2)
    assert(!detector.update(ms/100, ms));

  // Missing samples and explicit sensor errors restart the quiet interval.
  detector.reset();
  for (uint32_t ms=0; ms<3000; ms+=2) assert(!detector.update(0, ms));
  assert(!detector.update(0, 3100));
  for (uint32_t ms=3102; ms<=6100; ms+=2)
    assert(detector.update(0, ms) == (ms == 6100));
  detector.reset();
  assert(!detector.update(0, 6102));

  // Unsigned timer wrap is allowed; a large unwrapped encoder offset is too.
  detector.reset();
  for (uint32_t elapsed=0; elapsed<=4000; elapsed+=2)
    assert(detector.update(1000000 + (elapsed/2)%2, UINT32_MAX-1500+elapsed) == (elapsed >= 3000));

  // Replay real captures through the same C++ detector used on the ESP32.
  for (int arg=1; arg<argc; ++arg) {
    std::ifstream input(argv[arg]); assert(input.good());
    std::string line; std::getline(input,line);
    detector.reset(); double first_us=-1, ended=-1;
    while (std::getline(input,line)) {
      std::stringstream row(line); std::string field;
      double us=0; int32_t ticks=0;
      for (int col=0; col<=4; ++col) {
        assert(static_cast<bool>(std::getline(row,field,',')));
        if (col==1) us=std::stod(field);
        if (col==4) ticks=static_cast<int32_t>(std::stod(field));
      }
      if (first_us<0) first_us=us;
      const auto ms=static_cast<uint32_t>((us-first_us)*0.001);
      if (detector.update(ticks,ms) && ms>=7000) { ended=ms*0.001; break; }
    }
    assert(ended>=7 && ended<45);
    std::printf("%s: quiet at %.3f seconds\n",argv[arg],ended);
  }
  std::puts("Quiet detection checks passed.");
}
