import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Controller } from '../control.mjs';
test('時間差：境界未満は直進、境界以上は分岐', () => {
  for (const [elapsed, route] of [[2999, 'straight'], [3000, 'curve'], [5000, 'curve']]) {
    const c = new Controller('time'); c.sensorA(100); c.sensorB(100 + elapsed, 3000, 2000); assert.equal(c.route, route);
  }
});
test('LED：B検知時点の表示を保持', () => {
  for (const [elapsed, route] of [[1999, 'straight'], [2000, 'curve'], [4000, 'straight']]) {
    const c = new Controller('led'); c.sensorA(0); c.sensorB(elapsed, 3000, 2000); assert.equal(c.route, route);
    assert.equal(c.sensorB(99999, 3000, 2000), false); assert.equal(c.route, route);
  }
});
test('B単独・Aの二重検知を無視し、解除後に再利用可能', () => {
  const c = new Controller('time'); assert.equal(c.sensorB(1, 3000, 2000), false);
  c.sensorA(0); assert.equal(c.sensorA(2000), false); c.sensorB(2500, 3000, 2000);
  assert.equal(c.route, 'straight'); assert.equal(c.sensorA(3000), false);
  c.reset(); assert.equal(c.phase, 'idle'); assert.equal(c.route, null); assert.equal(c.sensorA(5000), true);
});
test('4組は独立して動作', () => {
  const all = ['time','time','led','led'].map(mode => new Controller(mode));
  all[0].sensorA(0); all[2].sensorA(0); all[2].sensorB(2500,3000,2000);
  assert.deepEqual(all.map(c => c.phase), ['waiting','idle','locked','idle']);
});
test('両方式：進路決定前はポイントを操作せず、解除後も前回位置を保持', () => {
  for (const mode of ['time', 'led']) {
    const c = new Controller(mode);
    assert.equal(c.point, null);
    c.sensorA(0);
    c.indication(2500, 2000);
    assert.equal(c.point, null);
    c.sensorB(2500, 2000, 2000);
    assert.equal(c.point, 'curve');
    c.reset();
    assert.equal(c.point, 'curve');
    c.sensorA(5000);
    c.indication(5001, 2000);
    assert.equal(c.point, 'curve');
    c.sensorB(5001, 2000, 2000);
    assert.equal(c.point, 'straight');
  }
});
