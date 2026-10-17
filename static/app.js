const $ = id => document.getElementById(id), CHUNK = 4, SR = 16000;
const COLOR = {low: "var(--safe)", medium: "var(--mid)", high: "var(--bad)"};
let lastWav = null, sid = null, stream, ctx, proc, parts = [], count = 0, rate = 0, busy = 0;

const say = (txt, cls = "") => {
  const feed = $("feed"); if (feed.firstChild && feed.firstChild.classList.contains("muted")) feed.textContent = "";
  const li = document.createElement("li"); li.className = cls;
  const t = document.createElement("time"); t.textContent = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit", second: "2-digit"});
  li.append(t, txt); feed.append(li); feed.scrollTop = feed.scrollHeight;
};
const post = async (url, fd) => { const r = await fetch(url, {method: "POST", body: fd}); const d = await r.json(); if (!r.ok) throw new Error(d.error || "Request failed."); return d; };
const pct = v => Math.round(v * 100) + "%";

function beep() {
  try { const c = new AudioContext(), o = c.createOscillator(); o.frequency.value = 880; o.connect(c.destination); o.start(); o.stop(c.currentTime + 0.35); } catch {}
  navigator.vibrate && navigator.vibrate([200, 100, 200]);
}

function wavBlob(x) {
  const ratio = rate / SR, n = Math.floor(x.length / ratio), v = new DataView(new ArrayBuffer(44 + n * 2));
  const s = (o, t) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  s(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); s(8, "WAVEfmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, SR, true); v.setUint32(28, SR * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  s(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {                        // average samples down to 16 kHz
    let a = Math.floor(i * ratio), b = Math.max(a + 1, Math.floor((i + 1) * ratio)), sum = 0;
    for (let j = a; j < b; j++) sum += x[j];
    v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, sum / (b - a))) * 32767, true);
  }
  return new Blob([v], {type: "audio/wav"});
}

function flush() {
  const x = new Float32Array(count); let o = 0;
  parts.forEach(p => { x.set(p, o); o += p.length; }); parts = []; count = 0;
  lastWav = wavBlob(x); $("hear").disabled = false;
  const fd = new FormData(); fd.append("id", sid); fd.append("audio", lastWav, "c.wav");
  busy++; post("/api/live/chunk", fd).then(handle).catch(e => $("err").textContent = e.message).finally(() => busy--);
}

function bar(d) {
  const tl = $("tl"), i = document.createElement("i"), lv = d.confirmed ? "bad" : d.first >= 0.5 ? "mid" : "";
  i.style.height = Math.max(6, (d.second ?? d.first) * 100) + "%"; i.className = lv + (d.second != null ? " two" : "");
  tl.append(i); while (tl.children.length > 30) tl.firstChild.remove();
}

function handle(d) {
  $("err").textContent = "";
  $("pct").textContent = pct(d.risk); $("fill").style.width = pct(d.risk); $("fill").style.background = COLOR[d.level];
  $("lvl").textContent = {low: "Low risk", medium: "Medium risk", high: "High risk"}[d.level];
  if (!d.speech) return;
  bar(d);
  if (d.first < 0.5) { say(`Checked the last ${CHUNK} seconds: sounds natural (${pct(d.first)} risk).`, "ok"); return; }
  say(`Part of that sounded synthetic (${pct(d.first)}). Checking again with more context...`, "warn");
  setTimeout(() => {
    if (d.confirmed) {
      say(`Second check agrees (${pct(d.second)}). This voice is likely AI-generated. Don't share codes or money. Hang up and call back on a number you know.`, "bad");
      const a = $("alert"); a.hidden = false; a.textContent = "Likely AI-cloned voice on this call. Verify before you act."; beep();
    } else say(`Second check disagrees (${pct(d.second)}). Probably a false alarm. Still listening.`);
  }, 700);
}

async function start() {
  $("err").textContent = "";
  try {
    stream = $("src").value === "mic"
      ? await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: $("clean").checked, noiseSuppression: $("clean").checked, autoGainControl: $("clean").checked}})
      : await navigator.mediaDevices.getDisplayMedia({video: true, audio: true});
    if (!stream.getAudioTracks().length) { stream.getTracks().forEach(t => t.stop()); throw new Error("No audio shared. Tick 'Share tab audio' (or 'Share system audio') in the picker."); }
    stream.getVideoTracks().forEach(t => t.stop());
    const info = await post("/api/live/start", new FormData()); sid = info.id; $("demo").hidden = !info.demo;
    const ms = new MediaStream(stream.getAudioTracks()); let node;
    try { ctx = new AudioContext({sampleRate: SR}); node = ctx.createMediaStreamSource(ms); }   // browser resamples to 16 kHz (Chrome/Edge)
    catch { ctx && ctx.close(); ctx = new AudioContext(); node = ctx.createMediaStreamSource(ms); }  // fallback: manual downsampling
    rate = ctx.sampleRate;
    proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = e => { parts.push(new Float32Array(e.inputBuffer.getChannelData(0))); count += 4096; if (count >= rate * CHUNK) flush(); };
    node.connect(proc); proc.connect(ctx.destination);
    $("go").textContent = "Stop protection"; $("go").classList.add("stop"); $("lvl").textContent = "Listening..."; $("alert").hidden = true;
    say(`I'm listening. I check the voice every ${CHUNK} seconds and double-check anything suspicious.`);
  } catch (e) { $("err").textContent = e.name === "NotAllowedError" ? "Audio access was blocked. Allow it in the browser and try again." : e.message; }
}

async function stop() {
  proc && proc.disconnect(); ctx && ctx.close(); stream && stream.getTracks().forEach(t => t.stop());
  for (let i = 0; i < 20 && busy; i++) await new Promise(r => setTimeout(r, 250));
  const fd = new FormData(); fd.append("id", sid); sid = null; parts = []; count = 0;
  await post("/api/live/stop", fd).catch(() => {});
  $("go").textContent = "Start protection"; $("go").classList.remove("stop"); $("lvl").textContent = "Not listening";
  say("Protection stopped. This call was saved to Past calls."); loadHistory();
}

$("go").onclick = () => sid ? stop() : start();

async function loadHistory() {
  const rows = await (await fetch("/api/history")).json(), tb = $("hist"); tb.textContent = ""; $("empty").hidden = rows.length > 0;
  rows.forEach(r => { const tr = tb.insertRow(); [r.kind === "live" ? "Live call" : "File", r.name, r.seconds + " s", pct(r.peak), r.alerts, r.started_at].forEach(t => tr.insertCell().textContent = t); });
}
loadHistory();

/* ---- tabs ---- */
document.querySelectorAll(".tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t === b));
  $("live").hidden = b.dataset.tab !== "live"; $("file").hidden = b.dataset.tab !== "file";
});

/* ---- file check ---- */
let fwav = null, fsamples = null;
async function toWav16(blob) {
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const dec = await ac.decodeAudioData(await blob.arrayBuffer()); ac.close();
  const off = new OfflineAudioContext(1, Math.ceil(dec.duration * SR), SR);
  const src = off.createBufferSource(); src.buffer = dec; src.connect(off.destination); src.start();
  const x = (await off.startRendering()).getChannelData(0);
  rate = SR; return {blob: wavBlob(x), x};
}
function drawWave(wins = [], dur = 0) {
  const c = $("wave"), g = c.getContext("2d"), W = c.width, H = c.height; g.clearRect(0, 0, W, H);
  wins.forEach(w => { g.fillStyle = `rgba(179,38,30,${0.08 + 0.5 * w.score})`; g.fillRect(w.start / dur * W, 0, (w.end - w.start) / dur * W, H); });
  if (!fsamples) return;
  const step = Math.ceil(fsamples.length / W); g.fillStyle = "#0E5A6B";
  for (let i = 0; i < W; i++) { let m = 0; for (let j = 0; j < step; j++) m = Math.max(m, Math.abs(fsamples[i * step + j] || 0)); g.fillRect(i, H / 2 - m * H / 2, 1, Math.max(1, m * H)); }
}
$("ufile").onchange = async e => {
  const f = e.target.files[0]; if (!f) return; $("ferr").textContent = ""; $("res").hidden = true;
  const saved = rate;
  try { const r = await toWav16(f); fwav = r.blob; fsamples = r.x; }
  catch { $("ferr").textContent = "This file could not be read as audio. Try a WAV, MP3 or M4A file."; return; }
  finally { rate = saved; }
  fwav.name = f.name; $("fname").textContent = `${f.name} (${(fsamples.length / SR).toFixed(1)} s)`;
  $("player").src = URL.createObjectURL(fwav); $("player").hidden = false; drawWave(); $("an").disabled = false;
};
$("an").onclick = async () => {
  $("an").disabled = true; $("an").textContent = "Analyzing..."; $("ferr").textContent = "";
  const fd = new FormData(); fd.append("audio", fwav, fwav.name.replace(/\.\w+$/, "") + ".wav");
  try {
    const d = await post("/api/analyze", fd), box = $("res"); box.hidden = false; box.className = "res " + d.level;
    $("rtitle").textContent = {low: "Likely a real voice", medium: "Suspicious: possible cloned voice", high: "Likely an AI-cloned voice"}[d.level];
    $("rfill").style.width = pct(d.risk); $("rscore").textContent = `Cloned-voice likelihood: ${pct(d.risk)}. ${d.confirmed} of ${d.windows.length} sections were flagged and confirmed on a second check.`;
    $("radv").textContent = d.advice; $("demo").hidden = !d.demo; drawWave(d.windows, fsamples.length / SR); loadHistory();
  } catch (e) { $("ferr").textContent = e.message; }
  $("an").disabled = false; $("an").textContent = "Analyze file";
};

/* ---- listen back + model picker ---- */
$("hear").onclick = () => lastWav && new Audio(URL.createObjectURL(lastWav)).play();
async function loadModels() {
  const h = await (await fetch("/api/health")).json(), sel = $("model"); sel.textContent = "";
  h.models.forEach(m => sel.add(new Option(m, m))); if (h.models.includes(h.model)) sel.value = h.model;
  $("mstat").textContent = h.demo ? "Demo mode: no real model loaded." : "Using " + h.model; $("demo").hidden = !h.demo;
}
$("apply").onclick = async () => {
  if (sid) { $("mstat").textContent = "Stop protection first."; return; }
  $("apply").disabled = true; $("mstat").textContent = "Loading model... the first time can take a few minutes.";
  try {
    const r = await fetch("/api/model", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: $("model").value})});
    const d = await r.json(); if (!r.ok) throw new Error(d.error);
    $("mstat").textContent = "Using " + d.model; $("demo").hidden = !d.demo;
  } catch (e) { $("mstat").textContent = e.message; }
  $("apply").disabled = false;
};
loadModels();
