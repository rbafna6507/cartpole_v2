#include <Arduino.h>
#include <Wire.h>
#include <QNEthernet.h>
#include "executor.h"
#include "motor_io.h"
#include "teensy_reference_store.h"

namespace deployment_firmware {
using namespace qindesign::network;
constexpr int USB_CLIENT=1,NET_CLIENT=2;
deployment::Executor core;
deployment::FrameParser usb_parser,net_parser;
EthernetServer server(9000);EthernetClient net_client;
bool net_ready=false,net_active=false,usb_present=false,encoder_configured=false;
uint32_t next_control=0,last_usb_stream=0,last_net_stream=0;
unsigned applied_home=0,usb_stream=0,net_stream=0;
struct TxQueue {
  char bytes[2048]{};size_t head=0,tail=0;uint32_t dropped=0;
  void clear(){head=tail=0;}
  bool push(const char *data,size_t n) {
    const size_t used=(head+sizeof bytes-tail)%sizeof bytes;
    if(n>=sizeof bytes-used){++dropped;return false;}
    for(size_t i=0;i<n;i++){bytes[head]=data[i];head=(head+1)%sizeof bytes;}return true;
  }
  template<class Transport>void service(Transport &transport) {
    if(head==tail)return;
    const int room=transport.availableForWrite();if(room<=0)return;
    size_t n=head>tail?head-tail:sizeof bytes-tail;
    if(n>size_t(room))n=size_t(room);if(n>256)n=256;
    const size_t sent=transport.write((const uint8_t *)bytes+tail,n);
    tail=(tail+sent)%sizeof bytes;
  }
};
TxQueue usb_tx,net_tx;
bool send(int client,const char *payload) {
  char encoded[257];const size_t n=deployment::frame(payload,encoded,sizeof encoded);
  if(!n)return false;
  if(client==USB_CLIENT)return usb_tx.push(encoded,n);
  return net_active && net_tx.push(encoded,n);
}
void harvestFault() {
  switch(stepper::pending) {
    case stepper::Fault::TIMING:core.latch("timing");break;
    case stepper::Fault::DEADLINE:core.latch("deadline");break;
    case stepper::Fault::RAIL:core.latch("rail");break;
    default:break;
  }
}
void syncMotor() {
  harvestFault();
  if(applied_home!=core.home_generation) {
    stepper::disable();stepper::home(core.half);applied_home=core.home_generation;
  }
  stepper::syncEnable(core.enabled(),core.deadline);
}
bool writeEncoder(uint8_t reg,uint8_t value) {
  Wire1.beginTransmission(0x36);Wire1.write(reg);Wire1.write(value);
  return Wire1.endTransmission()==0;
}
int readEncoder(uint8_t reg,uint8_t count) {
  Wire1.beginTransmission(0x36);Wire1.write(reg);
  if(Wire1.endTransmission(false)!=0)return -1;
  if(Wire1.requestFrom(uint8_t(0x36),count)!=count)return -1;
  int result=0;for(uint8_t i=0;i<count;i++)result=(result<<8)|Wire1.read();return result;
}
void control() {
  harvestFault();core.checkDeadline(micros());syncMotor();
  // Same volatile SF=2x setting as working source; no bus use inside ISR.
  const int status=readEncoder(0x0b,1),raw=readEncoder(0x0c,2);
  const uint32_t now=micros();
  const bool valid=encoder_configured && status>=0 && (status&0x38)==0x20 && raw>=0;
  core.sample(now,raw>=0?raw&4095:-1,valid);
  core.tick(now,float(stepper::position)/cart_hardware::steps_per_m);
  syncMotor();stepper::rate(core.motion.velocity);
  // Publish only after sensor, governor and pulse update have completed.
  stepper::heartbeat=micros();
}
void process(int client,const char *payload) {
  harvestFault();core.x=float(stepper::position)/cart_hardware::steps_per_m;
  char reply[250];const bool was_clear=std::strcmp(payload,"D1 clear")==0;
  core.handle(payload,micros(),client,reply,sizeof reply);
  if(was_clear && core.mode==deployment::Mode::DISARMED)stepper::clearFault();
  if(std::strcmp(reply,"D1 OK stream")==0) {
    if(client==USB_CLIENT)usb_stream=core.stream_hz;else net_stream=core.stream_hz;
  }
  syncMotor();
  if(!send(client,reply) && core.enabled() && core.owner==client){core.latch("tx");syncMotor();}
}
void frameByte(int client,deployment::FrameParser &parser,char c) {
  char payload[250];const auto result=parser.feed(c,payload,sizeof payload);
  if(result==deployment::FrameResult::GOOD)process(client,payload);
  else if(result==deployment::FrameResult::BAD) {
    core.invalidInput();syncMotor();send(client,"D1 ERR frame");
  }
}
void pollUsb() {
  const bool present=bool(Serial);
  if(usb_present && !present) {
    core.disconnected(USB_CLIENT);syncMotor();usb_parser.reset();usb_tx.clear();usb_stream=0;
  }
  usb_present=present;if(!present)return;
  unsigned budget=128;
  while(budget-- && Serial.available()) {
    const int c=Serial.read();if(c<0)break;frameByte(USB_CLIENT,usb_parser,char(c));
    if(c=='\n')break;
  }
}
void closeNet() {
  net_client.abort();net_active=false;net_parser.reset();net_tx.clear();net_stream=0;
}
void pollNet() {
  if(!net_ready)return;
  if(net_active && (!Ethernet.linkState() || !bool(net_client))) {
    // Disable before clearing buffered input; old queued actions cannot restart.
    core.disconnected(NET_CLIENT);syncMotor();closeNet();return;
  }
  EthernetClient incoming=server.accept();
  if(incoming) {
    if(net_active || core.enabled())incoming.abort();
    else {net_client=incoming;net_client.setNoDelay(true);net_active=true;net_parser.reset();net_tx.clear();net_stream=0;}
  }
  if(!net_active)return;
  unsigned budget=128;
  while(budget-- && net_client.available()) {
    const int c=net_client.read();if(c<0)break;frameByte(NET_CLIENT,net_parser,char(c));
    if(c=='\n')break;
  }
}
void streams() {
  const uint32_t now=micros();char payload[250];
  if(usb_present && usb_stream && uint32_t(now-last_usb_stream)>=1000000/usb_stream) {
    last_usb_stream=now;core.state(payload,sizeof payload);send(USB_CLIENT,payload);
  }
  if(net_active && net_stream && uint32_t(now-last_net_stream)>=1000000/net_stream) {
    last_net_stream=now;core.state(payload,sizeof payload);send(NET_CLIENT,payload);
  }
}
} // namespace deployment_firmware

void setup() {
  using namespace deployment_firmware;
  stepper::initialize();core.hardware_ready=stepper::timer_ready;
  if(!core.hardware_ready)core.latch("timer");
  Serial.begin(115200);
  uint16_t saved;if(teensy_reference_store::load(saved))core.upright_raw=saved;
  Wire1.setSDA(17);Wire1.setSCL(16);Wire1.begin();Wire1.setClock(400000);
  encoder_configured=writeEncoder(0x07,0x03);encoder_configured=writeEncoder(0x08,0x00) && encoder_configured;
  net_ready=Ethernet.begin(IPAddress(192,168,50,2),IPAddress(255,255,255,0),IPAddress(0,0,0,0));
  if(net_ready)server.begin();
  next_control=micros();
}
void loop() {
  using namespace deployment_firmware;
  const uint32_t now=micros();
  harvestFault();core.checkDeadline(now);syncMotor();
  if(int32_t(now-next_control)>=0) {
    if(uint32_t(now-next_control)>2000 && core.enabled())core.latch("timing");
    next_control+=1000;
    if(int32_t(now-next_control)>=0)next_control=now+1000;
    control();
  }
  pollNet();pollUsb();streams();
  if(net_active)net_tx.service(net_client);
  if(usb_present)usb_tx.service(Serial);
}
