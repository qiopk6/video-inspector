export type Severity = "pass" | "warning" | "failure" | "info";
export type JobStatus = "queued" | "analyzing" | "completed" | "failed" | "cancelled";

export interface TimeSegment {
  start: number;
  end: number;
  duration: number;
}

export interface Finding {
  code: string;
  title: string;
  severity: Severity;
  message: string;
  segments: TimeSegment[];
  details: Record<string, unknown>;
}

export interface MediaMetadata {
  path: string;
  filename: string;
  format_name: string;
  duration: number;
  size_bytes: number;
  overall_bitrate_kbps: number;
  video_codec: string;
  width: number;
  height: number;
  frame_rate: number;
  video_bitrate_kbps: number;
  pixel_format: string;
  audio_codec: string;
  audio_sample_rate: number;
  audio_channels: number;
  audio_bitrate_kbps: number;
  has_video: boolean;
  has_audio: boolean;
}

export interface AnalysisResult {
  metadata: MediaMetadata;
  status: Severity;
  score: number;
  findings: Finding[];
  elapsed_seconds: number;
  analyzed_at: string;
  tool_version: string;
}

export interface VideoJob {
  id: string;
  filename: string;
  size_bytes: number;
  status: JobStatus;
  progress: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  group: string | null;
  batch_id: string;
  batch_name: string;
  batch_created_at: string;
  batch_file_count: number;
  result: AnalysisResult | null;
}

export type QueueFilter = "all" | "issues" | "passed";
