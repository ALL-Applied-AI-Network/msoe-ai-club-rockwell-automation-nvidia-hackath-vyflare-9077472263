import express from "express";
import type { Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { recordedProducerRouter } from "./recorded-producer.js";
const servers: Server[] = [];
async function serve(app: express.Express) {
  const server = app.listen(0, "127.0.0.1"); servers.push(server);
  await new Promise<void>((resolve, reject) => { server.once("listening", resolve); server.once("error", reject); });
  const address = server.address(); if (!address || typeof address === "string") throw Error("No port");
  return `http://127.0.0.1:${address.port}`;
}
afterEach(async () => { await Promise.all(servers.splice(0).map(s => new Promise<void>(resolve => s.close(() => resolve())))); vi.unstubAllEnvs(); });
describe("Fresh recording producer proxy", () => {
  it("keeps credentials private, forwards asynchronous jobs and polling, and rejects forged inputs", async () => {
    vi.stubEnv("INFERENCE_TOKEN", "private-producer-fixture");
    let starts = 0;
    const python = express(); python.use(express.json());
    python.use((req, _res, next) => { expect(req.headers.authorization).toBe("Bearer private-producer-fixture"); next(); });
    python.get("/api/recipe-workflow/demo/producer/status", (_req, res) => res.json({ enabled: true, available: true }));
    python.post("/api/recipe-workflow/demo/producer/videos/video-1", (req, res) => { starts++; expect(req.body).toEqual({}); res.status(202).json({ state: "processing" }); });
    python.get("/api/recipe-workflow/demo/producer/videos/video-1", (_req, res) => res.json({ state: "completed", assessments: [{ recipe_id: 100 }] }));
    python.get("/api/recipe-workflow/demo/patterns", (_req, res) => res.json({ groups: [{ status: "PENDING_REPEAT", qualifying_fill_count: 1 }] }));
    python.get("/api/recipe-workflow/demo/recipes", (_req, res) => res.json({ recipes: [{ recipe_id: 100 }] }));
    const upstream = await serve(python); const app = express(); app.use(recordedProducerRouter(upstream)); const base = await serve(app);
    expect(await (await fetch(`${base}/status`)).json()).toEqual({ enabled: true, available: true });
    const post = (body: object, origin?: string) => fetch(`${base}/videos/video-1`, { method: "POST", headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}) }, body: JSON.stringify(body) });
    expect((await post({})).status).toBe(202);
    expect((await post({}, "https://untrusted.example")).status).toBe(403);
    expect((await post({ path: "/tmp/forged" })).status).toBe(400);
    expect((await fetch(`${base}/videos/video-99`)).status).toBe(404);
    expect((await (await fetch(`${base}/videos/video-1`)).json()).assessments[0].recipe_id).toBe(100);
    expect((await (await fetch(`${base}/recipes`)).json()).recipes[0].recipe_id).toBe(100);
    expect((await (await fetch(`${base}/patterns`)).json()).groups[0].qualifying_fill_count).toBe(1);
    expect(starts).toBe(1);
  });
  it("preserves service failures", async () => {
    const python = express(); python.get("/api/recipe-workflow/demo/producer/status", (_req, res) => res.status(401).json({ error: "Token required" }));
    const upstream = await serve(python); const app = express(); app.use(recordedProducerRouter(upstream)); const base = await serve(app);
    expect((await fetch(`${base}/status`)).status).toBe(401);
  });
});
