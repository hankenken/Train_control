"use strict";

(() => {
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const cameraCards = new Map();
  const laneCards = new Map();
  const modeNames = { demo: "デモ映像", replay: "録画の再生", pi: "Raspberry Piカメラ", usb: "USBカメラ・実映像" };
  const phaseNames = { idle: "待機", waiting: "Bの判定待ち", locked: "進路確定・ロック中", uncertain: "判定保留" };
  const laneNames = { upper_outer: "上側・外線", upper_inner: "上側・内線", lower_outer: "下側・外線", lower_inner: "下側・内線", UP_OUT: "上側・外線", UP_IN: "上側・内線", LOW_OUT: "下側・外線", LOW_IN: "下側・内線" };
  let connected = false;
  let outputsDisabled = false;
  let paused = false;
  let pauseBusy = false;
  let firstStatus = true;
  const editor = { camera: null, points: [], ready: false, busy: false, config: null };
  const localClock = () => typeof performance !== "undefined" ? performance.now() : Date.now();
  let liveStatus = null, receivedAt = 0;
  const STATUS_INTERVAL_MS=250;

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
    for (const card of cameraCards.values()) {
      card.button.disabled = !connected || !outputsDisabled || !card.present || !card.configured || !card.confirm.checked || card.busy;
      card.edit.disabled = !connected || !outputsDisabled || !card.present || card.busy;
    }
    for (const card of laneCards.values()) card.button.disabled = !connected || !outputsDisabled || !["locked", "uncertain"].includes(card.phase) || !card.confirm.checked || card.busy;
  }
  function setConnection(ok) {
    if (connected && !ok) {
      for (const card of cameraCards.values()) card.confirm.checked = false;
      for (const card of laneCards.values()) card.confirm.checked = false;
    }
    connected = ok;
    document.body.classList.toggle("connection-lost", !ok);
    $("#connection-label").textContent = ok ? "接続済み · 約0.25秒ごとに更新" : "接続できません · 自動で再試行します";
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
    card.edit = $(".calibration-button", node);
    card.edit.addEventListener("click", () => openEditor(id));
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
    $("#cameras").classList.toggle("single-camera",cameras.length===1);
    const present = new Set(cameras.map((camera) => String(camera.id)));
    for (const card of cameraCards.values()) {
      card.present = present.has(card.id);
      if (!card.present) {
        card.node.hidden = true;
        $(".camera-error", card.node).textContent = "このカメラの状態が取得できていません。";
        $(".camera-error", card.node).hidden = false;
        card.confirm.checked = false;
      }
    }
    for (const camera of cameras) {
      const card = ensureCamera(camera); card.present = true; card.node.hidden = false;
      card.configured = camera.lanes_configured > 0;
      if (camera.frame_size) $(".preview-frame",card.node).style.aspectRatio = `${camera.frame_size[0]} / ${camera.frame_size[1]}`;
      $("h3", card.node).textContent = camera.name || card.id;
      const badge = $(".calibration-state", card.node);
      badge.textContent = camera.calibrated ? "背景登録済み" : "背景未登録";
      badge.className = `calibration-state badge ${camera.calibrated ? "good" : "warning"}`;
      $(".camera-meta", card.node).textContent = `範囲 ${camera.lanes_configured || 0}件 ／ 取得 ${displayValue(camera.frames)} フレーム・${displayValue(camera.observed_read_fps)} fps ／ 取得→処理 ${milliseconds(camera.metrics?.capture_age_ms)} ／ 処理 ${milliseconds(camera.metrics?.processing_ms)}`;
      $(".camera-error", card.node).textContent = camera.error ? displayValue(camera.error) : "";
      $(".camera-error", card.node).hidden = !camera.error;
    }
  }
  function ensureLane(lane) {
    const id = String(lane.id);
    if (laneCards.has(id)) return laneCards.get(id);
    const node = $("#lane-template").content.firstElementChild.cloneNode(true);
    const card = { node, id, confirm: $(".clear-confirm", node), button: $(".release-button", node), phase: "", clearToken: "", busy: false };
    $("h3", node).textContent = lane.name || laneNames[id] || (id === "test_lane" ? "検証する線区" : id);
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
      $(".lane-mode",card.node).textContent = lane.mode === "led" ? `LED方式・${lane.led_interval_s}秒ごとに直／曲` : `時間差方式・${lane.time_threshold_s}秒未満＝直、以上＝曲`;
      const point = $(".point-output",card.node);
      point.classList.toggle("straight",lane.last_requested_route === "straight");
      point.classList.toggle("curve",lane.last_requested_route === "curve");
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
      row.textContent = `ID ${displayValue(track.id)} · ${laneNames[track.lane] || displayValue(track.lane)} · 面積 ${displayValue(track.area)}画素 · 中心 (${center}) · ${track.ambiguous ? "対応が不確か" : track.visible ? "検出中" : "一時的に見失い"}`;
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
      liveStatus=status;receivedAt=localClock();
      outputsDisabled = status.outputs_enabled === false;
      paused = typeof status.paused === "boolean" ? status.paused : status.running === false;
      $("#mode-label").textContent = modeNames[status.mode] || `モード：${displayValue(status.mode)}`;
      $("#running-label").textContent = paused ? "検出を一時停止中" : status.running ? "検出中" : "検出停止中";
      renderCameras(Array.isArray(status.cameras) ? status.cameras : []);
      renderLanes(Array.isArray(status.routes?.lanes) ? status.routes.lanes : []);
      const lastRequest = status.routes?.requests?.at(-1);
      if (lastRequest) $("#mock-output").textContent = `模擬出力 #${lastRequest.request_id}：${laneNames[lastRequest.lane] || (lastRequest.lane === "test_lane" ? "検証線区" : lastRequest.lane)} → ${routeName(lastRequest.route)} ／ A→B ${lastRequest.elapsed_s.toFixed(2)}秒 ／ ${relativeTime(lastRequest.timestamp,status.clock_now)}。実機出力はありません。`;
      renderTracks(Array.isArray(status.tracks) ? status.tracks : []);
      renderEvents(Array.isArray(status.events) ? status.events : [], status.clock_now);
      renderWarnings(Array.isArray(status.warnings) ? status.warnings : []);
      if (!outputsDisabled) notice("出力無効の状態を確認できません。操作を中止してサーバーの設定を確認してください。", true);
      else if (!connected && !firstStatus) notice("サーバーへ再接続しました。映像が更新されない場合は「映像を再接続」を押してください。");
      firstStatus = false; setConnection(true);
    } catch (error) {
      setConnection(false); $("#running-label").textContent = "状態未取得";
      if (firstStatus) notice(`状態を取得できません：${error.message}`, true);
    } finally { setTimeout(poll, STATUS_INTERVAL_MS); }
  }
  $("#pause-button").addEventListener("click", async () => {
    if ($("#pause-button").disabled) return;
    pauseBusy = true; syncButtons();
    const desiredPause = !paused;
    try { await postJSON("/api/pause", { paused: desiredPause }); paused = desiredPause; notice(paused ? "検出の一時停止を要求しました。" : "検出の再開を要求しました。"); }
    catch (error) { notice(`変更できませんでした：${error.message}`, true); }
    finally { pauseBusy = false; syncButtons(); }
  });
  $("#retry-previews").addEventListener("click", () => { for (const card of cameraCards.values()) if(card.present)attachPreview(card); });

  function drawEditor() {
    const canvas = $("#calibration-canvas"), ctx = canvas.getContext("2d");
    const w=canvas.width,h=canvas.height,pts=editor.points.map(p=>[p[0]*w,p[1]*h]);
    ctx.clearRect(0,0,w,h);ctx.lineWidth=Math.max(2,w/250);ctx.font=`bold ${Math.max(13,w/35)}px sans-serif`;
    if (pts.length >= 2) {
      const x=Math.min(pts[0][0],pts[1][0]),y=Math.min(pts[0][1],pts[1][1]),rw=Math.abs(pts[1][0]-pts[0][0]),rh=Math.abs(pts[1][1]-pts[0][1]);
      ctx.strokeStyle="#40ef9c";ctx.fillStyle="#40ef9c22";ctx.fillRect(x,y,rw,rh);ctx.strokeRect(x,y,rw,rh);
      if (pts.length === 4) {
        ctx.save();ctx.beginPath();ctx.rect(x,y,rw,rh);ctx.clip();
        const dx=pts[3][0]-pts[2][0],dy=pts[3][1]-pts[2][1],len=Math.hypot(dx,dy)||1;
        [2,3].forEach(i=>{ctx.strokeStyle=i===2?"#ffe240":"#65bbff";ctx.beginPath();ctx.moveTo(pts[i][0]+dy/len*w*2,pts[i][1]-dx/len*w*2);ctx.lineTo(pts[i][0]-dy/len*w*2,pts[i][1]+dx/len*w*2);ctx.stroke();});ctx.restore();
      }
    }
    pts.forEach((p,i)=>{ctx.fillStyle=i<2?"#40ef9c":i===2?"#ffe240":"#65bbff";ctx.beginPath();ctx.arc(p[0],p[1],Math.max(4,w/120),0,2*Math.PI);ctx.fill();ctx.fillText(["範囲1","範囲2","A","B"][i],p[0]+8,p[1]-8);});
    $("#calibration-step").textContent=["1/4：検出範囲の角をクリック","2/4：範囲の反対側の角をクリック（線路1本を囲む）","3/4：範囲内のA位置をクリック","4/4：範囲内のB位置をクリック（A→Bが進行方向）","4点選択済み。方式と時間を確認し、「適用して背景登録へ」を押してください。"][pts.length];
    $("#calibration-save").disabled = pts.length !== 4 || !editor.ready || editor.busy;
  }
  function editorSettings() {
    const lane=editor.config?.routes.lanes.find(l=>l.id===$("#calibration-lane").value);
    if(!lane)return;
    $("#calibration-mode").value=lane.mode;
    $("#calibration-time").value=lane.time_threshold_s || 2;
    $("#calibration-interval").value=lane.led_interval_s || 2;
  }
  async function openEditor(camera) {
    try {
      editor.config=await request("/api/config"); editor.camera=camera;editor.points=[];editor.ready=false;
      const select=$("#calibration-lane");select.replaceChildren();
      for(const lane of editor.config.routes.lanes) { const option=document.createElement("option");option.value=lane.id;option.textContent=laneNames[lane.id] || (lane.id === "test_lane" ? "検証する線区" : lane.id);select.append(option); }
      const assigned=editor.config.vision.lanes.find(l=>l.camera===camera);
      if(assigned)select.value=assigned.id;
      editorSettings();
      $("#calibration-threshold").value=editor.config.vision.threshold ?? 25;
      $("#calibration-area").value=editor.config.vision.min_area ?? 30;
      $("#calibration-distance").value=editor.config.vision.max_match_distance ?? 80;
      // Fetch reports a clear error instead of silently leaving a broken image.
      const response=await fetch(`/api/snapshot/${encodeURIComponent(camera)}.jpg?at=${Date.now()}`,{cache:"no-store"});
      if(!response.ok) {const data=await response.json();throw new Error(data.detail || "映像を取得できません");}
      const blob=await response.blob(), url=URL.createObjectURL(blob), img=$("#calibration-image");
      img.onload=()=>{URL.revokeObjectURL(url);const cv=$("#calibration-canvas");cv.width=img.naturalWidth;cv.height=img.naturalHeight;$(".calibration-frame").style.aspectRatio=`${cv.width} / ${cv.height}`;editor.ready=true;drawEditor();};
      img.src=url;$("#calibration-panel").hidden=false;drawEditor();$("#calibration-panel").scrollIntoView({behavior:"smooth",block:"start"});
    } catch(error) {notice(`設定画像を開けません：${error.message}`,true);}
  }
  $("#calibration-lane").addEventListener("change",editorSettings);
  $("#calibration-canvas").addEventListener("click",event=>{
    if(!editor.ready || editor.busy || editor.points.length>=4)return;
    const r=event.currentTarget.getBoundingClientRect();
    editor.points.push([Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))]);drawEditor();
  });
  $("#calibration-undo").addEventListener("click",()=>{if(!editor.busy){editor.points.pop();drawEditor();}});
  $("#calibration-reset").addEventListener("click",()=>{if(!editor.busy){editor.points=[];drawEditor();}});
  $("#calibration-close").addEventListener("click",()=>{$("#calibration-panel").hidden=true;});
  $("#calibration-save").addEventListener("click",async()=>{
    if(editor.points.length!==4 || editor.busy)return;
    editor.busy=true;drawEditor();
    try {
      await postJSON("/api/calibration",{camera:editor.camera,lane:$("#calibration-lane").value,roi:editor.points.slice(0,2),a:editor.points[2],b:editor.points[3],mode:$("#calibration-mode").value,time_threshold_s:Number($("#calibration-time").value),led_interval_s:Number($("#calibration-interval").value),threshold:Number($("#calibration-threshold").value),min_area:Number($("#calibration-area").value),max_match_distance:Number($("#calibration-distance").value)});
      $("#calibration-panel").hidden=true;
      const card=cameraCards.get(editor.camera);if(card){card.confirm.checked=false;card.node.scrollIntoView({behavior:"smooth",block:"center"});}
      notice("範囲・A/Bを適用しました。車両を取り除き、確認チェックを入れて「空の背景を登録」を押してください。次回用の設定はページ下部の「設定を保存」で保存できます。");
    } catch(error){notice(`設定できません：${error.message}`,true);}
    finally {editor.busy=false;drawEditor();}
  });
  function animateLEDs() {
    if(connected && liveStatus) {
      const now=liveStatus.clock_now+(localClock()-receivedAt)/1000;
      for(const lane of liveStatus.routes?.lanes || []) {
        const card=laneCards.get(String(lane.id));if(!card)continue;
        let direction=null;
        if(!paused && lane.mode==="led" && lane.state==="waiting" && Number.isFinite(lane.a_timestamp)) {
          const elapsed=Math.max(0,now-lane.a_timestamp),interval=lane.led_interval_s;
          direction=elapsed%(2*interval)<interval?"straight":"curve";
          $(".lane-indication",card.node).textContent=routeName(direction);
        }
        $(".led-straight",card.node).classList.toggle("lit",direction==="straight");
        $(".led-curve",card.node).classList.toggle("lit",direction==="curve");
      }
    }
    setTimeout(animateLEDs,100);
  }
  animateLEDs();
  $("#load-config").addEventListener("click", async () => {
    const button = $("#load-config"); button.disabled = true;
    try { $("#config-content").textContent = JSON.stringify(await request("/api/config"), null, 2); }
    catch (error) { $("#config-content").textContent = `設定を取得できません：${error.message}`; }
    finally { button.disabled = false; }
  });
  poll();
})();
