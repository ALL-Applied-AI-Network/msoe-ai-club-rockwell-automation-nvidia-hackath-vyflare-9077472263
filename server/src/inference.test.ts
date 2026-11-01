import express from "express";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Server } from "node:http";
import { inferenceRouter } from "./inference.js";

const servers: Server[] = [];
async function serve(app: express.Express) {
  const server = app.listen(0, "127.0.0.1"); servers.push(server);
  await new Promise<void>(resolve => server.once("listening", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("No port");
  return `http://127.0.0.1:${address.port}`;
}
afterEach(async () => { vi.unstubAllEnvs(); await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve())))); });
describe("Python gateway bridge", () => {
  it("translates image JSON into multipart and preserves upstream errors", async () => {
    const upstream = express();
    upstream.get("/health", (_req,res) => res.json({mode:"real",models:["measurements"],busy:false}));
    upstream.post("/predict", express.raw({type:()=>true,limit:"5mb"}), (req,res) => {
      expect(req.headers["content-type"]).toContain("multipart/form-data");
      expect(req.body.toString()).toContain('name="image"');
      expect(req.body.toString()).toContain("measurements");
      res.status(422).json({error:"ROI outside source image"});
    });
    const bridge=express(); bridge.use(inferenceRouter(await serve(upstream)));
    const url=await serve(bridge);
    expect((await (await fetch(`${url}/status`)).json()).available).toBe(true);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"data:image/png;base64,YWJj",model:"measurements"})});
    expect(response.status).toBe(422); expect((await response.json()).error).toContain("ROI");
  });
  it("reports unavailable instead of fabricated predictions", async () => {
    const bridge=express(); bridge.use(inferenceRouter("http://127.0.0.1:1"));
    const url=await serve(bridge);
    expect((await (await fetch(`${url}/status`)).json()).available).toBe(false);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"data:image/png;base64,YWJj",model:"measurements"})});
    expect(response.status).toBe(503);
  });
  it("rejects unsupported inputs before inference", async () => {
    const bridge=express(); bridge.use(inferenceRouter("http://127.0.0.1:1"));
    const url=await serve(bridge);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"not-an-image",model:"measurements"})});
    expect(response.status).toBe(400);
  });
  it("loads protected Model 4 recipes and forwards three frames with batch identity", async () => {
    vi.stubEnv("INFERENCE_TOKEN", "test-token");
    const upstream = express();
    upstream.get("/model4/recipes", (req, res) => {
      expect(req.headers.authorization).toBe("Bearer test-token"); res.json({ recipes: [{ recipe_id: 6 }] });
    });
    upstream.post("/predict/model4", express.raw({ type: () => true }), async (req, res) => {
      expect(req.headers.authorization).toBe("Bearer test-token");
      const form = await new Request("http://localhost", { method: "POST", headers: { "Content-Type": req.headers["content-type"]! }, body: req.body }).formData();
      expect(form.getAll("images")).toHaveLength(3);
      expect(await (form.get("images") as File).text()).toBe("abc");
      expect(form.get("batch_position")).toBe("1"); expect(form.get("recipe_id")).toBe("99");
      expect(form.get("vial_id")).toBe("vial-1"); expect(form.get("batch_id")).toBe("batch-1");
      expect(form.get("camera_profile")).toBe("vial-fill-640x480");
      res.setHeader("Retry-After", "2"); res.status(429).json({ error: "Inference busy" });
    });
    const bridge = express(); bridge.use(inferenceRouter(await serve(upstream))); const url = await serve(bridge);
    expect((await (await fetch(`${url}/model4/recipes`)).json()).recipes).toEqual([{ recipe_id: 6 }]);
    const response = await fetch(`${url}/model4`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images: Array(3).fill("data:image/png;base64,YWJj"), frame_id: "request-1", vial_id: "vial-1", batch_id: "batch-1", batch_position: 1, recipe_id: 99, camera_profile: "vial-fill-640x480" }) });
    expect(response.status).toBe(429); expect(response.headers.get("retry-after")).toBe("2"); expect((await response.json()).error).toBe("Inference busy");
  });
  it("rejects incomplete Model 4 evidence without calling Python", async () => {
    const bridge = express(); bridge.use(inferenceRouter("http://127.0.0.1:1")); const url = await serve(bridge);
    for (const override of [{ images: [] }, { batch_position: 0 }, { images: ["bad", "bad", "bad"] }, { recipe_id: null }]) {
      const response = await fetch(`${url}/model4`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ images: Array(3).fill("data:image/png;base64,YWJj"), frame_id: "request-1", vial_id: "vial-1", batch_id: "batch-1", batch_position: 2, recipe_id: 6, camera_profile: "vial-fill-640x480", ...override }) });
      expect(response.status).toBe(400);
    }
  });
  it("reports unavailable Model 4 and invalid upstream responses without inventing results", async () => {
    const upstream = express();
    upstream.get("/model4/recipes", (_req, res) => res.status(503).json({ error: "Model 4 disabled" }));
    upstream.get("/model4", (_req, res) => res.send("unexpected HTML"));
    const bridge = express(); bridge.use(inferenceRouter(await serve(upstream))); const url = await serve(bridge);
    expect((await fetch(`${url}/model4/recipes`)).status).toBe(503);
    expect((await fetch(`${url}/model4`)).status).toBe(502);
  });
});

describe("Cosmos recorded-frame transport", () => {
  it("preserves captured evidence IDs, prompts and credentials without recipe calls", async () => {
    vi.stubEnv("INFERENCE_TOKEN", "fixture-private-token");
    const upstream=express();
    upstream.post("/predict",express.raw({type:()=>true}),async(req,res)=>{
      expect(req.headers.authorization).toBe("Bearer fixture-private-token");
      const form=await new Request("http://localhost",{method:"POST",headers:{"Content-Type":req.headers["content-type"]!},body:req.body}).formData();
      expect(form.get("frame_id")).toBe("captured-frame-7"); expect(form.get("model")).toBe("cosmos_full"); expect(form.get("prompt")).toBe("Describe this frame only.");
      res.json({frame_id:form.get("frame_id"),model:form.get("model"),mode:"real",inference_ms:42,result:{text:"Contract-test description."}});
    });
    const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));const url=await serve(bridge);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"data:image/png;base64,YWJj",model:"cosmos_full",frame_id:"captured-frame-7",prompt:"Describe this frame only."})});
    expect(response.status).toBe(200);expect((await response.json()).frame_id).toBe("captured-frame-7");
  });
  it("rejects a successful reply bound to different evidence",async()=>{
    const upstream=express();upstream.post("/predict",(_req,res)=>res.json({frame_id:"wrong-frame",model:"cosmos_full",mode:"real",result:{text:"Wrong evidence"}}));
    const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));const url=await serve(bridge);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"data:image/png;base64,YWJj",model:"cosmos_full",frame_id:"wanted"})});expect(response.status).toBe(502);
  });
  it("preserves busy responses without falling back to saved descriptions",async()=>{
    const upstream=express();upstream.post("/predict",(_req,res)=>res.status(429).set("Retry-After","2").json({error:"GPU busy"}));
    const bridge=express();bridge.use(inferenceRouter(await serve(upstream)));const url=await serve(bridge);
    const response=await fetch(`${url}/predict`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:"data:image/png;base64,YWJj",model:"cosmos_full",frame_id:"wanted"})});expect(response.status).toBe(429);expect(response.headers.get("retry-after")).toBe("2");
  });
});
