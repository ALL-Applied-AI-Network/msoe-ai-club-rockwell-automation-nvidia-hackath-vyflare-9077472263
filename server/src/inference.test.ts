import express from "express";
import { afterEach, describe, expect, it } from "vitest";
import type { Server } from "node:http";
import { inferenceRouter } from "./inference.js";

const servers: Server[] = [];
async function serve(app: express.Express) {
  const server = app.listen(0, "127.0.0.1"); servers.push(server);
  await new Promise<void>(resolve => server.once("listening", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("No port");
  return `http://127.0.0.1:${address.port}`;
}
afterEach(async () => { await Promise.all(servers.splice(0).map(server => new Promise<void>(resolve => server.close(() => resolve())))); });
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
});
