#include "../../swingup/cart_motion.h"
#include <cstdio>
int main() {
  cart_motion::State s; s.velocity=-0.7411f;s.acceleration=-1.28f;
  float x=0.06543f;
  for(int i=1;i<=30;++i) {
    // Strongest possible request opposing the negative velocity.
    s=cart_motion::advance(s,x,15.0f,.75f,15.0f,15.0f,50.0f,.15f,.001f);
    x+=s.velocity*.001f;
    if(s.velocity<-.752f) {
      std::printf("Even maximum positive demand crosses firmware fault threshold after %d ms: v=%.6f m/s a=%.3f m/s^2 x=%.5f m\n",i,s.velocity,s.acceleration,x);
      return 0;
    }
  }
  return 1;
}
