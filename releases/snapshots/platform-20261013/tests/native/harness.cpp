// This translation unit includes the generated, assertion-checked ORIGINAL sketch.
// Only the protocol/reset/peripheral environment below is native test support.
#include <iostream>
#include <iomanip>
#include <sstream>
#include <string>
#include "firmware_native.ino"

static void output(){
 std::cout << std::setprecision(10)
  << "{\"mode\":" << static_cast<int>(mode)
  << ",\"theta\":" << th << ",\"angle_hat\":" << th_hat
  << ",\"rate_hat\":" << thd_hat << ",\"velocity\":" << vc
  << ",\"acceleration\":" << acc_cmd << ",\"demand\":" << oracle_demand
  << ",\"brake_direction\":" << cart_brake_direction << ",\"energy\":" << energy_n
  << ",\"enabled\":" << (g_energized?"true":"false")
  << ",\"upright_only\":" << (upright_only?"true":"false")
  << ",\"encoder_ok\":" << (enc_ok?"true":"false")
  << ",\"encoder_consecutive_errors\":" << enc_consec_err
  << ",\"encoder_recoveries\":" << enc_recoveries << "}" << std::endl;
}
static void reset(float theta,uint64_t now){
 oracle_now_us=now;step_timer_ready=true;timing_fault_pending=false;
 eStop();
 pump={};response_watch={};rail_recovery_state={};spin_recovery_state={};upright_return={};
 capture_upright=false;reference_saved=false;enc_upright_raw=encoder_reference::upright_raw;
 oracle_theta=swing_control::wrap(theta);oracle_x=oracle_demand=0;
 th=th_hat=oracle_theta;thd=thd_hat=0;xc=vc=acc_cmd=0;energy_n=-1;z_mm=0;
 req_estimator_reset=false;req_diag=req_encoder=diag_done=false;
 requested_upright_raw=0;reference_save_pending=false;reference_capture.reset();zero_t0=0;
 enc_last_raw=enc_ticks=enc_zero=0;enc_consec_err=enc_errors=enc_recoveries=0;
 enc_ok=true;Wire1.healthy=true;enc_status=enc_agc=0;
 home_steps=zhome_steps=0;v_manual_deadline=0;last_host_command_ms=millis();host_seen=false;
 next_control_us=control_deadline_misses=0;control_heartbeat_us=micros();
 tx_head=tx_tail=0;dropped_serial_frames=dropped_control_messages=0;
 for(int i=0;i<N_AX;++i){ax_pos[i]=ax_inc[i]=ax_acc[i]=0;ax_dir[i]=1;direction_initialized[i]=false;}
 computeGains();
}
int main(){
 std::string line;
 while(std::getline(std::cin,line)){
  std::istringstream in(line);std::string op;in>>op;
  if(op=="quit")break;
  if(op=="reset"){
   float theta;uint64_t now;in>>theta>>now;reset(theta,now);output();
  }else if(op=="param"){
   std::string name;float value;in>>name>>value;bool found=false;
   for(const auto &p:PARAMS)if(name==p.name){*p.ptr=value;found=true;break;}
   if(!found){std::cout<<"{\"error\":\"unknown parameter\"}"<<std::endl;continue;}
   computeGains();std::cout<<"{}"<<std::endl;
  }else if(op=="tick"){
   float theta,x,value;uint64_t now;int encoder,host;std::string command;
   in>>theta>>x>>now>>encoder>>host>>command>>value;
   oracle_now_us=now;oracle_x=x;oracle_demand=0;
   Wire1.healthy=encoder!=0;enc_ok=encoder!=0;
   if(encoder)oracle_theta=swing_control::wrap(theta);
   if(host)last_host_command_ms=millis();
   if(command!="-"){
    char cmd[96];std::snprintf(cmd,sizeof(cmd),"%s %.9g",command.c_str(),value);handleLine(cmd);
   }
   controlTick();output();
  }else if(op=="gains"){
   const auto k=swing_control::gains(controller),b=swing_control::uprightGains(controller);
   std::cout<<std::setprecision(10)<<"{\"k1\":"<<k.k1<<",\"k2\":"<<k.k2<<",\"k3\":"<<k.k3<<",\"k4\":"<<k.k4
    <<",\"bal_k1\":"<<b.k1<<",\"bal_k2\":"<<b.k2<<",\"bal_k3\":"<<b.k3<<",\"bal_k4\":"<<b.k4<<"}"<<std::endl;
  }else if(op=="estimate"){
   float measured,angle,rate,bandwidth,dt;in>>measured>>angle>>rate>>bandwidth>>dt;
   swing_control::estimate(measured,bandwidth,dt,angle,rate);
   std::cout<<std::setprecision(10)<<"{\"angle_hat\":"<<angle<<",\"rate_hat\":"<<rate<<"}"<<std::endl;
  }else if(op=="motion"){
   cart_motion::State s;float x,request,vmax,drive,brake,jerk,rail,dt;
   in>>s.velocity>>s.acceleration>>s.brake_direction>>x>>request>>vmax>>drive>>brake>>jerk>>rail>>dt;
   s=cart_motion::advance(s,x,request,vmax,drive,brake,jerk,rail,dt);
   std::cout<<std::setprecision(10)<<"{\"velocity\":"<<s.velocity<<",\"acceleration\":"<<s.acceleration<<",\"brake_direction\":"<<s.brake_direction<<"}"<<std::endl;
  }else if(op=="stopping"){
   float v,a,amax,jerk;in>>v>>a>>amax>>jerk;
   std::cout<<std::setprecision(10)<<"{\"distance\":"<<cart_motion::stoppingDistance(v,a,amax,jerk)<<"}"<<std::endl;
  }else{std::cout<<"{\"error\":\"unknown operation\"}"<<std::endl;}
 }
}
