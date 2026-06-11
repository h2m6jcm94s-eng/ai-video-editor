import { spawn } from "child_process";

export interface ProbeResult {
  videoCodec: string;
  audioCodec: string;
  duration: number;
  width: number;
  height: number;
  sizeBytes: number;
  averageLuma: number;
}

export async function probe(filePath: string): Promise<ProbeResult> {
  const raw: Record<string, unknown> = await new Promise((resolve, reject) => {
    const proc = spawn(
      "ffprobe",
      ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", filePath],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let out = "";
    let err = "";
    proc.stdout.on("data", (d) => (out += d));
    proc.stderr.on("data", (d) => (err += d));
    proc.on("close", (code) => {
      if (code !== 0) return reject(new Error(`ffprobe exited ${code}: ${err}`));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(new Error("ffprobe invalid JSON"));
      }
    });
  });

  const format = (raw.format as Record<string, unknown>) || {};
  const streams = (raw.streams as Array<Record<string, unknown>>) || [];

  const videoStream = streams.find((s) => s.codec_type === "video");
  const audioStream = streams.find((s) => s.codec_type === "audio");

  // Compute average luma (grayscale brightness) using ffmpeg
  const averageLuma = await computeAverageLuma(filePath);

  return {
    videoCodec: String(videoStream?.codec_name || ""),
    audioCodec: String(audioStream?.codec_name || ""),
    duration: parseFloat(String(format.duration || "0")),
    width: parseInt(String(videoStream?.width || "0"), 10),
    height: parseInt(String(videoStream?.height || "0"), 10),
    sizeBytes: parseInt(String(format.size || "0"), 10),
    averageLuma,
  };
}

async function computeAverageLuma(filePath: string): Promise<number> {
  return new Promise((resolve) => {
    const proc = spawn(
      "ffmpeg",
      ["-i", filePath, "-vf", "scale=100:-1,format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
      { stdio: ["ignore", "pipe", "ignore"] },
    );

    let total = 0;
    let count = 0;
    proc.stdout.on("data", (chunk: Buffer) => {
      for (let i = 0; i < chunk.length; i++) {
        total += chunk[i];
        count++;
      }
    });
    proc.on("close", () => {
      resolve(count > 0 ? total / count : 0);
    });
    proc.on("error", () => resolve(0));
  });
}
