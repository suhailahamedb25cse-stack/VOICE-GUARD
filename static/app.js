const $ = id => document.getElementById(id);
const LABEL = {genuine: "Likely a real voice", suspicious: "Suspicious: possible cloned voice", cloned: "Likely an AI-cloned voice"};
let wav = null, samples = null, recorder = null;

async function toWav(blob) {
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  const dec = await ac.decodeAudioData(await blob.arrayBuffer()); ac.close();
  const off = new OfflineAudioContext(1, Math.ceil(dec.duration * 16000), 16000);
  const src = off.createBufferSource(); src.buffer = dec; src.connect(off.destination); src.start();
  const x = (await off.startRendering()).getChannelData(0);
  const v = new DataView(new ArrayBuffer(44 + x.length * 2));
  const s = (o, t) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  s(0, "RIFF"); v.setUint32(4, 36 + x.length * 2, true); s(8, "WAVEfmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 16000, true); v.setUint32(28, 32000, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); s(36, "data"); v.setUint32(40, x.length * 2, true);
  x.forEach((a, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, a)) * 32767, true));
  return {blob: new Blob([v], {type: "audio/wav"}), samples: x};
}

function drawWave(windows = [], dur = 0) {
  const c = $("wave"), g = c.getContext("2d"), W = c.width, H = c.height;
  g.clearRect(0, 0, W, H);
  if (windows.length && dur) windows.forEach(w => {
    g.fillStyle = `rgba(179,38,30,${0.08 + 0.5 * w.score})`;
    g.fillRect(w.start / dur * W, 0, (w.end - w.start) / dur * W, H);
  });
  if (!samples) return;
  const step = Math.ceil(samples.length / W);
  g.fillStyle = "#0E5A6B";
  for (let i = 0; i < W; i++) {
    let mx = 0;
    for (let j = 0; j < step; j++) mx = Math.max(mx, Math.abs(samples[i * step + j] || 0));
    g.fillRect(i, H / 2 - mx * H / 2, 1, Math.max(1, mx * H));
  }
}

async function setAudio(blob, name) {
  $("err").textContent = ""; $("result").hidden = true;
  try {
    ({blob: wav, samples} = await toWav(blob));
  } catch { $("err").textContent = "This file could not be read as audio. Try a WAV, MP3 or M4A file."; return; }
  wav.name = name; $("fname").textContent = `${name} (${(samples.length / 16000).toFixed(1)} s)`;
  $("player").src = URL.createObjectURL(wav); $("player").hidden = false;
  drawWave(); $("go").disabled = false;
}

$("file").onchange = e => e.target.files[0] && setAudio(e.target.files[0], e.target.files[0].name);

$("rec").onclick = async () => {
  if (recorder) { recorder.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const parts = []; recorder = new MediaRecorder(stream);
    recorder.ondataavailable = e => parts.push(e.data);
    recorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop()); recorder = null;
      $("rec").textContent = "Record from microphone"; $("rec").classList.remove("rec");
      setAudio(new Blob(parts), "recording.wav");
    };
    recorder.start(); $("rec").textContent = "Stop recording"; $("rec").classList.add("rec");
  } catch { $("err").textContent = "Microphone access was blocked. Allow it in your browser, or upload a file instead."; }
};

$("go").onclick = async () => {
  $("go").disabled = true; $("go").textContent = "Analyzing..."; $("err").textContent = "";
  const fd = new FormData(); fd.append("audio", wav, wav.name.replace(/\.\w+$/, "") + ".wav");
  try {
    const r = await fetch("/api/analyze", {method: "POST", body: fd}), d = await r.json();
    if (!r.ok) throw new Error(d.error || "Analysis failed.");
    show(d); loadHistory();
  } catch (e) { $("err").textContent = e.message; }
  $("go").disabled = false; $("go").textContent = "Analyze voice";
};

function show(d) {
  const box = $("result"); box.hidden = false; box.className = "panel result " + d.verdict;
  $("vtitle").textContent = LABEL[d.verdict];
  $("fill").style.width = Math.round(d.score * 100) + "%";
  $("vscore").textContent = `Cloned-voice likelihood: ${Math.round(d.score * 100)}%`;
  $("advice").textContent = d.advice; $("demo").hidden = !d.demo;
  drawWave(d.windows, samples.length / 16000);
}

async function loadHistory() {
  const rows = await (await fetch("/api/history")).json(), tb = $("hist"); tb.textContent = "";
  $("empty").hidden = rows.length > 0;
  rows.forEach(r => {
    const tr = tb.insertRow();
    [r.filename || "recording", r.duration + " s", LABEL[r.verdict].split(":")[0], Math.round(r.score * 100) + "%", r.created_at]
      .forEach((t, i) => { const td = tr.insertCell(); td.textContent = t; if (i === 2) td.className = "v-" + r.verdict; });
  });
}
loadHistory();
