#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Platform-independent command/state machine. No camera or physical-position claim.
namespace tc2 {
struct Hardware {
  virtual ~Hardware() {}
  virtual uint32_t clock() = 0;
  virtual void inhibit() = 0;
  virtual void trigger() = 0;
  virtual void wake() = 0;
  virtual const char* configure() = 0;
  virtual const char* start(uint8_t channel, bool positive) = 0;
  virtual const char* finish(uint8_t channel) = 0;
  virtual void emit(const char* line) = 0;
};
class Controller {
 public:
  explicit Controller(Hardware& h): hw(h) {}
  bool armed=false;
  int8_t active=-1;
  uint32_t last_seq=0;
  const char* fault="NONE";
  bool vm_ready=false;
  void begin() { hw.inhibit(); }
  void fail(const char* reason) {
    cancel(); if (!strcmp(fault,"NONE")) fault=reason;
  }
  // ADC uses 100k/10k from VM, 5V ADC reference. These are *rail* thresholds.
  void tick(uint16_t adc, bool permit, bool fault_pin_high, bool usb) {
    uint32_t now=hw.clock();
    if (!vm_ready) {
      if (!cold_seen) {
        if (adc<=5) { if (!low_tracking) { low_tracking=true; low_at=now; }
          if (elapsed(now,low_at)>=100) cold_seen=true;
        } else low_tracking=false;
      } else if (adc>=150) {
        if (!high_tracking) { high_tracking=true; high_at=now; }
        if (elapsed(now,high_at)>=100) vm_ready=true;
      } else high_tracking=false;
    } else if (adc<140) fail("VM_LOST");
    if ((armed || phase!=IDLE || active>=0) && !usb) fail("USB_LOST");
    if ((armed || phase!=IDLE || active>=0) &&
        (!hb_seen || elapsed(now,hb_at)>=500)) fail("HEARTBEAT_TIMEOUT");
    if (active>=0) {
      if (!permit) { fail("GATE_TIMEOUT"); return; }
      if (!fault_pin_high) { fail("DRIVER_FAULT"); return; }
      if (elapsed(now,pulse_at)>=pulse_ms) {
        uint8_t ch=uint8_t(active); uint32_t seq=pending_seq;
        const char* err=hw.finish(ch);
        hw.inhibit(); active=-1; cooled[ch]=true; off_at[ch]=hw.clock();
        if (err) { fail(err); return; }
        char b[48]; snprintf(b,sizeof(b),"DONE %lu %u",(unsigned long)seq,ch); hw.emit(b);
      }
      return;
    }
    if (phase==IDLE) return;
    if (strcmp(fault,"NONE")) return;
    if (elapsed(now,prepare_at)>=300) { reject_pending("GATE_TIMEOUT"); return; }
    if (phase==WAIT_LOW && !permit) { hw.trigger(); phase=WAIT_HIGH; phase_at=now; return; }
    if (phase==WAIT_HIGH) {
      if (permit) { hw.wake(); phase=WAKE; phase_at=now; }
      else if (elapsed(now,phase_at)>=5) reject_pending("GATE_MISSING");
      return;
    }
    if (phase==WAKE && elapsed(now,phase_at)>=1) {
      if (!permit) { reject_pending("GATE_TIMEOUT"); return; }
      const char* err=hw.configure();
      if (err) { reject_pending(err); return; }
      // A finite independent gate must have ample time left after configuration.
      if (elapsed(hw.clock(),phase_at)>40) { reject_pending("CONFIG_TOO_SLOW"); return; }
      if (pending_arm) {
        hw.inhibit(); phase=IDLE; armed=true; ok(pending_seq,"ARM");
      } else {
        pulse_at=hw.clock();
        err=hw.start(pending_channel,pending_positive);
        if (err) { reject_pending(err); return; }
        phase=IDLE; active=pending_channel; ok(pending_seq,"PULSE");
      }
    }
  }
  void command(char* line) {
    char* words[7]; uint8_t n=0; char* ctx=nullptr;
    for (char* p=strtok_r(line," ", &ctx); p; p=strtok_r(nullptr," ",&ctx)) {
      if (n==7) { fail("MALFORMED"); error(0,"MALFORMED"); return; } words[n++]=p;
    }
    if (n==1 && !strcmp(words[0],"HELLO")) { hw.emit("READY TC2 DRV8235_I2C"); return; }
    if (n==1 && !strcmp(words[0],"STATUS")) { status(); return; }
    uint32_t seq=0, ch=0, ms=0;
    bool stop=n>=1 && !strcmp(words[0],"STOP");
    // Even a malformed/stale STOP must inhibit before parsing anything else.
    if (stop) cancel();
    bool basic=n==2 && (!strcmp(words[0],"HB") || !strcmp(words[0],"ARM") || stop);
    bool pulse=n==5 && !strcmp(words[0],"PULSE");
    if ((!basic && !pulse) || !number(words[1],seq) || seq==0 ||
        (pulse && (!number(words[2],ch) || ch>3 ||
        (strcmp(words[3],"P") && strcmp(words[3],"N")) ||
        !number(words[4],ms) || ms<20 || ms>100))) {
      fail("MALFORMED"); error(0,"MALFORMED"); return;
    }
    if (seq<=last_seq) { error(seq,"STALE"); return; }
    last_seq=seq;
    if (stop) { ok(seq,"STOP"); return; }
    if (!strcmp(words[0],"HB")) { hb_seen=true; hb_at=hw.clock(); ok(seq,"HB"); return; }
    if (strcmp(fault,"NONE")) { error(seq,fault); return; }
    if (!hb_seen || elapsed(hw.clock(),hb_at)>=500) { error(seq,"HEARTBEAT_TIMEOUT"); return; }
    if (active>=0 || phase!=IDLE) { error(seq,"BUSY"); return; }
    if (!vm_ready) { error(seq,"VM_RESET_REQUIRED"); return; }
    if (pulse && !armed) { error(seq,"DISARMED"); return; }
    if (pulse && cooled[ch] && elapsed(hw.clock(),off_at[ch])<1000) { error(seq,"COOLDOWN"); return; }
    pending_arm=!pulse; pending_seq=seq; pending_channel=uint8_t(ch);
    pending_positive=pulse && !strcmp(words[3],"P"); pulse_ms=uint16_t(ms);
    phase=WAIT_LOW; prepare_at=hw.clock(); hw.inhibit();
  }
  void status() {
    char b[160]; long age=hb_seen?(long)elapsed(hw.clock(),hb_at):-1;
    snprintf(b,sizeof(b),"STATUS TC2 DRV8235_I2C armed=%u active=%d last_seq=%lu hb_age_ms=%ld fault=%s vm_ready=%u pending=%u",
      armed?1:0,active,(unsigned long)last_seq,age,fault,vm_ready?1:0,phase!=IDLE?1:0); hw.emit(b);
  }
  static uint32_t elapsed(uint32_t a,uint32_t b) { return a-b; }
 private:
  enum Phase { IDLE,WAIT_LOW,WAIT_HIGH,WAKE } phase=IDLE;
  Hardware& hw;
  bool hb_seen=false, cold_seen=false, low_tracking=false, high_tracking=false;
  uint32_t hb_at=0,low_at=0,high_at=0,prepare_at=0,phase_at=0,pulse_at=0,pending_seq=0;
  bool cooled[4]={false,false,false,false},pending_arm=false,pending_positive=false;
  uint32_t off_at[4]={0,0,0,0}; uint8_t pending_channel=0; uint16_t pulse_ms=0;
  void ok(uint32_t seq,const char* kind) { reply("OK",seq,kind); }
  void error(uint32_t seq,const char* reason) { reply("ERR",seq,reason); }
  void reply(const char* prefix,uint32_t seq,const char* text) {
    char b[80]; snprintf(b,sizeof(b),"%s %lu %s",prefix,(unsigned long)seq,text); hw.emit(b);
  }
  void cancel() {
    hw.inhibit(); if(active>=0) { cooled[active]=true; off_at[active]=hw.clock(); }
    active=-1; phase=IDLE; armed=false;
  }
  void reject_pending(const char* reason) { uint32_t s=pending_seq; fail(reason); error(s,reason); }
  static bool number(const char* s,uint32_t& value) {
    if (!s || !*s) return false;
    value=0;
    for (;*s;++s) { if (*s<'0'||*s>'9') return false;
      uint8_t d=uint8_t(*s-'0'); if(value>429496729UL || (value==429496729UL && d>5))return false;
      value=value*10+d;
    } return true;
  }
};
}
