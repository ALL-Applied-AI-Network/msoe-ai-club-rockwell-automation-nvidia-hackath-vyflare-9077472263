import express from "express";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

export function recipeLibraryRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  router.get("/references", (_req, res) => {
    try {
      const bytes = readFileSync("backend/model4_assets/recipes.json");
      const manifest = JSON.parse(readFileSync("backend/model4_assets/manifest.json", "utf8"));
      if (createHash("sha256").update(bytes).digest("hex") !== manifest.sha256["recipes.json"]) throw Error("Reference integrity mismatch");
      const catalog = JSON.parse(bytes.toString("utf8"));
      const recipes = Object.entries(catalog.recipes).map(([id, value]) => {
        const r = value as { amounts_ml: Record<string, number>; total_ml: number; expected_order: string[] };
        return { recipe_id: Number(id), ...r, proportions: Object.fromEntries(Object.entries(r.amounts_ml).map(([t, amount]) => [t, amount / r.total_ml])) };
      }).sort((a, b) => a.recipe_id - b.recipe_id);
      res.json({ source: `${catalog.source_workbook}/${catalog.source_sheet}`, basis: "recipe_settings_not_measured_delivery", recipes });
    } catch { res.status(503).json({ error: "The reference recipe catalog is unavailable or failed its integrity check." }); }
  });
  router.get("/candidates", async (_req, res) => {
    try {
      const headers: Record<string, string> = process.env.INFERENCE_TOKEN ? { Authorization: `Bearer ${process.env.INFERENCE_TOKEN}` } : {};
      const response = await fetch(`${baseUrl}/api/recipes?collection=UNMATCHED`, { headers, signal: AbortSignal.timeout(5000) });
      const body = await response.json();
      if (!response.ok) { res.status(response.status).json({ error: body.error ?? "Candidate service unavailable." }); return; }
      if (body.collection !== "UNMATCHED" || !Array.isArray(body.recipes)) throw Error("Invalid candidate response");
      res.json({ ...body, persistence: response.headers.get("x-recipe-storage") ?? "in_memory", source: "observation_matching_service" });
    } catch { res.status(503).json({ error: "The unmatched-candidate service is unavailable. Check the Python connection." }); }
  });
  return router;
}
