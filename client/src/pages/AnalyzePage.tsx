import { useEffect, useRef, useState } from "react";
type Status = {available:boolean; mode:string; models:string[]; message?:string};
type Result = {mode:string; model:string; inference_ms:number; result:{mean_rgb?:number[]; color_hex?:string; region_pixels?:number; text?:string; task?:string; mock?:boolean; message?:string; limitations?:string[]; predictions?:{label:string;score:number}[]}};
export function AnalyzePage() {
  const [status,setStatus]=useState<Status|null>(null), [model,setModel]=useState(""), [image,setImage]=useState("");
  const [roi,setRoi]=useState([0,0,1,1]), [prompt,setPrompt]=useState("Describe visible liquid, glare, and uncertainty. Do not infer measured volume or a proven defect.");
  const [result,setResult]=useState<Result|null>(null), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const controller=useRef<AbortController|null>(null);
  const refresh=()=>fetch("/api/inference/status").then(r=>r.json()).then((s:Status)=>{setStatus(s);setModel(m=>s.models.includes(m)?m:s.models[0]??"");}).catch(()=>setError("Could not check Python connection."));
  useEffect(()=>{void refresh();return()=>controller.current?.abort();},[]);
  const selectFile=(file?:File)=>{
    setImage("");setResult(null);setError("");if(!file)return;
    if(!["image/jpeg","image/png"].includes(file.type)||file.size>4*1024*1024){setError("Select a JPEG or PNG no larger than 4 MiB.");return;}
    const reader=new FileReader();reader.onload=()=>setImage(String(reader.result));reader.onerror=()=>setError("Could not read image.");reader.readAsDataURL(file);
  };
  const analyze=async()=>{
    setBusy(true);setError("");setResult(null);controller.current=new AbortController();
    try{
      const response=await fetch("/api/inference/predict",{method:"POST",signal:controller.current.signal,headers:{"Content-Type":"application/json"},body:JSON.stringify({image,model,prompt:model==="measurements"?JSON.stringify({roi}):prompt})});
      const body=await response.json();if(!response.ok)throw new Error(body.error??"Analysis failed");setResult(body);
    }catch(e){setError(e instanceof Error&&e.name==="AbortError"?"Request cancelled. Remote inference may still be finishing.":e instanceof Error?e.message:"Analysis failed");}finally{setBusy(false);}
  };
  return <><div className="page-heading"><div><p className="eyebrow">Connected Python workflow</p><h1>Analyze an image</h1><p>Upload evidence and run the selected method. This console does not save uploaded images.</p></div></div>
    <p className="callout">Experimental advisory tool. Measurements and descriptions do not establish a defect, actual composition, or physical volume.</p>
    <div className="integration-grid"><section className="card integration-card"><div className="card__header"><h2>Image and method</h2><button className="ghost-button" disabled={busy} onClick={()=>void refresh()}>Refresh connection</button></div>
      <p role="status">{status?status.available?`Python connected · ${status.mode==="mock"?"MOCK — no inference":"real computation"}`:status.message:"Checking Python connection…"}</p>
      <label>Method<select value={model} disabled={busy||!status?.available} onChange={e=>{setModel(e.target.value);setResult(null);}}>{status?.models.map(m=><option key={m}>{m}</option>)}</select></label>
      <label>Source image<input type="file" accept="image/jpeg,image/png" disabled={busy} onChange={e=>selectFile(e.target.files?.[0])}/></label>
      {image&&<div className="upload-preview"><img src={image} alt="Uploaded source"/>{model==="measurements"&&<div className="selected-roi" style={{left:`${roi[0]*100}%`,top:`${roi[1]*100}%`,width:`${roi[2]*100}%`,height:`${roi[3]*100}%`}}/>}</div>}
      {model==="measurements"?<><p>Region coordinates are fractions from 0 to 1. The outline marks averaged pixels; liquid is not automatically segmented.</p><div className="roi-fields">{["Left","Top","Width","Height"].map((name,i)=><label key={name}>{name}<input type="number" min="0" max="1" step="0.01" value={roi[i]} disabled={busy} onChange={e=>{setRoi(a=>a.map((v,j)=>j===i?Number(e.target.value):v));setResult(null);}}/></label>)}</div></>:<label>Prompt<textarea value={prompt} maxLength={2000} disabled={busy} onChange={e=>setPrompt(e.target.value)}/></label>}
      <button className="primary-action" disabled={busy||!image||!model||!status?.available} onClick={()=>void analyze()}>{busy?"Analyzing…":"Run analysis"}</button>{busy&&<button className="ghost-button" onClick={()=>controller.current?.abort()}>Cancel request</button>}{error&&<p role="alert" className="integration-error">{error}</p>}
    </section><section className="card integration-card" aria-live="polite"><p className="eyebrow">Result provenance</p><h2>{result?result.mode==="mock"||result.result.mock?"Mock response":"Computed from your upload":"Waiting for analysis"}</h2>
      {result?<><p>{result.model} · {result.inference_ms} ms</p>{result.result.color_hex&&<div className="analysis-color"><span style={{background:result.result.color_hex}}/><div><strong>{result.result.color_hex}</strong><p>Mean RGB: {result.result.mean_rgb?.join(", ")}</p><p>{result.result.region_pixels?.toLocaleString()} selected pixels</p></div></div>}
      {result.result.text&&<p className="model-observation">{result.result.text}</p>}{result.result.message&&<p>{result.result.message}</p>}{result.result.task&&<p>Task: {result.result.task.replaceAll("_"," ")}</p>}
      {result.result.predictions&&<ul>{result.result.predictions.map(p=><li key={p.label}>{p.label}: {(p.score*100).toFixed(1)}% class score</li>)}</ul>}
      <p className="callout">Inspection verdict: unable to decide. Human review and a validated recipe comparison are required.</p>{result.result.limitations?.map(l=><p key={l}>{l}</p>)}<details><summary>Full response</summary><pre className="result-json">{JSON.stringify(result,null,2)}</pre></details></>:<p>The CPU measurements method works without trained weights or a GPU. ResNet and Cosmos appear when configured in Python.</p>}
    </section></div></>;
}
