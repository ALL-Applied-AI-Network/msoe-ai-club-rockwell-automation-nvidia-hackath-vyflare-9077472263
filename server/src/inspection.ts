import express from "express";
import path from "node:path";
import { readFileSync, existsSync } from "node:fs";

export function inspectionRouter() {
  const router = express.Router();
  const manifestPath = path.resolve("evidence/recorded-inspection.json");
  router.get("/evidence", (_req, res) => {
    try {
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
      for (let n=3;n<=5;n++) {
        const filename=`vial_fill_video_${n}.mp4`;
        if (existsSync(path.resolve("cosmos-original-dataset/videos",filename))) manifest.videos.push({id:`video-${n}`,name:`Video ${n}`,filename,url:`/api/inspection/videos/video-${n}`,duration:0,vials:[]});
      }
      res.json({ ...manifest, videos: manifest.videos.map((video: { filename: string }) => ({ ...video,
        available: existsSync(path.resolve("cosmos-original-dataset/videos", video.filename)) })) });
    } catch { res.status(503).json({ error: "Recorded inspection annotations are unavailable." }); }
  });
  router.get("/videos/:id", (req, res) => {
    const files: Record<string, string> = { "video-1": "vial_fill_video_1.mp4", "video-2": "vial_fill_video_2.mp4" };
    for (let n=3;n<=5;n++) files[`video-${n}`]=`vial_fill_video_${n}.mp4`;
    const filename = files[req.params.id];
    if (!filename) { res.status(404).json({ error: "Unknown recorded video." }); return; }
    const source = path.resolve("cosmos-original-dataset/videos", filename);
    if (!existsSync(source)) { res.status(404).json({ error: "Source video is not installed on this server." }); return; }
    res.sendFile(filename, { root: path.dirname(source) });
  });
  return router;
}
