import express from "express";
import type { Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { recipeLibraryRouter } from "./recipe-library.js";
const servers: Server[] = [];
async function serve(app: express.Express) {
  const server = app.listen(0, "127.0.0.1"); servers.push(server);
  await new Promise<void>((resolve, reject) => { server.once("listening", resolve); server.once("error", reject); });
  const address = server.address(); if (!address || typeof address === "string") throw Error("No port");
  return `http://127.0.0.1:${address.port}`;
}
afterEach(async () => { await Promise.all(servers.splice(0).map(s => new Promise<void>(resolve => s.close(() => resolve())))); vi.unstubAllEnvs(); });
describe("Recipe library", () => {
  it("loads all 52 integrity-checked reference settings, including the missing recipe IDs", async () => {
    const app = express(); app.use(recipeLibraryRouter()); const url = await serve(app);
    const response = await fetch(`${url}/references`); expect(response.status).toBe(200);
    const body = await response.json(); expect(body.recipes).toHaveLength(52);
    expect(body.recipes.map((r: { recipe_id: number }) => r.recipe_id)).toEqual(expect.arrayContaining([41, 50, 60, 99]));
    expect(body.basis).toBe("recipe_settings_not_measured_delivery");
    for (const r of body.recipes) {
      expect(Object.values(r.amounts_ml).reduce((a: number, b) => a + Number(b), 0)).toBeCloseTo(r.total_ml);
      expect(Object.values(r.proportions).reduce((a: number, b) => a + Number(b), 0)).toBeCloseTo(1);
    }
  });
  it("requests only unmatched records, forwards the server token, and reports temporary storage", async () => {
    vi.stubEnv("INFERENCE_TOKEN", "test-private-token");
    const upstream = express(); upstream.get("/api/recipes", (req, res) => {
      expect(req.query.collection).toBe("UNMATCHED"); expect(req.headers.authorization).toBe("Bearer test-private-token");
      res.json({ collection: "UNMATCHED", recipes: [{ id: 100, final_color: "blue", dispenses: [], dispense_count: 0 }] });
    });
    const base = await serve(upstream); const app = express(); app.use(recipeLibraryRouter(base)); const url = await serve(app);
    const response = await fetch(`${url}/candidates`); expect(response.status).toBe(200);
    const body = await response.json(); expect(body.recipes[0].id).toBe(100); expect(body.persistence).toBe("in_memory");
    expect(JSON.stringify(body)).not.toContain("test-private-token");
  });
  it("keeps unavailable candidate data distinct from an empty collection", async () => {
    const upstream = express(); upstream.get("/api/recipes", (_req, res) => res.status(401).json({ error: "Credentials required" }));
    const base = await serve(upstream); const app = express(); app.use(recipeLibraryRouter(base)); const url = await serve(app);
    const response = await fetch(`${url}/candidates`); expect(response.status).toBe(401); expect(await response.json()).toEqual({ error: "Credentials required" });
  });
});
