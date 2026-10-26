import { Controller } from './control.mjs';
const names = ['1 外側・右方向', '1 内側・左方向', '2 外側・左方向', '2 内側・右方向'];
const controls = names.map((_, i) => new Controller(i < 2 ? 'time' : 'led'));
const routeName = r => r === 'straight' ? '直進' : '分岐';
const threshold = document.querySelector('#threshold');
const interval = document.querySelector('#interval');
const panels = document.querySelector('#panels');
panels.innerHTML = controls.map((c, i) => `<section class="panel" id="panel-${i}"><div class="section-title"><h2>${names[i]}</h2><span>${c.mode === 'time' ? '時間差方式' : 'LED選択方式'}</span></div><div class="status"></div><div class="lamps"><span class="straight">● 直</span><span class="curve">● 曲</span></div><p class="detail"></p><div class="buttons"><button data-id="${i}" data-action="a">センサA 通過</button><button data-id="${i}" data-action="b">センサB 通過</button><button data-id="${i}" data-action="clear">通過完了</button></div><p class="help">${c.mode === 'time' ? 'A通過からの経過時間で進路を選択します。' : 'Aで交互表示を開始。B通過時の点灯方向を選択します。'}</p></section>`).join('');
function settingsValid() { return [threshold, interval].every(x => x.checkValidity() && Number(x.value) > 0); }
function render() {
  const now = performance.now();
  controls.forEach((c, i) => {
    const el = document.querySelector(`#panel-${i}`);
    const active = c.route || (c.phase === 'waiting' && c.mode === 'led' ? c.indication(now, Number(interval.value) * 1000) : null);
    el.querySelector('.status').textContent = c.phase === 'idle' ? '待機中 / 信号：停止' : c.phase === 'waiting' ? '選択中 / 信号：停止' : `進路ロック / 模擬信号：${routeName(c.route)}進行`;
    el.querySelector('.detail').textContent = c.started === null ? 'Aの通過を待っています' : c.phase === 'locked' ? `ポイント：${routeName(c.route)}（模擬）` : `A通過から ${((now - c.started) / 1000).toFixed(1)} 秒`;
    ['straight', 'curve'].forEach(r => el.querySelector(`.${r}`).classList.toggle('lit', active === r));
    el.querySelector('[data-action="a"]').disabled = c.phase !== 'idle' || !settingsValid();
    el.querySelector('[data-action="b"]').disabled = c.phase !== 'waiting';
    el.querySelector('[data-action="clear"]').disabled = c.phase !== 'locked';
    document.querySelector(`#marker-${i}`).classList.toggle('selected', c.phase === 'locked');
  });
  threshold.disabled = interval.disabled = controls.some(c => c.phase !== 'idle');
}
panels.addEventListener('click', e => {
  const button = e.target.closest('button'); if (!button) return;
  const i = Number(button.dataset.id), c = controls[i], action = button.dataset.action;
  let message;
  if (action === 'a' && settingsValid() && c.sensorA(performance.now())) message = 'センサA検知';
  if (action === 'b' && c.sensorB(performance.now(), Number(threshold.value) * 1000, Number(interval.value) * 1000)) message = `センサB検知 → ${routeName(c.route)}でロック`;
  if (action === 'clear' && c.phase === 'locked') { c.reset(); message = '通過完了・ロック解除'; }
  if (message) {
    const li = document.createElement('li'); li.textContent = `${new Date().toLocaleTimeString('ja-JP')} ${names[i]}：${message}`;
    const log = document.querySelector('#events'); log.prepend(li); while (log.children.length > 40) log.lastChild.remove();
  }
  render();
});
setInterval(render, 100); render();
