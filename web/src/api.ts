import type { VideoJob } from "./types";

async function messageFrom(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || `请求失败 (${response.status})`;
  } catch {
    return `请求失败 (${response.status})`;
  }
}

export async function getJobs(): Promise<VideoJob[]> {
  const response = await fetch("/api/jobs", { cache: "no-store" });
  if (!response.ok) throw new Error(await messageFrom(response));
  const payload = (await response.json()) as { jobs: VideoJob[] };
  return payload.jobs;
}

export async function sendHeartbeat(): Promise<void> {
  const response = await fetch("/api/session/heartbeat", {
    method: "POST",
    cache: "no-store",
    keepalive: true,
  });
  if (!response.ok) throw new Error(await messageFrom(response));
}

export async function exitApplication(): Promise<void> {
  const response = await fetch("/api/session/exit", {
    method: "POST",
    keepalive: true,
  });
  if (!response.ok) throw new Error(await messageFrom(response));
}

export function uploadVideos(files: File[], onProgress: (value: number) => void): Promise<VideoJob[]> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    request.open("POST", "/api/jobs");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        const payload = JSON.parse(request.responseText) as { jobs: VideoJob[] };
        resolve(payload.jobs);
      } else {
        try {
          const payload = JSON.parse(request.responseText) as { detail?: string };
          reject(new Error(payload.detail || `上传失败 (${request.status})`));
        } catch {
          reject(new Error(`上传失败 (${request.status})`));
        }
      }
    });
    request.addEventListener("error", () => reject(new Error("无法连接本地检测服务")));
    request.send(body);
  });
}

export async function addHlsDirectory(path: string): Promise<VideoJob> {
  const response = await fetch("/api/hls/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!response.ok) throw new Error(await messageFrom(response));
  const payload = (await response.json()) as { jobs: VideoJob[] };
  return payload.jobs[0];
}

export function uploadHlsDirectory(files: File[], onProgress: (value: number) => void): Promise<VideoJob[]> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const body = new FormData();
    const sourcePaths = files.map((file) => file.webkitRelativePath || file.name);
    const firstParts = sourcePaths[0]?.split("/") || [];
    const directoryName = firstParts.length > 1 ? firstParts[0] : "HLS";
    const relativePaths = sourcePaths.map((path) => {
      const parts = path.split("/").filter(Boolean);
      return parts.length > 1 ? parts.slice(1).join("/") : parts[0];
    });

    files.forEach((file) => body.append("files", file, file.name));
    body.append("relative_paths", JSON.stringify(relativePaths));
    body.append("directory_name", directoryName);
    request.open("POST", "/api/hls/upload");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    request.addEventListener("load", () => {
      if (request.status >= 200 && request.status < 300) {
        const payload = JSON.parse(request.responseText) as { jobs: VideoJob[] };
        resolve(payload.jobs);
      } else {
        try {
          const payload = JSON.parse(request.responseText) as { detail?: string };
          reject(new Error(payload.detail || `上传失败 (${request.status})`));
        } catch {
          reject(new Error(`上传失败 (${request.status})`));
        }
      }
    });
    request.addEventListener("error", () => reject(new Error("无法连接本地检测服务")));
    request.send(body);
  });
}

export async function cancelJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  if (!response.ok) throw new Error(await messageFrom(response));
}

export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await messageFrom(response));
}

export async function clearFinishedJobs(): Promise<{ deleted: number; remaining: number }> {
  const response = await fetch("/api/jobs", { method: "DELETE" });
  if (!response.ok) throw new Error(await messageFrom(response));
  return (await response.json()) as { deleted: number; remaining: number };
}

export async function getJobLog(jobId: string): Promise<string> {
  const response = await fetch(`/api/jobs/${jobId}/log`, { cache: "no-store" });
  if (!response.ok) throw new Error(await messageFrom(response));
  const payload = (await response.json()) as { log: string };
  return payload.log;
}
