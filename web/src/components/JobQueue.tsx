import {
  CheckCircle,
  Clock,
  Prohibit,
  SpinnerGap,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import type { QueueFilter, VideoJob } from "../types";

interface Props {
  jobs: VideoJob[];
  selectedId: string | null;
  filter: QueueFilter;
  onFilter: (filter: QueueFilter) => void;
  onSelect: (id: string) => void;
}

const statusText = {
  queued: "等待中",
  analyzing: "检测中",
  completed: "已完成",
  failed: "检测失败",
  cancelled: "已取消",
};

function StatusIcon({ job }: { job: VideoJob }) {
  if (job.status === "analyzing") return <SpinnerGap className="spin" size={18} aria-hidden="true" />;
  if (job.status === "queued") return <Clock size={18} aria-hidden="true" />;
  if (job.status === "failed") return <WarningCircle size={18} aria-hidden="true" />;
  if (job.status === "cancelled") return <Prohibit size={18} aria-hidden="true" />;
  if (job.result?.status === "failure") return <XCircle size={18} weight="fill" aria-hidden="true" />;
  if (job.result?.status === "warning") return <WarningCircle size={18} weight="fill" aria-hidden="true" />;
  return <CheckCircle size={18} weight="fill" aria-hidden="true" />;
}

function formatBytes(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value / 1024 / 1024) + " MB";
}

export function JobQueue({ jobs, selectedId, filter, onFilter, onSelect }: Props) {
  const visible = jobs.filter((job) => {
    if (filter === "passed") return job.result?.status === "pass";
    if (filter === "issues") return job.status === "failed" || ["warning", "failure"].includes(job.result?.status || "");
    return true;
  });

  return (
    <aside className="queue-panel" aria-label="检测队列">
      <div className="queue-heading">
        <span className="queue-title">检测队列</span>
        <span className="queue-count">{jobs.length}</span>
      </div>
      <div className="segmented" role="group" aria-label="筛选检测任务">
        {(["all", "issues", "passed"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={filter === value ? "is-active" : ""}
            aria-pressed={filter === value}
            onClick={() => onFilter(value)}
          >
            {{ all: "全部", issues: "有问题", passed: "通过" }[value]}
          </button>
        ))}
      </div>
      <div className="queue-list">
        {visible.map((job) => {
          const severity = job.result?.status || (job.status === "failed" ? "failure" : "info");
          return (
            <button
              type="button"
              className={`queue-item severity-${severity}${selectedId === job.id ? " is-selected" : ""}`}
              key={job.id}
              onClick={() => onSelect(job.id)}
            >
              <span className="queue-status"><StatusIcon job={job} /></span>
              <span className="queue-main">
                <span className="queue-filename" title={job.filename}>{job.filename}</span>
                <span className="queue-meta">
                  {job.status === "analyzing" ? `${job.progress}%` : statusText[job.status]}
                  <span aria-hidden="true">/</span>
                  {formatBytes(job.size_bytes)}
                </span>
                {job.status === "analyzing" && <progress max="100" value={job.progress} aria-label={`${job.filename} 检测进度`} />}
              </span>
              {job.result && <span className="queue-score">{job.result.score}</span>}
            </button>
          );
        })}
        {!visible.length && jobs.length > 0 && <p className="queue-empty">当前筛选没有任务。</p>}
      </div>
    </aside>
  );
}
