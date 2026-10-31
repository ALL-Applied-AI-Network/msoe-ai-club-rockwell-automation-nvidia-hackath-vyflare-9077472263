export const tanks = ["T100", "T200", "T400"] as const;
export type Tank = typeof tanks[number];
export type Mixture = Record<Tank, number>;
export type Frame = { dataUrl: string; label: string; requestedTime?: number };
export type Vial = { id: string; label: string; appearance: string; finalSampleSeconds: number; flowEndUpper: number; stationaryUntil: number;
  pulses: { order: number; startLower: number; startUpper: number; endLower: number; endUpper: number; appearance: string }[] };
export type RecordedVideo = { id: string; name: string; url: string; duration: number; available: boolean; vials: Vial[] };
export type Health = { available: boolean; mode: string; models: string[]; busy?: boolean; message?: string };
export type Recipe = { recipe_id: number; amounts_ml: Mixture; total_ml: number; proportions: Mixture };
export type Model4Response = { frame_id: string; vial_id: string; batch_id: string; batch_position: number; mode: string; inference_ms: number;
  result: { mock?: boolean; message?: string; expected: Recipe; checkpoint: null | { estimated_percentages: Mixture; signed_difference_percentage_points: Mixture; feature_extrapolation: boolean };
    review: { status: string; required: boolean; expected_transition_contamination: boolean; automatic_release: boolean };
    model_metadata: { checkpoint_id: string; checkpoint_sha256: string }; interpretation?: string } };

export async function readResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok || body === null) throw new Error(body?.error ?? `Request failed (${response.status}).`);
  return body as T;
}

export async function readFrame(file: File): Promise<Frame> {
  if (!["image/jpeg", "image/png"].includes(file.type) || file.size > 4 * 1024 * 1024) throw new Error("Each frame must be a JPEG or PNG up to 4 MiB.");
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error("Could not read frame.")); reader.readAsDataURL(file);
  });
  await new Promise<void>((resolve, reject) => {
    const image = new Image(); image.onload = () => image.naturalWidth === 640 && image.naturalHeight === 480 ? resolve() : reject(new Error("Frames must be 640 × 480. Images are not resized."));
    image.onerror = () => reject(new Error("Could not decode frame.")); image.src = dataUrl;
  });
  return { dataUrl, label: file.name };
}

export const timeLabel = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toFixed(2).padStart(5, "0")}`;
