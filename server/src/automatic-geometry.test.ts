import { afterEach, describe, expect, it, vi } from "vitest";
import express from "express";
import type { Server } from "node:http";
import { geometryRouter } from "./geometry.js";
import { geometryAt, type GeometryFrame } from "../../client/src/inspection/automaticGeometry.js";

const servers: Server[] = [];
afterEach(async () => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); await Promise.all(servers.map(s => new Promise<void>(resolve => s.close(() => resolve())))); servers.length = 0; });
async function app() {
  const app = express(); app.use("/api/geometry", geometryRouter("http://geometry-service"));
  const server = await new Promise<Server>(resolve => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); }); servers.push(server);
  const address = server.address(); if (!address || typeof address === "string") throw Error("Missing test server");
  return `http://127.0.0.1:${address.port}/api/geometry`;
}
const actualFetch = globalThis.fetch;
describe("Pixel geometry routing and playback", () => {
  it("forwards bounded pixels with server-only credentials", async () => {
    const base = await app(); vi.stubEnv("INFERENCE_TOKEN", "private-test-token");
    const upstream = vi.fn(async (_url: string, _options: RequestInit) => new Response(JSON.stringify({ detections: [] }), { status: 200, headers: { "Content-Type": "application/json" } })); vi.stubGlobal("fetch", upstream);
    const body = { image: "data:image/jpeg;base64,pixels", captured_at: .25 };
    const r = await actualFetch(`${base}/sessions/${"a".repeat(32)}/frame`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    expect(r.status).toBe(200); expect(upstream.mock.calls[0]?.[0]).toBe(`http://geometry-service/api/geometry/sessions/${"a".repeat(32)}/frame`);
    const call = upstream.mock.calls[0] as unknown as [string, RequestInit]; expect(call[1].headers).toMatchObject({ Authorization: "Bearer private-test-token" }); expect(JSON.parse(call[1].body as string)).toEqual(body);
    expect(JSON.stringify(await r.json())).not.toContain("private-test-token");
  });
  it("rejects cross-origin requests and invalid session/recording paths", async () => {
    const base = await app(); const upstream = vi.fn(); vi.stubGlobal("fetch", upstream);
    const foreign = await actualFetch(`${base}/sessions`, { method: "POST", headers: { Origin: "https://foreign.example", "Content-Type": "application/json" }, body: "{}" });
    expect(foreign.status).toBe(403);
    expect((await actualFetch(`${base}/sessions/bad/frame`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).status).toBe(400);
    expect((await actualFetch(`${base}/recordings/video-3`)).status).toBe(404); expect(upstream).not.toHaveBeenCalled();
  });
  it("returns unavailable instead of simulated tracking", async () => {
    const base = await app(); vi.stubGlobal("fetch", vi.fn().mockRejectedValue(Error("offline")));
    expect((await actualFetch(`${base}/status`)).status).toBe(503);
  });
  it("handles browser media-clock rounding at native frame timestamps", () => {
    const frame = { captured_at: 22.2666666667, width: 640, height: 480, detections: [], issues: [] } satisfies GeometryFrame;
    expect(geometryAt([frame], 22.266666)).toBe(frame);
    expect(geometryAt([frame], 22.26)).toBeUndefined();
  });
  it("selects only recent preceding frames without extrapolating across gaps", () => {
    const frames = [1, 1.25, 2].map(captured_at => ({ captured_at, width: 640, height: 480, detections: [], issues: [] } satisfies GeometryFrame));
    expect(geometryAt(frames, .9)).toBeUndefined(); expect(geometryAt(frames, 1.2)).toBe(frames[0]);
    expect(geometryAt(frames, 1.8)).toBeUndefined(); expect(geometryAt(frames, 2.5)).toBeUndefined();
  });
});
