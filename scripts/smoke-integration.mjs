import { spawn, execFileSync } from "node:child_process";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
const recipeTestDir=mkdtempSync(path.join(tmpdir(),"vyflare-recipe-smoke-"));
const python=process.env.PYTHON ?? (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const backend=spawn(python,["backend/app.py"],{env:{...process.env,RECIPE_DB_PATH:path.join(recipeTestDir,"recipes.sqlite3"),PORT:"18000",MODEL_MODE:"real",ENABLED_MODELS:"measurements,model4"},stdio:["ignore","pipe","pipe"]});
const web=spawn(process.execPath,["server/dist/server/src/index.js"],{env:{...process.env,PORT:"18787",INFERENCE_URL:"http://127.0.0.1:18000"},stdio:["ignore","pipe","pipe"]});
let log=""; for(const child of [backend,web]){ child.stdout.on("data",b=>{log+=b});child.stderr.on("data",b=>{log+=b});child.on("error",e=>{log+=e.message}); }
const waitFor=async url=>{for(let i=0;i<100;i++){try{const r=await fetch(url);if(r.ok)return;}catch{}await new Promise(r=>setTimeout(r,100));}throw new Error(`Service failed: ${url}\n${log}`);};
try{
  await Promise.all([waitFor("http://127.0.0.1:18000/health"),waitFor("http://127.0.0.1:18787/api/health")]);
  const status=await (await fetch("http://127.0.0.1:18787/api/inference/status")).json();assert.equal(status.mode,"real");assert.ok(status.models.includes("measurements"));
  const evidence=await (await fetch("http://127.0.0.1:18787/api/experiments")).json();assert.equal(evidence.anomaly.vials.length,30);assert.equal(evidence.cosmos.clips.length,30);assert.equal(evidence.validated,false);
  assert.ok((await fetch("http://127.0.0.1:18787/experiment-thumbs/v5_e01.jpg")).ok);
  for(const route of ["/inspect","/overview","/recipes","/analyze","/experiments","/inspection/DEMO-V5-04"]) {
    const response=await fetch(`http://127.0.0.1:18787${route}`); const html=await response.text();
    assert.ok(response.ok && html.includes('<div id="root">'), `${route}: HTTP ${response.status}, ${html.slice(0,400)}\n${log}`);
  }
  const png=execFileSync(python,["-c","from PIL import Image; import sys; Image.new('RGB',(32,24),(255,0,0)).save(sys.stdout.buffer,format='PNG')"]);
  const response=await fetch("http://127.0.0.1:18787/api/inference/predict",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:`data:image/png;base64,${png.toString("base64")}`,model:"measurements",prompt:'{"roi":[0,0,1,1]}'})});
  assert.equal(response.status,200);const body=await response.json();assert.deepEqual(body.result.mean_rgb,[255,0,0]);assert.equal(body.result.volume_ml,null);assert.equal(body.result.decision,"UNABLE_TO_DECIDE");
  const recipes = await (await fetch("http://127.0.0.1:18787/api/inference/model4/recipes")).json(); assert.equal(recipes.recipes.length,52);
  const frames = JSON.parse(execFileSync(python,["-c", "import numpy as np, json, io, base64; from PIL import Image; a=np.load('backend/tests/fixtures/model4/registered_frames.npz',allow_pickle=False); result=[]\nfor i in range(1,4):\n b=io.BytesIO(); Image.fromarray(a['post_'+str(i)]).save(b,'PNG'); result.append('data:image/png;base64,'+base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"],{encoding:"utf8",maxBuffer:16*1024*1024}));
  for (const batch_position of [1,2]) {
    const response = await fetch("http://127.0.0.1:18787/api/inference/model4",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({images:frames,frame_id:"smoke-fill",vial_id:"smoke-vial",batch_id:"smoke-batch",batch_position,recipe_id:6,camera_profile:"vial-fill-640x480"})});
    assert.equal(response.status,200); const prediction=await response.json(); assert.equal(prediction.mode,"real");
    assert.ok(Math.abs(prediction.result.checkpoint.estimated_percentages.T200-30.87182601227989)<0.000001);
    assert.equal(prediction.result.review.expected_transition_contamination,batch_position===1); assert.equal(prediction.result.review.automatic_release,false);
  }
  const manifest=await(await fetch("http://127.0.0.1:18787/api/inspection/evidence")).json();assert.deepEqual(manifest.videos.map(v=>v.vials.length),[19,3]);
  for (const video of manifest.videos.filter(v=>v.available)) {
    const response=await fetch(`http://127.0.0.1:18787${video.url}`,{headers:{Range:"bytes=0-31"}});
    assert.equal(response.status,206); assert.equal((await response.arrayBuffer()).byteLength,32);
  }
  const library=await(await fetch("http://127.0.0.1:18787/api/recipe-library/references")).json();assert.equal(library.recipes.length,52);
  for(const id of [41,50,60,99]) assert.ok(library.recipes.some(r=>r.recipe_id===id));
  const candidates=await(await fetch("http://127.0.0.1:18787/api/recipe-library/candidates")).json();assert.deepEqual(candidates.recipes,[]);assert.equal(candidates.persistence,"sqlite");
  const assessUrl="http://127.0.0.1:18787/api/recipe-workflow/recorded/video-1/V1-V01";
  const assess=()=>fetch(assessUrl,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}).then(r=>r.json());
  const first=await assess();assert.equal(first.assessment.assessment_status,"INSUFFICIENT_EVIDENCE");assert.equal(first.assessment.coverage.comparable_reference_count,0);
  assert.equal((await assess()).assessment.inspection_id,first.assessment.inspection_id);
  const saved=await(await fetch("http://127.0.0.1:18787/api/recipe-workflow/videos/video-1/assessments")).json();assert.equal(saved.assessments.length,1);
  console.log("PASS: built console → Node → real Python measurements and frozen Model 4; normal/first-vial review, 52 recipes, 22 reviewed fills, original routes.");
}finally{backend.kill();web.kill();rmSync(recipeTestDir,{recursive:true,force:true});}
