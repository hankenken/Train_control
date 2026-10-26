export class Controller {
  constructor(mode) { this.mode = mode; this.point = null; this.reset(); }
  reset() { this.phase = 'idle'; this.started = null; this.route = null; }
  indication(now, interval) {
    return Math.floor((now - this.started) / interval) % 2 === 0 ? 'straight' : 'curve';
  }
  sensorA(now) {
    if (this.phase !== 'idle') return false;
    this.started = now; this.phase = 'waiting'; return true;
  }
  sensorB(now, threshold, interval) {
    if (this.phase !== 'waiting') return false;
    this.route = this.mode === 'time'
      ? (now - this.started < threshold ? 'straight' : 'curve')
      : this.indication(now, interval);
    this.point = this.route;
    this.phase = 'locked'; return true;
  }
}
