#include "../frequency_test/frequency_motion.h"
#include <cassert>
#include <cstdio>
#include <limits>
#include <initializer_list>
namespace ft=frequency_test;
int main(int argc,char**) {
  if(argc>1) {
    auto s=ft::sample({100,.25},3.14159);
    std::printf("%.12g %.12g %.12g %.12g\n",s.x,s.v,s.a,s.j);
    return 0;
  }
  assert(ft::valid({270,.5}));
  assert(ft::rampSeconds({100,.05})==2);
  assert(ft::rampSeconds({100,.25,3})==3);
  assert(!ft::valid({100,.25,0}));
  assert(!ft::valid({300,.5}));
  assert(!ft::valid({270,5}));
  assert(!ft::valid({100,0}));
  assert(!ft::valid({std::numeric_limits<double>::quiet_NaN(),1}));
  for(double travel:{1.,100.,270.}) for(double hz:{.02,.25,1.,5.}) {
    ft::Config c={travel,hz}; if(!ft::valid(c))continue;
    const double ramp=ft::rampSeconds(c), finish=ramp+2.37/hz, end=finish+ramp;
    double old_v=0,x_integrated=0;
    for(double t=0;t<end+.01;t+=.001) {
      const auto s=ft::sample(c,t,finish),next=ft::sample(c,t+.001,finish);
      assert(fabs(s.x)<=travel/2000+1e-9);
      assert(fabs(s.v)<=ft::speedBound(c)+1e-9);
      // Exactly the interval velocity dispatched by the firmware.
      double v=(next.x-s.x)/.001;
      assert(fabs(v)<=ft::max_speed+1e-6);
      x_integrated+=v*.001;
      assert(fabs(x_integrated-next.x)<1e-8);
      assert(fabs(v-old_v)<.05);old_v=v;
      if(t>.01 && fabs(t-ramp)>.01 && fabs(t-finish)>.01 && fabs(t-end)>.01) {
        const double h=1e-5;
        const auto lo=ft::sample(c,t-h,finish),hi=ft::sample(c,t+h,finish);
        assert(fabs((hi.x-lo.x)/(2*h)-s.v)<1e-5);
        assert(fabs((hi.v-lo.v)/(2*h)-s.a)<1e-4);
        assert(fabs((hi.a-lo.a)/(2*h)-s.j)<.01);
      }
    }
    assert(fabs(x_integrated)<1e-7);
    const auto ended=ft::sample(c,end+.001,finish);
    assert(ended.x==0 && ended.v==0 && ended.a==0 && ended.j==0);
  }
  std::puts("Waveform checks passed: range, pulse ceiling, derivatives, ramps, centered finish.");
}
