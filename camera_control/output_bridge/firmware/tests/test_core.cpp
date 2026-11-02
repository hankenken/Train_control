#include "../TC2_DRV8235/tc2_core.h"
#include <cassert>
#include <string>
#include <vector>
#include <iostream>
struct Fake:tc2::Hardware {
 uint32_t now=0; int starts=0,ends=0,triggers=0,configs=0; bool awake=false;
 const char* config_error=nullptr; const char* start_error=nullptr; const char* end_error=nullptr;
 std::vector<std::string> lines;
 uint32_t clock()override{return now;}
 void inhibit()override{awake=false;} void trigger()override{++triggers;}
 void wake()override{awake=true;} const char* configure()override{++configs;return config_error;}
 const char* start(uint8_t,bool)override{++starts;return start_error;}
 const char* finish(uint8_t)override{++ends;return end_error;}
 void emit(const char* s)override{lines.push_back(s);}
 bool has(const std::string& s){for(auto& x:lines)if(x==s)return true;return false;}
};
struct Rig {
 Fake h;tc2::Controller c{h};uint32_t seq=0;
 Rig(){c.begin();}
 void cmd(std::string s){char b[128];snprintf(b,sizeof(b),"%s",s.c_str());c.command(b);}
 void next(std::string s){auto p=s.find(' ');cmd(s.substr(0,p)+" "+std::to_string(++seq)+(p==s.npos?"":s.substr(p)));}
 void tick(uint32_t dt=1,bool permit=false,bool nf=true,bool usb=true,uint16_t vm=225){h.now+=dt;c.tick(vm,permit,nf,usb);}
 void power(){tick(1,false,true,true,0);tick(100,false,true,true,0);tick(1);tick(100);assert(c.vm_ready);}
 void prepare(){tick(1);tick(1,true);tick(1,true);assert(h.configs);}
 void arm(){next("HB");next("ARM");prepare();assert(c.armed);}
 void pulse(int ch=0,int width=50){next("HB");next("PULSE "+std::to_string(ch)+" P "+std::to_string(width));prepare();assert(c.active==ch);}
};
int main(){
 int passed=0;
 {Rig r;r.next("HB");r.next("ARM");assert(r.h.has("ERR 2 VM_RESET_REQUIRED"));assert(r.h.starts==0);++passed;}
 {Rig r;r.cmd("HELLO");r.cmd("STATUS");assert(r.c.last_seq==0&&!r.c.armed&&r.h.triggers==0);++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.tick(49,true);assert(r.h.ends==0);r.tick(1,true);assert(r.h.ends==1&&!r.h.awake&&r.c.active==-1);assert(r.h.has("DONE 4 0"));++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.cmd("PULSE 4 0 P 50");assert(r.h.has("ERR 4 STALE")&&r.h.starts==1);r.next("PULSE 1 N 20");assert(r.h.has("ERR 5 BUSY"));r.tick(50,true);r.next("PULSE 0 N 20");assert(r.h.has("ERR 6 COOLDOWN"));++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.cmd("STOP 1");assert(!r.c.armed&&r.c.active==-1&&!r.h.awake&&r.h.has("ERR 1 STALE"));++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.tick(1,false);assert(std::string(r.c.fault)=="GATE_TIMEOUT"&&!r.h.awake);r.next("ARM");assert(!r.c.armed);++passed;}
 {Rig r;r.power();r.arm();r.tick(500);assert(std::string(r.c.fault)=="HEARTBEAT_TIMEOUT"&&!r.c.armed);++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.tick(1,true,true,false);assert(std::string(r.c.fault)=="USB_LOST"&&!r.h.awake);++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.tick(1,true,false);assert(std::string(r.c.fault)=="DRIVER_FAULT"&&!r.h.awake);++passed;}
 {Rig r;r.power();r.next("HB");r.h.config_error="CONFIG_MISMATCH";r.next("ARM");r.prepare();assert(!r.c.armed&&r.h.starts==0&&!r.h.awake);++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.h.end_error="I2C_FAULT";r.tick(50,true);assert(!r.h.awake&&std::string(r.c.fault)=="I2C_FAULT"&&!r.h.has("DONE 4 0"));++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.cmd("PULSE 9999999999999 0 P 50");assert(!r.h.awake&&std::string(r.c.fault)=="MALFORMED");++passed;}
 {Rig r;r.power();r.next("HB");r.next("ARM");r.tick(299,true);assert(r.h.triggers==0);r.tick(1,true);assert(std::string(r.c.fault)=="GATE_TIMEOUT"&&r.h.starts==0);++passed;}
 {Rig r;r.power();r.next("HB");r.next("ARM");r.tick(1);r.tick(5);assert(std::string(r.c.fault)=="GATE_MISSING"&&r.h.starts==0);++passed;}
 {Rig r;r.power();r.h.now=0xFFFFFFF0u;r.arm();r.pulse(3,100);r.tick(99,true);assert(r.c.active==3);r.tick(1,true);assert(r.c.active==-1);++passed;}
 {Rig r;r.power();r.arm();r.pulse();r.tick(1,true,true,true,0);assert(std::string(r.c.fault)=="VM_LOST"&&!r.h.awake);++passed;}
 std::cout<<passed<<" firmware state-machine scenarios passed\n";
}
