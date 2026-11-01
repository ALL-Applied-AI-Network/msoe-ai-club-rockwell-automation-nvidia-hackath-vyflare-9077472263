import express from "express";
import type {Server} from "node:http";
import {afterEach,describe,expect,it,vi} from "vitest";
import {inferenceRouter} from "./inference.js";
const servers:Server[]=[];
async function serve(app:express.Express){const s=app.listen(0,"127.0.0.1");servers.push(s);await new Promise<void>(r=>s.once("listening",r));const a=s.address();if(!a||typeof a==="string")throw Error();return `http://127.0.0.1:${a.port}`;}
afterEach(async()=>{vi.unstubAllEnvs();await Promise.all(servers.splice(0).map(s=>new Promise<void>(r=>s.close(()=>r()))));});
const input={images:Array(3).fill("data:image/png;base64,YWJj"),frame_id:"capture-1",vial_id:"vial-1",batch_id:"batch-1",batch_position:1,recipe_id:41,camera_profile:"vial-fill-640x480"};
const post=(url:string,body:unknown=input)=>fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
describe("Model2 branch transport",()=>{
 it("preserves protected metadata and paired independent results",async()=>{
  vi.stubEnv("INFERENCE_TOKEN","private");const upstream=express();
  upstream.get("/model2",(req,res)=>{expect(req.headers.authorization).toBe("Bearer private");res.json({approved_for_supporting_evidence:false,config_version:"model2-baseline-v4"});});
  upstream.post("/predict/vial-evidence",express.raw({type:()=>true} ),async(req,res)=>{
   expect(req.headers.authorization).toBe("Bearer private");const form=await new Request("http://localhost",{method:"POST",headers:{"Content-Type":req.headers["content-type"]!},body:req.body}).formData();
   expect(form.getAll("images")).toHaveLength(3);expect(form.get("recipe_id")).toBe("41");expect(form.get("batch_position")).toBe("1");
   res.json({...input,images:undefined,intended_recipe_id:41,model4:{review:{expected_transition_contamination:true}},model2:{verification:{counts_as_supporting_evidence:false}},combined_review:{automatic_release:false,flags:["expected_transition_contamination"]}});
  });
  const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));const url=await serve(bridge);
  expect((await(await fetch(url+"/model2")).json()).approved_for_supporting_evidence).toBe(false);
  const r=await post(url+"/vial-evidence");expect(r.status).toBe(200);const b=await r.json();expect(b.model4.review.expected_transition_contamination).toBe(true);expect(b.model2.verification.counts_as_supporting_evidence).toBe(false);expect(b.combined_review.automatic_release).toBe(false);
 });
 it("rejects mismatched response identity instead of attaching another fill's scores",async()=>{
  const upstream=express();upstream.post("/predict/model2",(_req,res)=>res.json({...input,frame_id:"another-fill"}));const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));expect((await post((await serve(bridge))+"/model2")).status).toBe(502);
 });
 it("keeps retry information and rejects incomplete evidence before Python",async()=>{
  let calls=0;const upstream=express();upstream.post("/predict/model2",(_req,res)=>{calls++;res.status(429).set("Retry-After","1").json({error:"busy"});});const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));const url=await serve(bridge);
  expect((await post(url+"/model2",{...input,images:[]})).status).toBe(400);expect(calls).toBe(0);
  const r=await post(url+"/model2");expect(r.status).toBe(429);expect(r.headers.get("retry-after")).toBe("1");expect(calls).toBe(1);
 });
});
