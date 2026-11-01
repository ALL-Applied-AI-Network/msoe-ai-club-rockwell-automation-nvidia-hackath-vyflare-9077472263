import express from "express";
import type { Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { recipeWorkflowRouter } from "./recipe-workflow.js";
const servers: Server[] = [];
async function serve(app: express.Express) {
  const server = app.listen(0, "127.0.0.1"); servers.push(server);
  await new Promise<void>((resolve, reject) => { server.once("listening", resolve); server.once("error", reject); });
  const address = server.address(); if (!address || typeof address === "string") throw Error("No port");
  return `http://127.0.0.1:${address.port}`;
}
afterEach(async () => { await Promise.all(servers.splice(0).map(s => new Promise<void>(resolve => s.close(() => resolve())))); vi.unstubAllEnvs(); });
describe("Recipe assessment proxy", () => {
  it("forwards the private token and fixed reviewed-evidence request without accepting client observations", async () => {
    vi.stubEnv("INFERENCE_TOKEN", "private-test-token");
    let writes = 0;
    const python = express(); python.use(express.json());
    python.get("/api/recipe-workflow/status", (req, res) => { expect(req.headers.authorization).toBe("Bearer private-test-token"); res.json({ persistence: "sqlite" }); });
    python.post("/api/recipe-workflow/recorded/video-1/V1-V01", (req, res) => { writes++; expect(req.body).toEqual({}); expect(req.headers.authorization).toBe("Bearer private-test-token"); res.json({ assessment: { assessment_status: "INSUFFICIENT_EVIDENCE" } }); });
    const upstream = await serve(python); const app = express(); app.use(recipeWorkflowRouter(upstream)); const base = await serve(app);
    expect((await (await fetch(`${base}/status`)).json()).persistence).toBe("sqlite");
    const post = (body: object, origin?: string) => fetch(`${base}/recorded/video-1/V1-V01`, { method: "POST", headers: { "Content-Type": "application/json", ...(origin ? { Origin: origin } : {}) }, body: JSON.stringify(body) });
    expect((await post({})).status).toBe(200);
    expect((await post({}, "https://untrusted.example")).status).toBe(403);
    expect((await post({ dispenses: [] })).status).toBe(400);
    expect(writes).toBe(1);
    expect((await fetch(`${base}/observations`, { method: "POST" })).status).toBe(404);
    expect((await fetch(`${base}/videos/video-3/assessments`)).status).toBe(404);
  });
  it("preserves upstream authentication errors instead of presenting an empty result", async () => {
    const python = express(); python.get("/api/recipe-workflow/status", (_req, res) => res.status(401).json({ error: "Credentials required" }));
    const upstream = await serve(python); const app = express(); app.use(recipeWorkflowRouter(upstream)); const base = await serve(app);
    const result = await fetch(`${base}/status`); expect(result.status).toBe(401); expect(await result.json()).toEqual({ error: "Credentials required" });
  });
});
