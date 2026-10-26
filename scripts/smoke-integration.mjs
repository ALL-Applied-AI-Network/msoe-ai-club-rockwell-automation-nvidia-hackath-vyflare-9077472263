import { spawn, execFileSync } from "node:child_process";
import assert from "node:assert/strict";
const python=process.env.PYTHON ?? (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const backend=spawn(python,["backend/app.py"],{env:{...process.env,PORT:"18000",MODEL_MODE:"real",ENABLED_MODELS:"measurements"},stdio:["ignore","pipe","pipe"]});
const web=spawn(process.execPath,["server/dist/server/src/index.js"],{env:{...process.env,PORT:"18787",INFERENCE_URL:"http://127.0.0.1:18000"},stdio:["ignore","pipe","pipe"]});
let log=""; for(const child of [backend,web]){ child.stdout.on("data",b=>{log+=b});child.stderr.on("data",b=>{log+=b});child.on("error",e=>{log+=e.message}); }
const waitFor=async url=>{for(let i=0;i<100;i++){try{const r=await fetch(url);if(r.ok)return;}catch{}await new Promise(r=>setTimeout(r,100));}throw new Error(`Service failed: ${url}\n${log}`);};
try{
  await Promise.all([waitFor("http://127.0.0.1:18000/health"),waitFor("http://127.0.0.1:18787/api/health")]);
  const status=await (await fetch("http://127.0.0.1:18787/api/inference/status")).json();assert.equal(status.mode,"real");assert.ok(status.models.includes("measurements"));
  const evidence=await (await fetch("http://127.0.0.1:18787/api/experiments")).json();assert.equal(evidence.anomaly.vials.length,30);assert.equal(evidence.cosmos.clips.length,30);assert.equal(evidence.validated,false);
  assert.ok((await fetch("http://127.0.0.1:18787/experiment-thumbs/v5_e01.jpg")).ok);
  for(const route of ["/analyze","/experiments","/inspection/DEMO-V5-04"]) assert.ok((await (await fetch(`http://127.0.0.1:18787${route}`)).text()).includes('<div id="root">'));
  const png=execFileSync(python,["-c","from PIL import Image; import sys; Image.new('RGB',(32,24),(255,0,0)).save(sys.stdout.buffer,format='PNG')"]);
  const response=await fetch("http://127.0.0.1:18787/api/inference/predict",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:`data:image/png;base64,${png.toString("base64")}`,model:"measurements",prompt:'{"roi":[0,0,1,1]}'})});
  assert.equal(response.status,200);const body=await response.json();assert.deepEqual(body.result.mean_rgb,[255,0,0]);assert.equal(body.result.volume_ml,null);assert.equal(body.result.decision,"UNABLE_TO_DECIDE");
  console.log("PASS: built console → Node proxy → Python → measured red pixels; 30 recorded experiments, thumbnails, and SPA routes.");
}finally{backend.kill();web.kill();}
