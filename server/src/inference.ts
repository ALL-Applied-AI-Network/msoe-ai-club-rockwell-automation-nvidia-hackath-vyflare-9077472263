import express from "express";

export function inferenceRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  router.get("/status", async (_req, res) => {
    try {
      const response = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
      if (!response.ok) throw new Error("Backend not ready");
      const health = await response.json() as {mode: string; models: string[]; busy: boolean};
      if (!Array.isArray(health.models) || !["real", "mock"].includes(health.mode)) throw new Error("Invalid backend");
      res.json({ available: true, ...health });
    } catch {
      res.json({ available: false, mode: "unavailable", models: [], message: "Start the Python backend, or set INFERENCE_URL to its private address." });
    }
  });
  router.post("/predict", express.json({ limit: "7mb" }), async (req, res) => {
    const { image, model, prompt = "Describe the visible liquid and acknowledge uncertainty." } = req.body ?? {};
    if (typeof image !== "string" || !/^data:image\/(jpeg|png);base64,[A-Za-z0-9+/]+=*$/.test(image)
        || typeof model !== "string" || !["measurements", "resnet18", "cosmos", "cosmos_lite", "cosmos_full"].includes(model)
        || typeof prompt !== "string" || !prompt.trim() || prompt.length > 2000) {
      res.status(400).json({ error: "Provide a JPEG/PNG image, supported model, and prompt of 1–2000 characters." }); return;
    }
    const bytes = Buffer.from(image.slice(image.indexOf(",")+1), "base64");
    if (!bytes.length || bytes.length > 4*1024*1024) { res.status(413).json({error: "Image must be at most 4 MiB."}); return; }
    const body = new FormData();
    body.append("image", new Blob([bytes], {type: image.startsWith("data:image/png") ? "image/png" : "image/jpeg"}), "upload");
    body.append("model", model); body.append("prompt", prompt); body.append("frame_id", crypto.randomUUID());
    try {
      const headers: Record<string, string> = {};
      if (process.env.INFERENCE_TOKEN) headers.Authorization = `Bearer ${process.env.INFERENCE_TOKEN}`;
      const response = await fetch(`${baseUrl}/predict`, { method: "POST", body, headers, signal: AbortSignal.timeout(125000) });
      const result = await response.json();
      if (response.headers.get("retry-after")) res.setHeader("Retry-After", response.headers.get("retry-after")!);
      res.status(response.status).json(result);
    } catch {
      res.status(503).json({ error: "Inference unavailable or timed out. Check the Python service and selected model." });
    }
  });
  return router;
}
