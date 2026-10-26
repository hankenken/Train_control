// Hardware-independent filter. No GPIO, SPI or output actuation.
export class SensorFilter {
  constructor({ empty, roof, on = 0.60, off = 0.35, onMs = 30, offMs = 150, minContrast = 100 }) {
    if (![empty, roof, on, off, onMs, offMs, minContrast].every(Number.isFinite)
      || empty < 0 || empty > 1023 || roof < 0 || roof > 1023
      || minContrast <= 0 || Math.abs(roof - empty) < minContrast
      || off < 0 || on > 1 || off >= on || onMs < 0 || offMs < 0) {
      throw new Error('Invalid sensor calibration or filter settings');
    }
    Object.assign(this, { empty, roof, on, off, onMs, offMs });
    this.reset();
  }
  reset() {
    this.armed = false; this.present = false; this.candidate = null;
    this.since = null; this.lastTime = null;
  }
  sample(raw, now) {
    if (!Number.isFinite(raw) || raw < 0 || raw > 1023 || !Number.isFinite(now)
      || (this.lastTime !== null && now < this.lastTime)) {
      this.reset(); throw new Error('Invalid sensor sample or timestamp');
    }
    this.lastTime = now;
    const value = (raw - this.empty) / (this.roof - this.empty);
    const next = value >= this.on ? true : value <= this.off ? false : null;
    // Startup must first see a stable clear track; never synthesize a train event.
    if (!this.armed && next !== false) {
      this.candidate = null; this.since = null; return null;
    }
    if (next === null || (this.armed && next === this.present)) {
      this.candidate = null; this.since = null; return null;
    }
    if (next !== this.candidate) { this.candidate = next; this.since = now; }
    if (now - this.since < (next ? this.onMs : this.offMs)) return null;
    const timestamp = this.since;
    this.candidate = null; this.since = null;
    if (!this.armed) { this.armed = true; return null; }
    this.present = next;
    return { type: next ? 'detected' : 'cleared', timestamp };
  }
}
