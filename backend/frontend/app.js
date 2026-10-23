const el = id => document.getElementById(id);
let stream = null, timer = null, busy = false, sequence = 0, generation = 0;
const show = value => { el('result').textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
const endpoint = path => el('api').value.replace(/\/$/, '') + path;
el('health').onclick = async () => {
  try { const r = await fetch(endpoint('/health')); show(await r.json()); }
  catch (e) { show(`API unavailable: ${e.message}`); }
};
async function send(image, session) {
  const id = String(++sequence), body = new FormData();
  body.append('image', image, 'frame.jpg');
  body.append('frame_id', id);
  body.append('model', el('model').value);
  body.append('prompt', el('prompt').value);
  // The browser supplies the multipart boundary; do not set Content-Type.
  const response = await fetch(endpoint('/predict'), {method: 'POST', body});
  const data = await response.json();
  if (session !== generation) return;
  if (!response.ok) { show(data); return; }
  if (data.frame_id === id) show(data);
}
async function capture() {
  if (!stream || busy || el('video').readyState < 2) return;
  busy = true;
  const session = generation;
  try {
    const video = el('video'), canvas = el('canvas');
    canvas.width = Math.min(960, video.videoWidth);
    canvas.height = Math.round(video.videoHeight * canvas.width / video.videoWidth);
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    if (blob && session === generation) await send(blob, session);
  } catch (e) { if (session === generation) show(e.message); }
  finally { busy = false; }
}
function schedule() {
  clearInterval(timer);
  timer = setInterval(capture, el('model').value === 'cosmos' ? 5000 : 500);
}
el('start').onclick = async () => {
  el('start').disabled = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({video: true, audio: false});
    el('video').srcObject = stream;
    generation++;
    el('stop').disabled = false;
    schedule();
  } catch (e) { el('start').disabled = false; show(`Camera: ${e.message}`); }
};
function stop() {
  generation++;
  clearInterval(timer);
  stream?.getTracks().forEach(track => track.stop());
  stream = null;
  el('video').srcObject = null;
  el('start').disabled = false;
  el('stop').disabled = true;
  // Do not clear busy until an outstanding request finishes.
}
el('stop').onclick = stop;
el('model').onchange = () => { generation++; if (stream) schedule(); };
el('file').onchange = async () => {
  if (busy) { show('An inference is still running; try again when it finishes.'); return; }
  const file = el('file').files[0];
  if (!file) return;
  stop(); busy = true;
  try { await send(file, generation); } catch (e) { show(e.message); }
  finally { busy = false; el('file').value = ''; }
};
window.addEventListener('pagehide', stop);
