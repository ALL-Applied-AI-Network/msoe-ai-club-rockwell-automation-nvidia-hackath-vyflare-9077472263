import express from "express";

// Explicit routes only: no arbitrary upstream URL, file path or measurement input.
export const recordingId = /^(?:video-[1-5]|recording-[0-9a-f]{64})$/;

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
    if (req.path !== "/recordings" && (!req.body || Array.isArray(req.body) || Object.keys(req.body).length)) {
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
  router.post("/recordings", (req,res,next) => {
    const local = ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(req.socket.remoteAddress ?? "") && ["127.0.0.1", "localhost", "[::1]"].includes(req.hostname);
    if (!local) { res.status(403).json({ error: "Opening new recordings currently requires a local inspection console. Public uploads need authenticated deployment configuration." }); return; }
    next();
  }, express.raw({ type: ["video/mp4", "video/webm", "video/quicktime"], limit: "128mb" }), async (req,res) => {
    if (!Buffer.isBuffer(req.body) || !req.body.length) { res.status(400).json({ error: "Choose a nonempty MP4, MOV or WebM recording." }); return; }
    const type = req.get("content-type")?.split(";")[0];
    if (!["video/mp4", "video/webm", "video/quicktime"].includes(type ?? "")) { res.status(415).json({ error: "Unsupported recording type." }); return; }
    const headers: Record<string,string> = { "Content-Type": type!, "X-Recording-Name": (req.get("x-recording-name") ?? "Opened Recording").slice(0,1000) };
    if (process.env.INFERENCE_TOKEN) headers.Authorization = `Bearer ${process.env.INFERENCE_TOKEN}`;
    try {
      const response = await fetch(`${baseUrl}/api/recipe-workflow/demo/producer/recordings`, { method: "POST", headers, body: new Uint8Array(req.body), signal: AbortSignal.timeout(120000) });
      const body = await response.json(); res.status(response.status).json(body);
    } catch { res.status(503).json({ error: "Could not register recording. Check the Python connection." }); }
  });
  router.post("/videos/:videoId/ensure", (req,res) => {
    if (!recordingId.test(req.params.videoId)) {res.status(404).json({error:"Unknown recording"}); return;}
    return forward(`/producer/videos/${req.params.videoId}/ensure`, "POST", res);
  });
  router.get("/status", (_req, res) => forward("/producer/status", "GET", res));
  router.get("/patterns", (_req, res) => forward("/patterns", "GET", res));
  router.get("/recipes", (_req, res) => forward("/recipes", "GET", res));
  router.route("/videos/:videoId").all((req, res, next) => {
    if (!recordingId.test(req.params.videoId)) { res.status(404).json({ error: "Unsupported recorded video." }); return; }
    next();
  }).get((req, res) => forward(`/producer/videos/${req.params.videoId}`, "GET", res))
    .post((req, res) => forward(`/producer/videos/${req.params.videoId}`, "POST", res));
  return router;
}
