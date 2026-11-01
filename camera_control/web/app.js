"use strict";

(() => {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const cameraCards = new Map();
  const laneCards = new Map();
  const modeNames = { demo: "デモ映像", replay: "録画の再生", pi: "Raspberry Piカメラ" };
  const phaseNames = { idle: "待機", waiting: "Bの判定待ち", locked: "進路確定・ロック中", uncertain: "判定保留" };
  const laneNames = { upper_outer: "上側・外線", upper_inner: "上側・内線", lower_outer: "下側・外線", lower_inner: "下側・内線", UP_OUT: "上側・外線", UP_IN: "上側・内線", LOW_OUT: "下側・外線", LOW_IN: "下側・内線" };
  let connected = false;
  let outputsDisabled = false;
  let paused = false;
  let pauseBusy = false;
  let firstStatus = true;

  const displayValue = (value) => value === null || value === undefined || value === "" ? "—" : String(value);
  const routeName = (route) => ({ straight: "直進", curve: "分岐", branch: "分岐", direct: "直進" }[route] || displayValue(route));
  function notice(message, error = false) {
    const el = $("#notice");
    el.textContent = message;
    el.classList.toggle("error", error);
    el.hidden = !message;
  }
  async function request(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(url, { cache: "no-store", ...options, signal: controller.signal });
      const raw = await response.text();
      let data = null;
      if (raw) {
        try { data = JSON.parse(raw); } catch { data = { detail: raw.slice(0, 300) }; }
      }
      if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}`);
      return data;
    } finally { clearTimeout(timer); }
  }
  const postJSON = (url, value) => request(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
  function syncButtons() {
    $("#pause-button").disabled = !connected || !outputsDisabled || pauseBusy;
    $("#pause-button").textContent = paused ? "検出を再開" : "検出を一時停止";
    for (const card of cameraCards.values()) card.button.disabled = !connected || !outputsDisabled || !card.present || !card.confirm.checked || card.busy;
    for (const card of laneCards.values()) card.button.disabled = !connected || !outputsDisabled || !["locked", "uncertain"].includes(card.phase) || !card.confirm.checked || card.busy;
  }
  function setConnection(ok) {
    if (connected && !ok) {
      for (const card of cameraCards.values()) card.confirm.checked = false;
      for (const card of laneCards.values()) card.confirm.checked = false;
    }
    connected = ok;
    document.body.classList.toggle("connection-lost", !ok);
    $("#connection-label").textContent = ok ? "接続済み · 約1秒ごとに更新" : "接続できません · 自動で再試行します";
    $("#connection-dot").className = `status-dot ${ok ? "online" : "offline"}`;
    syncButtons();
  }
  function attachPreview(card) {
    card.previewState.textContent = "映像へ接続中";
    card.previewState.hidden = false;
    card.img.src = `/api/preview/${encodeURIComponent(card.id)}.mjpg?session=${Date.now()}`;
  }
  function ensureCamera(camera) {
    const id = String(camera.id);
    if (cameraCards.has(id)) return cameraCards.get(id);
    const node = $("#camera-template").content.firstElementChild.cloneNode(true);
    const card = { node, id, img: $("img", node), previewState: $(".preview-state", node), confirm: $(".empty-confirm", node), button: $(".background-button", node), busy: false, present: true };
    $("h3", node).textContent = camera.name || id;
    card.img.alt = `${camera.name || id}の映像`;
    card.img.addEventListener("load", () => { card.previewState.hidden = true; });
    card.img.addEventListener("error", () => { card.previewState.textContent = "映像未取得 · 必要なら「映像を再接続」"; card.previewState.hidden = false; });
    card.confirm.addEventListener("change", syncButtons);
    card.button.addEventListener("click", async () => {
      if (card.button.disabled || !card.confirm.checked) return;
      card.busy = true; syncButtons();
      try {
        await request(`/api/background/${encodeURIComponent(id)}`, { method: "POST" });
        card.confirm.checked = false;
        notice(`${camera.name || id}の背景登録を要求しました。状態表示と映像を確認してください。`);
      } catch (error) { notice(`背景を登録できませんでした：${error.message}`, true); }
      finally { card.busy = false; syncButtons(); }
    });
    $("#cameras").append(node); cameraCards.set(id, card); attachPreview(card);
    return card;
  }
  function milliseconds(value) {
    return typeof value === "number" && Number.isFinite(value) ? `${Math.max(0, value).toFixed(1)} ms` : "—";
  }
  function relativeTime(timestamp, now) {
    if (typeof timestamp !== "number" || !Number.isFinite(timestamp) || typeof now !== "number" || !Number.isFinite(now)) return "時刻確認中";
    const seconds = Math.max(0, now - timestamp);
    if (seconds < 60) return `${seconds.toFixed(1)}秒前`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}分${Math.floor(seconds % 60)}秒前`;
  }
  function renderCameras(cameras) {
    const present = new Set(cameras.map((camera) => String(camera.id)));
    for (const card of cameraCards.values()) {
      card.present = present.has(card.id);
      if (!card.present) {
        $(".camera-error", card.node).textContent = "このカメラの状態が取得できていません。";
        $(".camera-error", card.node).hidden = false;
        card.confirm.checked = false;
      }
    }
    for (const camera of cameras) {
      const card = ensureCamera(camera); card.present = true;
      $("h3", card.node).textContent = camera.name || card.id;
      const badge = $(".calibration-state", card.node);
      badge.textContent = camera.calibrated ? "背景登録済み" : "背景未登録";
      badge.className = `calibration-state badge ${camera.calibrated ? "good" : "warning"}`;
      $(".camera-meta", card.node).textContent = `取得 ${displayValue(camera.frames)} フレーム ／ 取得→処理 ${milliseconds(camera.metrics?.capture_age_ms)} ／ 処理 ${milliseconds(camera.metrics?.processing_ms)}`;
      $(".camera-error", card.node).textContent = camera.error ? displayValue(camera.error) : "";
      $(".camera-error", card.node).hidden = !camera.error;
    }
  }
  function ensureLane(lane) {
    const id = String(lane.id);
    if (laneCards.has(id)) return laneCards.get(id);
    const node = $("#lane-template").content.firstElementChild.cloneNode(true);
    const card = { node, id, confirm: $(".clear-confirm", node), button: $(".release-button", node), phase: "", clearToken: "", busy: false };
    $("h3", node).textContent = lane.name || laneNames[id] || id;
    card.confirm.addEventListener("change", syncButtons);
    card.button.addEventListener("click", async () => {
      if (card.button.disabled || !card.confirm.checked) return;
      card.busy = true; syncButtons();
      try {
        await postJSON(`/api/release/${encodeURIComponent(id)}`, { confirm_clear: true });
        card.confirm.checked = false;
        notice(`${lane.name || laneNames[id] || id}の通過完了を記録しました。実機出力はありません。`);
      } catch (error) { notice(`解除できませんでした：${error.message}`, true); }
      finally { card.busy = false; syncButtons(); }
    });
    $("#lanes").append(node); laneCards.set(id, card);
    return card;
  }
  function renderLanes(lanes) {
    $("#lanes-empty").hidden = lanes.length > 0;
    const present = new Set(lanes.map((lane) => String(lane.id)));
    for (const card of laneCards.values()) {
      card.node.hidden = !present.has(card.id);
      if (card.node.hidden) { card.phase = ""; card.confirm.checked = false; }
    }
    for (const lane of lanes) {
      const card = ensureLane(lane);
      const phase = lane.phase || lane.state || "";
      const token = JSON.stringify([phase, lane.track_id ?? null, lane.last_requested_route ?? lane.route ?? null]);
      if (token !== card.clearToken) { card.confirm.checked = false; card.clearToken = token; }
      card.phase = phase;
      const badge = $(".lane-phase", card.node);
      badge.textContent = phaseNames[phase] || "状態未確認";
      badge.className = `lane-phase badge ${phase === "uncertain" ? "warning" : phase === "locked" ? "locked" : ""}`;
      $(".lane-track", card.node).textContent = displayValue(lane.track_id);
      $(".lane-route", card.node).textContent = routeName(lane.route ?? lane.last_requested_route);
      $(".lane-indication", card.node).textContent = routeName(lane.indication ?? lane.led_route);
      const reason = lane.reason || lane.uncertainty_reason;
      $(".lane-reason", card.node).textContent = reason || "";
      $(".lane-reason", card.node).hidden = !reason;
    }
  }
  function renderTracks(tracks) {
    const list = $("#tracks"); list.replaceChildren();
    if (!tracks.length) { const p = document.createElement("p"); p.className = "empty-state"; p.textContent = "現在追跡している車両はありません。"; list.append(p); return; }
    for (const track of tracks) {
      const row = document.createElement("div"); row.className = `track-row ${track.ambiguous ? "ambiguous" : ""}`;
      const center = Array.isArray(track.center) ? track.center.map((n) => typeof n === "number" ? n.toFixed(1) : n).join(", ") : displayValue(track.center);
      row.textContent = `ID ${displayValue(track.id)} · ${laneNames[track.lane] || displayValue(track.lane)} · 中心 (${center}) · ${track.ambiguous ? "対応が不確か" : track.visible ? "検出中" : "一時的に見失い"}`;
      list.append(row);
    }
  }
  function renderEvents(events, now) {
    const list = $("#events"); list.replaceChildren();
    if (!events.length) { const li = document.createElement("li"); li.className = "empty-state"; li.textContent = "記録はありません。"; list.append(li); return; }
    // The API supplies newest first. Sort numeric capture timestamps to keep
    // that order explicit, without exposing boot-time timestamps to the user.
    const ordered = events.slice().sort((a, b) => {
      const at = a && typeof a === "object" ? a.timestamp : null;
      const bt = b && typeof b === "object" ? b.timestamp : null;
      return typeof at === "number" && Number.isFinite(at) && typeof bt === "number" && Number.isFinite(bt) ? bt - at : 0;
    }).slice(0, 30);
    for (const event of ordered) {
      const li = document.createElement("li");
      if (typeof event === "string") { li.textContent = event; list.append(li); continue; }
      const kind = event.kind ?? event.type ?? event.event;
      const label = ({ gate: "仮想線を通過", decision: "進路要求（模擬）", route_requested: "進路要求（模擬）", background_set: "背景を登録", manual_release: "手動でロック解除", pause: event.paused ? "検出を一時停止" : "検出を再開" })[kind] || displayValue(kind);
      const details = [relativeTime(event.timestamp ?? event.time, now), event.message || label, laneNames[event.lane] || event.lane, event.camera, event.gate ? `${event.gate}線` : null, event.track_id != null ? `ID ${event.track_id}` : null, event.route ? routeName(event.route) : null, typeof event.elapsed_s === "number" ? `A→B ${event.elapsed_s.toFixed(2)}秒` : null, event.reason].filter((v) => v !== null && v !== undefined && v !== "");
      li.textContent = details.join(" · ");
      list.append(li);
    }
  }
  function renderWarnings(warnings) {
    const node = $("#warnings"); node.replaceChildren(); node.hidden = warnings.length === 0;
    if (!warnings.length) return;
    const ul = document.createElement("ul");
    for (const warning of warnings) { const li = document.createElement("li"); li.textContent = typeof warning === "string" ? warning : warning.message || JSON.stringify(warning); ul.append(li); }
    node.append(ul);
  }
  async function poll() {
    try {
      const status = await request("/api/status");
      if (!status || typeof status !== "object") throw new Error("状態の形式が正しくありません");
      outputsDisabled = status.outputs_enabled === false;
      paused = typeof status.paused === "boolean" ? status.paused : status.running === false;
      $("#mode-label").textContent = modeNames[status.mode] || `モード：${displayValue(status.mode)}`;
      $("#running-label").textContent = paused ? "検出を一時停止中" : status.running ? "検出中" : "検出停止中";
      renderCameras(Array.isArray(status.cameras) ? status.cameras : []);
      renderLanes(Array.isArray(status.routes?.lanes) ? status.routes.lanes : []);
      renderTracks(Array.isArray(status.tracks) ? status.tracks : []);
      renderEvents(Array.isArray(status.events) ? status.events : [], status.clock_now);
      renderWarnings(Array.isArray(status.warnings) ? status.warnings : []);
      if (!outputsDisabled) notice("出力無効の状態を確認できません。操作を中止してサーバーの設定を確認してください。", true);
      else if (!connected && !firstStatus) notice("サーバーへ再接続しました。映像が更新されない場合は「映像を再接続」を押してください。");
      firstStatus = false; setConnection(true);
    } catch (error) {
      setConnection(false); $("#running-label").textContent = "状態未取得";
      if (firstStatus) notice(`状態を取得できません：${error.message}`, true);
    } finally { setTimeout(poll, 1000); }
  }
  $("#pause-button").addEventListener("click", async () => {
    if ($("#pause-button").disabled) return;
    pauseBusy = true; syncButtons();
    const desiredPause = !paused;
    try { await postJSON("/api/pause", { paused: desiredPause }); paused = desiredPause; notice(paused ? "検出の一時停止を要求しました。" : "検出の再開を要求しました。"); }
    catch (error) { notice(`変更できませんでした：${error.message}`, true); }
    finally { pauseBusy = false; syncButtons(); }
  });
  $("#retry-previews").addEventListener("click", () => { for (const card of cameraCards.values()) attachPreview(card); });
  $("#load-config").addEventListener("click", async () => {
    const button = $("#load-config"); button.disabled = true;
    try { $("#config-content").textContent = JSON.stringify(await request("/api/config"), null, 2); }
    catch (error) { $("#config-content").textContent = `設定を取得できません：${error.message}`; }
    finally { button.disabled = false; }
  });
  ensureCamera({ id: "cam0", name: "カメラ0" });
  ensureCamera({ id: "cam1", name: "カメラ1" });
  poll();
})();
