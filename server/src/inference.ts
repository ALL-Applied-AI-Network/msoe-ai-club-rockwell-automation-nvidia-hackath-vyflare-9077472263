import express from "express";

export function inferenceRouter(baseUrl = process.env.INFERENCE_URL ?? "http://127.0.0.1:8000") {
  const router = express.Router();
  const authHeaders = (): Record<string, string> => process.env.INFERENCE_TOKEN ? { Authorization: `Bearer ${process.env.INFERENCE_TOKEN}` } : {};
  const forward = async (response: Response, res: express.Response) => {
    if (response.headers.get("retry-after")) res.setHeader("Retry-After", response.headers.get("retry-after")!);
    const body = await response.json().catch(() => null);
    if (body === null) { res.status(502).json({ error: "Python returned an invalid response." }); return; }
    res.status(response.status).json(body);
  };
  for (const path of ["/model4", "/model4/recipes"]) {
    router.get(path, async (_req, res) => {
      try {
        await forward(await fetch(`${baseUrl}${path}`, { headers: authHeaders(), signal: AbortSignal.timeout(5000) }), res);
      } catch { res.status(503).json({ error: "Model 4 is unavailable. Check the Python connection." }); }
    });
  }
  router.post("/model4", express.json({ limit: "17mb" }), async (req, res) => {
    const { images, frame_id, vial_id, batch_id, batch_position, recipe_id, camera_profile } = req.body ?? {};
    if (![frame_id, vial_id, batch_id].every(value => typeof value === "string" && value.trim().length > 0 && value.trim().length <= 128)
      || !Number.isInteger(batch_position) || batch_position < 1 || batch_position > 999999999
      || !Number.isInteger(recipe_id) || recipe_id < 1 || recipe_id > 999999999
      || camera_profile !== "vial-fill-640x480" || !Array.isArray(images) || images.length !== 3) {
      res.status(400).json({ error: "Provide three frames, vial and batch identities, a positive batch position, a comparison recipe, and the registered camera profile." }); return;
    }
    const files: { bytes: Buffer; type: string }[] = [];
    for (const image of images) {
      if (typeof image !== "string" || !/^data:image\/(jpeg|png);base64,[A-Za-z0-9+/]+=*$/.test(image)) {
        res.status(400).json({ error: "Model 4 frames must be JPEG or PNG images." }); return;
      }
      const bytes = Buffer.from(image.slice(image.indexOf(",") + 1), "base64");
      if (!bytes.length || bytes.length > 4 * 1024 * 1024) { res.status(413).json({ error: "Each frame must be at most 4 MiB." }); return; }
      files.push({ bytes, type: image.startsWith("data:image/png") ? "image/png" : "image/jpeg" });
    }
    if (files.reduce((sum, file) => sum + file.bytes.length, 0) > 11 * 1024 * 1024) {
      res.status(413).json({ error: "The three frames must total at most 11 MiB." }); return;
    }
    const body = new FormData();
    for (const [key, value] of Object.entries({ frame_id: frame_id.trim(), vial_id: vial_id.trim(), batch_id: batch_id.trim(), batch_position, recipe_id, camera_profile })) body.append(key, String(value));
    files.forEach((file, i) => body.append("images", new Blob([new Uint8Array(file.bytes)], { type: file.type }), `post-fill-${i + 1}.${file.type === "image/png" ? "png" : "jpg"}`));
    try {
      await forward(await fetch(`${baseUrl}/predict/model4`, { method: "POST", body, headers: authHeaders(), signal: AbortSignal.timeout(30000) }), res);
    } catch { res.status(503).json({ error: "Model 4 inference unavailable or timed out. Check the Python service." }); }
  });
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
    const { image, model, frame_id, prompt = "Describe the visible liquid and acknowledge uncertainty." } = req.body ?? {};
    if (typeof image !== "string" || !/^data:image\/(jpeg|png);base64,[A-Za-z0-9+/]+=*$/.test(image)
        || typeof model !== "string" || !["measurements", "resnet18", "cosmos", "cosmos_lite", "cosmos_full"].includes(model)
        || typeof prompt !== "string" || !prompt.trim() || prompt.length > 2000
        || (frame_id !== undefined && (typeof frame_id !== "string" || !frame_id.trim() || frame_id.length > 128))) {
      res.status(400).json({ error: "Provide a JPEG/PNG image, supported model, and prompt of 1–2000 characters." }); return;
    }
    const bytes = Buffer.from(image.slice(image.indexOf(",")+1), "base64");
    if (!bytes.length || bytes.length > 4*1024*1024) { res.status(413).json({error: "Image must be at most 4 MiB."}); return; }
    const body = new FormData();
    body.append("image", new Blob([bytes], {type: image.startsWith("data:image/png") ? "image/png" : "image/jpeg"}), "upload");
    body.append("model", model); body.append("prompt", prompt); const evidenceId = frame_id?.trim() ?? crypto.randomUUID(); body.append("frame_id", evidenceId);
    try {
      const headers: Record<string, string> = {};
      if (process.env.INFERENCE_TOKEN) headers.Authorization = `Bearer ${process.env.INFERENCE_TOKEN}`;
      const response = await fetch(`${baseUrl}/predict`, { method: "POST", body, headers, signal: AbortSignal.timeout(125000) });
      const result = await response.json();
      if (response.ok && (result?.frame_id !== evidenceId || result?.model !== model)) { res.status(502).json({ error: "Inference response does not match the requested evidence or model." }); return; }
      if (response.headers.get("retry-after")) res.setHeader("Retry-After", response.headers.get("retry-after")!);
      res.status(response.status).json(result);
    } catch {
      res.status(503).json({ error: "Inference unavailable or timed out. Check the Python service and selected model." });
    }
  });
  return router;
}
