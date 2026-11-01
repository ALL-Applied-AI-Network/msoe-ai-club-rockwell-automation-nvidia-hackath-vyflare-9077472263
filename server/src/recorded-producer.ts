import express from "express";

// Explicit routes only: no arbitrary upstream URL, file path or measurement input.
export function recordedProducerRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  router.use(express.json({ limit: "1kb" }));
  router.use((req, res, next) => {
    if (req.method !== "POST") { next(); return; }
    const origin = req.get("origin");
    if (origin) {
      try {
        const url = new URL(origin), local = ["localhost", "127.0.0.1", "[::1]", "::1"];
        const dev = local.includes(url.hostname) && local.includes(req.hostname) && url.port === "5173";
        if (url.host !== req.get("host") && !dev) { res.status(403).json({ error: "Cross-origin recipe writes are not allowed." }); return; }
      } catch { res.status(403).json({ error: "Invalid request origin." }); return; }
    }
    if (!req.body || Array.isArray(req.body) || Object.keys(req.body).length) {
      res.status(400).json({ error: "Send an empty JSON object. Videos and detector settings are selected server-side." }); return;
    }
    next();
  });
  const forward = async (suffix: string, method: string, res: express.Response) => {
    try {
      const headers: Record<string, string> = {};
      if (process.env.INFERENCE_TOKEN) headers.Authorization = `Bearer ${process.env.INFERENCE_TOKEN}`;
      if (method === "POST") headers["Content-Type"] = "application/json";
      const response = await fetch(`${baseUrl}/api/recipe-workflow/demo${suffix}`, {
        method, headers, ...(method === "POST" ? { body: "{}" } : {}), signal: AbortSignal.timeout(15000)
      });
      const body = await response.json().catch(() => null);
      res.status(body ? response.status : 502).json(body ?? { error: "Invalid observation service response." });
    } catch { res.status(503).json({ error: "Recorded observation service is unavailable." }); }
  };
  router.get("/status", (_req, res) => forward("/producer/status", "GET", res));
  router.get("/patterns", (_req, res) => forward("/patterns", "GET", res));
  router.get("/recipes", (_req, res) => forward("/recipes", "GET", res));
  router.route("/videos/:videoId").all((req, res, next) => {
    if (!/^video-[12]$/.test(req.params.videoId)) { res.status(404).json({ error: "Unsupported recorded video." }); return; }
    next();
  }).get((req, res) => forward(`/producer/videos/${req.params.videoId}`, "GET", res))
    .post((req, res) => forward(`/producer/videos/${req.params.videoId}`, "POST", res));
  return router;
}
