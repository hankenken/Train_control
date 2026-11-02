// Prototype for LattePanda 3 Delta onboard Leonardo. NOT hardware validated.
#include <Wire.h>
#include <avr/wdt.h>
#include "tc2_core.h"

constexpr uint8_t SLEEP_REQUEST=4, GATE_TRIGGER=5, GATE_SENSE=6, NFAULT=7;
constexpr uint8_t ADDR[4]={0x30,0x32,0x36,0x38};
// 256-byte nonblocking USB transmit ring; overflow inhibits instead of waiting.
char tx[256]; uint8_t tx_head=0,tx_tail=0; bool tx_fault=false;
class Board: public tc2::Hardware {
 public:
  uint32_t clock() override { return millis(); }
  void inhibit() override { digitalWrite(SLEEP_REQUEST,LOW); }
  void trigger() override { digitalWrite(GATE_TRIGGER,HIGH); delayMicroseconds(10); digitalWrite(GATE_TRIGGER,LOW); }
  void wake() override { digitalWrite(SLEEP_REQUEST,HIGH); }
  void emit(const char* s) override {
    for (;;) { char c=*s?*s++:'\n'; uint8_t next=uint8_t(tx_head+1);
      if (next==tx_tail) { tx_fault=true; inhibit(); return; }
      tx[tx_head]=c; tx_head=next; if(c=='\n')return;
    }
  }
  const char* configure() override {
    // Explicit safe settings, reserved bits zero, all writes EN_OUT=0.
    for (uint8_t i=0;i<4;++i) {
      uint8_t f;
      if(!read(i,0x09,f))return "I2C_FAULT";
      if(f&0x80)return "UNEXPECTED_ENABLED"; // Never clear stale live drive and continue.
      if(!write(i,0x09,0x40) || !write(i,0x0C,0xB0) ||
         !write(i,0x0D,0x3C) || !write(i,0x0E,0x07))return "I2C_FAULT";
      const uint8_t regs[]={0x09,0x0C,0x0D,0x0E};
      const uint8_t vals[]={0x40,0xB0,0x3C,0x07};
      for(uint8_t k=0;k<4;++k) {
        if(!read(i,regs[k],f))return "I2C_FAULT";
        if(f!=vals[k])return "CONFIG_MISMATCH";
      }
      if(!read(i,0x00,f))return "I2C_FAULT";
      if(f&0xBC)return "DRIVER_FAULT";
      if(!digitalRead(GATE_SENSE))return "GATE_TIMEOUT";
    }
    return digitalRead(NFAULT)?nullptr:"DRIVER_FAULT";
  }
  const char* start(uint8_t ch,bool positive) override {
    uint8_t value=positive?0x3E:0x3D,f;
    if(!write(ch,0x0D,value)||!read(ch,0x0D,f))return "I2C_FAULT";
    if(f!=value)return "CONFIG_MISMATCH";
    if(!digitalRead(GATE_SENSE)||!digitalRead(NFAULT))return "GATE_TIMEOUT";
    if(!write(ch,0x09,0xC0)||!read(ch,0x09,f))return "I2C_FAULT";
    return f==0xC0?nullptr:"CONFIG_MISMATCH";
  }
  const char* finish(uint8_t ch) override {
    uint8_t f;
    if(!write(ch,0x09,0x40)||!read(ch,0x09,f))return "I2C_FAULT";
    if(f!=0x40)return "CONFIG_MISMATCH";
    if(!write(ch,0x0D,0x3C)||!read(ch,0x0D,f))return "I2C_FAULT";
    return f==0x3C?nullptr:"CONFIG_MISMATCH";
  }
 private:
  bool write(uint8_t ch,uint8_t reg,uint8_t value) {
    Wire.clearWireTimeoutFlag(); Wire.beginTransmission(ADDR[ch]); Wire.write(reg); Wire.write(value);
    uint8_t e=Wire.endTransmission(); return !e&&!Wire.getWireTimeoutFlag();
  }
  bool read(uint8_t ch,uint8_t reg,uint8_t& value) {
    Wire.clearWireTimeoutFlag(); Wire.beginTransmission(ADDR[ch]); Wire.write(reg);
    if(Wire.endTransmission(false)||Wire.getWireTimeoutFlag())return false;
    if(Wire.requestFrom(ADDR[ch],uint8_t(1))!=1||Wire.getWireTimeoutFlag())return false;
    value=Wire.read(); return true;
  }
} board;
tc2::Controller controller(board);
char line[64]; uint8_t used=0; bool overflow=false;
void setup() {
  MCUSR=0; wdt_disable();
  digitalWrite(SLEEP_REQUEST,LOW); pinMode(SLEEP_REQUEST,OUTPUT);
  digitalWrite(GATE_TRIGGER,LOW); pinMode(GATE_TRIGGER,OUTPUT);
  pinMode(GATE_SENSE,INPUT); pinMode(NFAULT,INPUT); // External 10k resistors required.
  analogReference(DEFAULT); controller.begin();
  Wire.begin(); Wire.setClock(100000); Wire.setWireTimeout(2000,true);
  Serial.begin(115200); // Do not wait for USB/Serial.
  wdt_enable(WDTO_60MS);
}
void loop() {
  wdt_reset();
  // AVR core 1.8.6 Serial::operator bool() contains delay(10); do not use it.
  bool connected=Serial.dtr();
  controller.tick(analogRead(A0),digitalRead(GATE_SENSE),digitalRead(NFAULT),connected);
  if(tx_fault)controller.fail("SERIAL_TX");
  if(!connected) {
    used=0; overflow=false; tx_head=tx_tail=0;
    for(uint8_t i=0;i<16 && Serial.available();++i)Serial.read();
    return;
  }
  // Bound work per loop so line flooding cannot starve the pulse deadline.
  for(uint8_t i=0;i<16 && Serial.available();++i) {
    char c=Serial.read();
    if(c=='\n') {
      if(overflow) { controller.fail("LINE_TOO_LONG"); board.emit("ERR 0 LINE_TOO_LONG"); }
      else { if(used && line[used-1]=='\r')--used; line[used]=0; controller.command(line); }
      used=0; overflow=false;
    } else if(!overflow) {
      if(c=='\0' || (uint8_t(c)<32 && c!='\r') || uint8_t(c)>126) {
        controller.fail("MALFORMED"); overflow=true;
      } else if(used<63)line[used++]=c;
      else { controller.fail("LINE_TOO_LONG"); overflow=true; }
    }
  }
  for(uint8_t i=0;i<16 && tx_tail!=tx_head && Serial.dtr() && Serial.availableForWrite();++i) {
    Serial.write(tx[tx_tail]); ++tx_tail;
  }
}
