import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SensorFilter } from '../hardware/sensor-filter.mjs';
const make = () => new SensorFilter({ empty: 900, roof: 200 });
const arm = f => { f.sample(900, 0); f.sample(900, 150); };
test('起動時の列車を検知イベントにしない', () => {
  const f = make(); assert.equal(f.sample(200, 0), null);
  assert.equal(f.sample(200, 1000), null); assert.equal(f.armed, false);
  f.sample(900, 1010); f.sample(900, 1160); assert.equal(f.armed, true);
});
test('安定検知は最初の時刻を返し、停車中は再検知しない', () => {
  const f = make(); arm(f); f.sample(200, 200);
  assert.equal(f.sample(200, 229), null);
  assert.deepEqual(f.sample(200, 230), { type: 'detected', timestamp: 200 });
  assert.equal(f.sample(200, 1000), null);
});
test('短いノイズを無視し、ヒステリシスと復帰待ちで状態保持', () => {
  const f = make(); arm(f); f.sample(200, 200); f.sample(900, 210);
  assert.equal(f.present, false);
  f.sample(200, 300); f.sample(200, 330);
  f.sample(900, 400); f.sample(550, 500); assert.equal(f.present, true);
  f.sample(900, 600); assert.equal(f.sample(900, 749), null);
  assert.deepEqual(f.sample(900, 750), { type: 'cleared', timestamp: 600 });
  f.sample(200, 800); assert.equal(f.sample(200, 830).type, 'detected');
});
test('反射で値が増えるセンサも扱う', () => {
  const f = new SensorFilter({ empty: 100, roof: 800 });
  f.sample(100, 0); f.sample(100, 150); f.sample(800, 200);
  assert.equal(f.sample(800, 230).type, 'detected');
});
test('校正不良を拒否し、異常入力時は空き確認からやり直す', () => {
  assert.throws(() => new SensorFilter({ empty: 500, roof: 520 }));
  assert.throws(() => new SensorFilter({ empty: null, roof: null }));
  const f = make(); arm(f); assert.throws(() => f.sample(NaN, 200));
  assert.equal(f.armed, false); assert.equal(f.sample(200, 210), null);
  f.sample(900, 220); assert.throws(() => f.sample(900, 219));
});
