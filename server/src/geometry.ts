import express from "express";

export function geometryRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  router.use(express.json({ limit: "750kb" }));
  router.use((req, res, next) => {
    if (!["POST", "DELETE"].includes(req.method)) { next(); return; }
    const origin = req.get("origin");
    if (origin) {
      try {
        const url = new URL(origin), local = ["localhost", "127.0.0.1", "[::1]", "::1"];
        const dev = local.includes(url.hostname) && local.includes(req.hostname) && url.port === "5173";
        if (url.host !== req.get("host") && !dev) { res.status(403).json({ error: "Cross-origin tracking requests are not allowed." }); return; }
      } catch { res.status(403).json({ error: "Invalid request origin." }); return; }
    }
    next();
  });
  const forward = async (suffix: string, req: express.Request, res: express.Response) => {
    try {
      const headers: Record<string, string> = {};
      if (process.env.INFERENCE_TOKEN) headers.Authorization = `Bearer ${process.env.INFERENCE_TOKEN}`;
      if (req.method === "POST") headers["Content-Type"] = "application/json";
      const response = await fetch(`${baseUrl}/api/geometry${suffix}`, { method: req.method, headers,
        ...(req.method === "POST" ? { body: JSON.stringify(req.body) } : {}), signal: AbortSignal.timeout(10000) });
      if (response.status === 204) { res.sendStatus(204); return; }
      const body = await response.json().catch(() => null);
      res.status(body ? response.status : 502).json(body ?? { error: "Invalid tracking service response." });
    } catch { res.status(503).json({ error: "Automatic tracking service is unavailable." }); }
  };
  router.get("/status", (req, res) => forward("/status", req, res));
  router.post("/sessions", (req, res) => forward("/sessions", req, res));
  router.route("/sessions/:sessionId").all((req, res, next) => {
    if (!/^[a-f0-9]{32}$/.test(req.params.sessionId)) { res.status(400).json({ error: "Invalid tracking session." }); return; } next();
  }).delete((req, res) => forward(`/sessions/${req.params.sessionId}`, req, res));
  router.post("/sessions/:sessionId/frame", (req, res) => {
    if (!/^[a-f0-9]{32}$/.test(req.params.sessionId)) { res.status(400).json({ error: "Invalid tracking session." }); return; }
    void forward(`/sessions/${req.params.sessionId}/frame`, req, res);
  });
  router.route("/recordings/:videoId").all((req, res, next) => {
    if (!/^video-[12]$/.test(req.params.videoId)) { res.status(404).json({ error: "Unsupported recording." }); return; } next();
  }).get((req, res) => forward(`/recordings/${req.params.videoId}`, req, res))
    .post((req, res) => forward(`/recordings/${req.params.videoId}`, req, res));
  return router;
}
