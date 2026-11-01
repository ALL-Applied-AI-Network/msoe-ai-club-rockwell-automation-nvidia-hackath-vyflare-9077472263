import express from "express";

export function recipeWorkflowRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  const forward = async (upstream: string, res: express.Response, method = "GET") => {
    try {
      const headers: Record<string, string> = process.env.INFERENCE_TOKEN ? { Authorization: `Bearer ${process.env.INFERENCE_TOKEN}` } : {};
      if (method === "POST") headers["Content-Type"] = "application/json";
      const response = await fetch(`${baseUrl}/api/recipe-workflow${upstream}`, { method, headers,
        ...(method === "POST" ? { body: "{}" } : {}), signal: AbortSignal.timeout(15000) });
      const body = await response.json().catch(() => null);
      if (!body) { res.status(502).json({ error: "Recipe service returned an invalid response." }); return; }
      res.status(response.status).json(body);
    } catch { res.status(503).json({ error: "Recipe assessment service unavailable. Check the Python connection." }); }
  };
  router.get("/status", (_req, res) => forward("/status", res));
  router.get("/videos/:videoId/assessments", (req, res) => {
    if (!/^video-[12]$/.test(req.params.videoId)) { res.status(404).json({ error: "Unknown reviewed video" }); return; }
    return forward(`/videos/${req.params.videoId}/assessments`, res);
  });
  router.post("/recorded/:videoId/:vialId", express.json({ limit: "1kb" }), (req, res) => {
    const origin = req.get("origin");
    if (origin) {
      try {
        const url = new URL(origin);
        const local = ["localhost", "127.0.0.1", "[::1]", "::1"];
        const dev = local.includes(url.hostname) && local.includes(req.hostname) && url.port === "5173";
        if (url.host !== req.get("host") && !dev) { res.status(403).json({ error: "Cross-origin recipe writes are not allowed." }); return; }
      } catch { res.status(403).json({ error: "Invalid request origin." }); return; }
    }
    if (!/^video-[12]$/.test(req.params.videoId) || !/^V[12]-V[0-9]{2}$/.test(req.params.vialId)) {
      res.status(404).json({ error: "Unknown reviewed vial" }); return;
    }
    if (!req.body || Array.isArray(req.body) || Object.keys(req.body).length) {
      res.status(400).json({ error: "Reviewed observations are loaded server-side; send an empty JSON object." }); return;
    }
    return forward(`/recorded/${req.params.videoId}/${req.params.vialId}`, res, "POST");
  });
  return router;
}
