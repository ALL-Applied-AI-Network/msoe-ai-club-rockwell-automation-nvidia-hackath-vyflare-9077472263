import { useEffect, useRef, useState } from "react";
import { RectangleSelection } from "../components/RectangleSelection";
import { clamp } from "../inspection/geometry";
type Status = {available:boolean; mode:string; models:string[]; message?:string};
type Result = {mode:string; model:string; inference_ms:number; result:{mean_rgb?:number[]; color_hex?:string; region_pixels?:number; text?:string; task?:string; mock?:boolean; message?:string; limitations?:string[]; predictions?:{label:string;score:number}[]}};
const methods: Record<string, { label: string; description: string }> = {
  measurements: { label: "Average Color in Selected Area", description: "Computes the average RGB pixel color inside your selected area using the CPU. This is a color calculation without a trained model; it does not isolate the liquid, identify a recipe, or measure volume." },
  resnet18: { label: "ResNet18 Image Classification", description: "Runs the configured ResNet18 classifier on your image. Custom weights return their trained classes; default weights return ImageNet demonstration classes. Class scores do not establish a defect or verified recipe." },
  cosmos: { label: "Cosmos Image Description — Local", description: "Runs the configured Cosmos3 model on the Python service's GPU using your image and prompt. Its visual descriptions require review; they do not measure volume or verify a recipe." },
  cosmos_lite: { label: "Cosmos Image Description — Local (Lite Route)", description: "Runs the configured Cosmos3 model on the Python service's GPU using your image and prompt. Lite is a route name, not a smaller model. Its visual descriptions require review; they do not measure volume or verify a recipe." },
  cosmos_full: { label: "Cosmos Image Description — Remote Gateway", description: "Sends your image and prompt to the configured remote Cosmos service for a visual description. Full is a route name, not a larger model. Descriptions require review; they do not measure volume or verify a recipe." }
};
export function AnalyzePage() {
  const [status,setStatus]=useState<Status|null>(null), [model,setModel]=useState(""), [image,setImage]=useState("");
  const [roi,setRoi]=useState([0,0,1,1]), [prompt,setPrompt]=useState("Describe visible liquid, glare, and uncertainty. Do not infer measured volume or a proven defect.");
  const [result,setResult]=useState<Result|null>(null), [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const controller=useRef<AbortController|null>(null);
  const refresh=()=>fetch("/api/inference/status").then(r=>r.json()).then((s:Status)=>{const single={...s,models:s.models.filter(m=>m!=="model4")};setStatus(single);setModel(m=>single.models.includes(m)?m:single.models[0]??"");}).catch(()=>setError("Could not check Python connection."));
  useEffect(()=>{void refresh();return()=>controller.current?.abort();},[]);
  const selectFile=(file?:File)=>{
    setImage("");setRoi([0,0,1,1]);setResult(null);setError("");if(!file)return;
    if(!["image/jpeg","image/png"].includes(file.type)||file.size>4*1024*1024){setError("Select a JPEG or PNG no larger than 4 MiB.");return;}
    const reader=new FileReader();reader.onload=()=>setImage(String(reader.result));reader.onerror=()=>setError("Could not read image.");reader.readAsDataURL(file);
  };
  const analyze=async()=>{
    setBusy(true);setError("");setResult(null);controller.current=new AbortController();
    try{
      const response=await fetch("/api/inference/predict",{method:"POST",signal:controller.current.signal,headers:{"Content-Type":"application/json"},body:JSON.stringify({image,model,prompt:model==="measurements"?JSON.stringify({roi:[roi[0],roi[1],Math.min(roi[2],1-roi[0]),Math.min(roi[3],1-roi[1])]}):prompt})});
      const body=await response.json();if(!response.ok)throw new Error(body.error??"Analysis failed");setResult(body);
    }catch(e){setError(e instanceof Error&&e.name==="AbortError"?"Request cancelled. Remote inference may still be finishing.":e instanceof Error?e.message:"Analysis failed");}finally{setBusy(false);}
  };
  return <><div className="page-heading"><div><p className="eyebrow">Single-Image Analysis</p><h1>Analyze an Image</h1><p>Upload one image and choose a method. Cosmos runs only when a Cosmos method is selected and connected. This console does not save uploaded images.</p></div></div>
    <p className="callout">Experimental advisory tool. Measurements and descriptions do not establish a defect, actual composition, or physical volume.</p>
    <div className="integration-grid"><section className="card integration-card"><div className="card__header"><h2>Image and Method</h2><button className="ghost-button" disabled={busy} onClick={()=>void refresh()}>Refresh Connection</button></div>
      <p role="status">{status?status.available?`Python connected · ${status.mode==="mock"?"MOCK — no inference":"real computation"}`:status.message:"Checking Python connection…"}</p>
      <label>Method<select value={model} aria-describedby="method-description" disabled={busy||!status?.available} onChange={e=>{setModel(e.target.value);setResult(null);}}>{status?.models.map(m=><option key={m} value={m}>{methods[m]?.label ?? m}</option>)}</select></label>
      <p id="method-description">{methods[model]?.description ?? "Connect an image-analysis method to see its description."}</p>
      {model && !model.startsWith("cosmos") && <p>Cosmos is not used by the selected method.</p>}
      <label>Source Image<input type="file" accept="image/jpeg,image/png" disabled={busy} onChange={e=>selectFile(e.target.files?.[0])}/></label>
      {image&&<div className="upload-preview"><img src={image} alt="Uploaded source" draggable={false}/>{model==="measurements"&&<RectangleSelection value={{x:roi[0],y:roi[1],width:roi[2],height:roi[3]}} disabled={busy} onChange={r=>{setRoi([r.x,r.y,r.width,r.height]);setResult(null);}}/>}</div>}
      {model==="measurements"?<><p>Drag on the image to select an area, or enter coordinates below. Both stay synchronized. Coordinates are fractions from 0 to 1; the box selects pixels and does not segment liquid.</p><div className="roi-fields">{["Left","Top","Width","Height"].map((name,i)=><label key={name}>{name}<input type="number" min="0" max="1" step="0.01" value={roi[i]} disabled={busy} onChange={e=>{const n=Number(e.target.value);if(!Number.isFinite(n))return;setRoi(a=>{const next=[...a];next[i]=clamp(n,i<2?0:0.001,i<2?0.999:1-next[i-2]);next[2]=Math.min(next[2],1-next[0]);next[3]=Math.min(next[3],1-next[1]);return next;});setResult(null);}}/></label>)}</div><button className="ghost-button" disabled={busy} onClick={()=>{setRoi([0,0,1,1]);setResult(null);}}>Select Entire Image</button></>:<label>Prompt<textarea value={prompt} maxLength={2000} disabled={busy} onChange={e=>setPrompt(e.target.value)}/></label>}
      <button className="primary-action" disabled={busy||!image||!model||!status?.available} onClick={()=>void analyze()}>{busy?"Analyzing…":"Run Analysis"}</button>{busy&&<button className="ghost-button" onClick={()=>controller.current?.abort()}>Cancel Request</button>}{error&&<p role="alert" className="integration-error">{error}</p>}
    </section><section className="card integration-card" aria-live="polite"><p className="eyebrow">Result Provenance</p><h2>{result?result.mode==="mock"||result.result.mock?"Mock Response":"Computed from Your Upload":"Waiting for Analysis"}</h2>
      {result?<><p>{methods[result.model]?.label ?? result.model} · {result.inference_ms} ms</p>{result.result.color_hex&&<div className="analysis-color"><span style={{background:result.result.color_hex}}/><div><strong>{result.result.color_hex}</strong><p>Mean RGB: {result.result.mean_rgb?.join(", ")}</p><p>{result.result.region_pixels?.toLocaleString()} selected pixels</p></div></div>}
      {result.result.text&&<p className="model-observation">{result.result.text}</p>}{result.result.message&&<p>{result.result.message}</p>}{result.result.task&&<p>Task: {result.result.task.replaceAll("_"," ")}</p>}
      {result.result.predictions&&<ul>{result.result.predictions.map(p=><li key={p.label}>{p.label}: {(p.score*100).toFixed(1)}% class score</li>)}</ul>}
      <p className="callout">Inspection verdict: unable to decide. Human review and a validated recipe comparison are required.</p>{result.result.limitations?.map(l=><p key={l}>{l}</p>)}<details><summary>Full Response</summary><pre className="result-json">{JSON.stringify(result,null,2)}</pre></details></>:<p>Results appear after you run the selected method. Average Color in Selected Area computes pixel color; Cosmos describes an image using your prompt when its service is configured. Model 4 mixture comparison is available in the Inspection Workspace.</p>}
    </section></div></>;
}
