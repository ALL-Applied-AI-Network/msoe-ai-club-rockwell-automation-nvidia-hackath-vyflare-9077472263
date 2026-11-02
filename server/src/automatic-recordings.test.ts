import express from "express";
import {request as httpRequest,type Server} from "node:http";
import {afterEach,describe,expect,it,vi} from "vitest";
import {recordedProducerRouter} from "./recorded-producer.js";
const servers:Server[]=[];
async function serve(app:express.Express){const s=app.listen(0,"127.0.0.1");servers.push(s);await new Promise<void>(r=>s.once("listening",r));const a=s.address();if(!a||typeof a==="string")throw Error();return `http://127.0.0.1:${a.port}`;}
afterEach(async()=>{vi.unstubAllEnvs();await Promise.all(servers.splice(0).map(s=>new Promise<void>(r=>s.close(()=>r()))));});
describe("Automatic new-recording transport",()=>{
 it("registers raw footage and automatically ensures a job with private credentials",async()=>{
  vi.stubEnv("INFERENCE_TOKEN","private");const key="recording-"+"a".repeat(64);let starts=0;
  const upstream=express();upstream.post("/api/recipe-workflow/demo/producer/recordings",express.raw({type:()=>true}), (req,res)=>{
   expect(req.headers.authorization).toBe("Bearer private");expect(req.body.toString()).toBe("new media");expect(req.get("x-recording-name")).toBe("new.mp4");res.status(201).json({video_id:key,sha256:"a".repeat(64)});
  });
  upstream.post(`/api/recipe-workflow/demo/producer/videos/${key}/ensure`,express.json(),(req,res)=>{expect(req.body).toEqual({});starts++;res.status(202).json({state:"queued",events:[]});});
  upstream.post("/api/recipe-workflow/demo/producer/videos/video-3/ensure",express.json(),(_req,res)=>res.status(202).json({state:"processing"}));
  const app=express();app.use(recordedProducerRouter(await serve(upstream)));const url=await serve(app);
  const registration=await fetch(url+"/recordings",{method:"POST",headers:{"Content-Type":"video/mp4","X-Recording-Name":"new.mp4"},body:"new media"});expect(registration.status).toBe(201);expect((await registration.json()).video_id).toBe(key);
  const r=await fetch(url+`/videos/${key}/ensure`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});expect(r.status).toBe(202);expect((await r.json()).state).toBe("queued");expect(starts).toBe(1);
  expect((await fetch(url+"/videos/video-3/ensure",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})).status).toBe(202);
 });
 it("rejects foreign/public uploads and client-supplied measurements",async()=>{
  const app=express();app.use(recordedProducerRouter("http://127.0.0.1:1"));const url=await serve(app);
  expect((await fetch(url+"/recordings",{method:"POST",headers:{"Content-Type":"video/mp4",Origin:"https://foreign.example"},body:"abc"})).status).toBe(403);
  const publicStatus=await new Promise<number|undefined>((resolve,reject)=>{const req=httpRequest(url+"/recordings",{method:"POST",headers:{"Content-Type":"video/mp4",Host:"public.example"}},r=>{r.resume();resolve(r.statusCode);});req.on("error",reject);req.end("abc");});expect(publicStatus).toBe(403);
  expect((await fetch(url+"/videos/video-3/ensure",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({recipe_id:7})})).status).toBe(400);
 });
});
