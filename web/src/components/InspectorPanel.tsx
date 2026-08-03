import { useEffect, useState } from "react";
import {
  DownloadSimple,
  FileMagnifyingGlass,
  Prohibit,
  SpinnerGap,
  Trash,
  WarningCircle,
} from "@phosphor-icons/react";
import { getJobLog } from "../api";
import type { AnalysisResult, Severity, VideoJob } from "../types";
import { Timeline } from "./Timeline";

interface Props {
  job: VideoJob | null;
  view: "overview" | "log";
  onView: (view: "overview" | "log") => void;
  onCancel: (job: VideoJob) => void;
  onDelete: (job: VideoJob) => void;
}

const severityText: Record<Severity, string> = {
  pass: "通过",
  warning: "需要复核",
  failure: "不通过",
  info: "信息",
};

function duration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = Math.floor(seconds % 60);
  return [hours, minutes, remaining].map((value) => value.toString().padStart(2, "0")).join(":");
}

function number(value: number, digits = 0): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: digits }).format(value);
}

function Metadata({ result }: { result: AnalysisResult }) {
  const media = result.metadata;
  const items = [
    ["时长", duration(media.duration)],
    ["画面", `${media.width} x ${media.height}`],
    ["帧率", `${number(media.frame_rate, 2)} fps`],
    ["视频码率", media.video_bitrate_kbps ? `${number(media.video_bitrate_kbps)} kbps` : "未提供"],
    ["视频编码", media.video_codec || "无"],
    ["像素格式", media.pixel_format || "未提供"],
    ["音频编码", media.audio_codec || "无音频轨"],
    ["采样率", media.audio_sample_rate ? `${number(media.audio_sample_rate)} Hz` : "未提供"],
  ];
  return (
    <section className="metadata-section" aria-labelledby="metadata-title">
      <h2 id="metadata-title">媒体信息</h2>
      <dl className="metadata-grid">
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Findings({ result }: { result: AnalysisResult }) {
  return (
    <section className="findings-section" aria-labelledby="findings-title">
      <div className="section-heading-row">
        <h2 id="findings-title">检测明细</h2>
        <span>{result.findings.length} 项</span>
      </div>
      <div className="findings-table-wrap">
        <table className="findings-table">
          <thead>
            <tr><th scope="col">结论</th><th scope="col">检测项</th><th scope="col">说明</th></tr>
          </thead>
          <tbody>
            {result.findings.map((finding) => (
              <tr key={finding.code}>
                <td><span className={`finding-status status-${finding.severity}`}>{severityText[finding.severity]}</span></td>
                <th scope="row">{finding.title}</th>
                <td>{finding.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function InspectorPanel({ job, view, onView, onCancel, onDelete }: Props) {
  const [log, setLog] = useState("");
  const [logError, setLogError] = useState("");

  useEffect(() => {
    setLog("");
    setLogError("");
    if (!job || view !== "log" || job.status !== "completed") return;
    let active = true;
    getJobLog(job.id)
      .then((value) => active && setLog(value))
      .catch((error: Error) => active && setLogError(error.message));
    return () => { active = false; };
  }, [job?.id, job?.status, view]);

  function handleTabKey(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = Array.from(event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]') || []);
    const current = tabs.indexOf(event.currentTarget);
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[next]?.focus();
    tabs[next]?.click();
  }

  if (!job) {
    return (
      <main className="inspector-panel inspector-empty" id="main-content">
        <FileMagnifyingGlass size={40} weight="duotone" aria-hidden="true" />
        <h1>选择一条检测记录</h1>
        <p>结果、时间尺和媒体信息会显示在这里。</p>
      </main>
    );
  }

  if (job.status === "queued" || job.status === "analyzing") {
    return (
      <main className="inspector-panel running-state" id="main-content">
        <div className="running-heading">
          <SpinnerGap className={job.status === "analyzing" ? "spin" : ""} size={28} aria-hidden="true" />
          <div><h1>{job.filename}</h1><p>{job.status === "queued" ? "等待前面的任务完成" : "正在逐帧检测视频"}</p></div>
        </div>
        <div className="large-progress">
          <div><span>检测进度</span><strong>{job.progress}%</strong></div>
          <progress max="100" value={job.progress} aria-label="检测进度" />
        </div>
        <button className="button button-secondary" type="button" onClick={() => onCancel(job)}>
          <Prohibit size={18} aria-hidden="true" />取消检测
        </button>
      </main>
    );
  }

  if (job.status === "failed" || job.status === "cancelled") {
    return (
      <main className="inspector-panel error-state" id="main-content">
        <WarningCircle size={34} aria-hidden="true" />
        <h1>{job.status === "cancelled" ? "检测已取消" : "无法完成检测"}</h1>
        <p>{job.error || (job.status === "cancelled" ? "该任务没有生成检测报告。" : "检查文件是否损坏或格式是否受支持。")}</p>
        <button className="button button-danger-quiet" type="button" onClick={() => onDelete(job)}>
          <Trash size={18} aria-hidden="true" />删除记录
        </button>
      </main>
    );
  }

  const result = job.result!;
  return (
    <main className="inspector-panel" id="main-content">
      <header className="result-header">
        <div className="result-title">
          <span className={`result-status status-${result.status}`}>{severityText[result.status]}</span>
          <h1 title={job.filename}>{job.filename}</h1>
          <p>{result.metadata.format_name}</p>
        </div>
        <div className="score-block" aria-label={`质量评分 ${result.score} 分`}>
          <strong>{result.score}</strong><span>/ 100</span>
        </div>
      </header>

      <div className="result-toolbar">
        <div className="tabs" role="tablist" aria-label="结果视图">
          <button id="overview-tab" type="button" role="tab" aria-controls="overview-panel" aria-selected={view === "overview"} tabIndex={view === "overview" ? 0 : -1} onKeyDown={handleTabKey} onClick={() => onView("overview")}>检测概览</button>
          <button id="log-tab" type="button" role="tab" aria-controls="log-panel" aria-selected={view === "log"} tabIndex={view === "log" ? 0 : -1} onKeyDown={handleTabKey} onClick={() => onView("log")}>FFmpeg 日志</button>
        </div>
        <div className="report-actions">
          <a className="button button-secondary" href={`/api/jobs/${job.id}/report?format=html`} download>
            <DownloadSimple size={17} aria-hidden="true" />HTML
          </a>
          <a className="button button-secondary" href={`/api/jobs/${job.id}/report?format=json`} download>
            <DownloadSimple size={17} aria-hidden="true" />JSON
          </a>
          <button className="icon-button danger-icon" type="button" aria-label="删除检测记录" title="删除检测记录" onClick={() => onDelete(job)}>
            <Trash size={18} aria-hidden="true" />
          </button>
        </div>
      </div>

      {view === "overview" ? (
        <div className="result-content" id="overview-panel" role="tabpanel" aria-labelledby="overview-tab">
          <Timeline result={result} />
          <Metadata result={result} />
          <Findings result={result} />
        </div>
      ) : (
        <div className="log-panel" id="log-panel" role="tabpanel" aria-labelledby="log-tab">
          {logError && <p className="inline-error" role="alert">{logError}</p>}
          {!log && !logError ? <div className="log-loading">正在读取日志…</div> : <pre>{log}</pre>}
        </div>
      )}
    </main>
  );
}
