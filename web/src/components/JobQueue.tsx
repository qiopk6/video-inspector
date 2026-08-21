import { useEffect, useMemo, useRef, useState } from "react";
import {
  CaretDown,
  CaretRight,
  CheckCircle,
  Clock,
  Prohibit,
  SpinnerGap,
  Trash,
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
  onClear: () => void;
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

function resolutionEntries(jobs: VideoJob[]) {
  const groups = jobs.reduce<Map<string, VideoJob[]>>((result, job) => {
    const key = job.group || "普通视频";
    result.set(key, [...(result.get(key) || []), job]);
    return result;
  }, new Map());

  return Array.from(groups.entries())
    .map(([group, groupJobs]) => [group, [...groupJobs].sort((left, right) => left.filename.localeCompare(right.filename, "zh-CN", { numeric: true }))] as const)
    .sort(([left], [right]) => {
      if (left === "普通视频") return 1;
      if (right === "普通视频") return -1;
      return Number.parseInt(left, 10) - Number.parseInt(right, 10);
    });
}

export function JobQueue({ jobs, selectedId, filter, onFilter, onSelect, onClear }: Props) {
  const [expandedBatches, setExpandedBatches] = useState<Set<string>>(new Set());
  const knownBatchIds = useRef<Set<string>>(new Set());
  const visible = useMemo(() => jobs.filter((job) => {
    if (filter === "passed") return job.result?.status === "pass";
    if (filter === "issues") return job.status === "failed" || ["warning", "failure"].includes(job.result?.status || "");
    return true;
  }), [filter, jobs]);
  const batches = useMemo(() => {
    const grouped = visible.reduce<Map<string, VideoJob[]>>((result, job) => {
      const key = job.batch_id || `legacy-${job.id}`;
      result.set(key, [...(result.get(key) || []), job]);
      return result;
    }, new Map());
    return Array.from(grouped.entries()).sort(([, left], [, right]) => {
      const leftCreated = left[0]?.batch_created_at || left[0]?.created_at || "";
      const rightCreated = right[0]?.batch_created_at || right[0]?.created_at || "";
      return rightCreated.localeCompare(leftCreated);
    });
  }, [visible]);
  const allBatchIds = useMemo(() => jobs.map((job) => job.batch_id || `legacy-${job.id}`), [jobs]);
  const batchIdKey = allBatchIds.join("|");

  useEffect(() => {
    const added = allBatchIds.filter((id) => !knownBatchIds.current.has(id));
    knownBatchIds.current = new Set(allBatchIds);
    setExpandedBatches((current) => {
      const available = new Set(allBatchIds);
      const next = new Set([...current].filter((id) => available.has(id)));
      added.forEach((id) => next.add(id));
      return next;
    });
  }, [batchIdKey]);

  const finishedCount = jobs.filter((job) => ["completed", "failed", "cancelled"].includes(job.status)).length;

  return (
    <aside className="queue-panel" aria-label="检测队列">
      <div className="queue-heading">
        <span className="queue-title">检测队列</span>
        <span className="queue-count">{jobs.length}</span>
        <button className="icon-button queue-clear" type="button" aria-label="清空已完成记录" title="清空已完成记录" disabled={!finishedCount} onClick={onClear}>
          <Trash size={17} aria-hidden="true" />
        </button>
      </div>
      <div className="segmented" role="group" aria-label="筛选检测任务">
        {(["all", "issues", "passed"] as const).map((value) => (
          <button key={value} type="button" className={filter === value ? "is-active" : ""} aria-pressed={filter === value} onClick={() => onFilter(value)}>
            {{ all: "全部", issues: "有问题", passed: "通过" }[value]}
          </button>
        ))}
      </div>
      <div className="queue-list">
        {batches.map(([batchId, batchJobs]) => {
          const expanded = expandedBatches.has(batchId);
          const firstJob = batchJobs[0];
          const batchName = firstJob.batch_name || `${firstJob.created_at} · ${batchJobs.length} 个文件`;
          const issueCount = batchJobs.filter((job) => job.status === "failed" || ["warning", "failure"].includes(job.result?.status || "")).length;
          return (
            <section className="queue-batch" key={batchId}>
              <button
                type="button"
                className="queue-batch-toggle"
                aria-expanded={expanded}
                onClick={() => setExpandedBatches((current) => {
                  const next = new Set(current);
                  if (next.has(batchId)) next.delete(batchId);
                  else next.add(batchId);
                  return next;
                })}
              >
                <span className="queue-batch-chevron">{expanded ? <CaretDown size={16} aria-hidden="true" /> : <CaretRight size={16} aria-hidden="true" />}</span>
                <span className="queue-batch-main">
                  <strong>{batchName}</strong>
                  <span>{batchJobs.length} 个检测任务{issueCount ? ` · ${issueCount} 个问题` : ""}</span>
                </span>
              </button>
              {expanded && resolutionEntries(batchJobs).map(([group, groupJobs]) => (
                <section className="queue-group" key={`${batchId}-${group}`}>
                  {group !== "普通视频" && <h3 className="queue-group-title">{group}<span>{groupJobs.length} 个任务</span></h3>}
                  {groupJobs.map((job) => {
                    const severity = job.result?.status || (job.status === "failed" ? "failure" : "info");
                    return (
                      <button type="button" className={`queue-item severity-${severity}${selectedId === job.id ? " is-selected" : ""}`} key={job.id} onClick={() => onSelect(job.id)}>
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
                </section>
              ))}
            </section>
          );
        })}
        {!visible.length && jobs.length > 0 && <p className="queue-empty">当前筛选没有任务。</p>}
      </div>
    </aside>
  );
}
