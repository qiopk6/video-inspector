import { useCallback, useEffect, useMemo, useState } from "react";
import { FilmStrip, Moon, Sun } from "@phosphor-icons/react";
import { cancelJob, deleteJob, getJobs, uploadHlsDirectory, uploadVideos } from "./api";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { InspectorPanel } from "./components/InspectorPanel";
import { JobQueue } from "./components/JobQueue";
import { HlsFolderPicker } from "./components/HlsFolderPicker";
import { UploadDropzone } from "./components/UploadDropzone";
import type { QueueFilter, VideoJob } from "./types";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  const saved = localStorage.getItem("video-inspector-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readUrlState(): { jobId: string | null; view: "overview" | "log"; filter: QueueFilter } {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view") === "log" ? "log" : "overview";
  const filter = ["issues", "passed"].includes(params.get("filter") || "") ? params.get("filter") as QueueFilter : "all";
  return { jobId: params.get("job"), view, filter };
}

export default function App() {
  const initial = useMemo(readUrlState, []);
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(initial.jobId);
  const [view, setView] = useState<"overview" | "log">(initial.view);
  const [filter, setFilter] = useState<QueueFilter>(initial.filter);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [hlsAdding, setHlsAdding] = useState(false);
  const [hlsProgress, setHlsProgress] = useState(0);
  const [notice, setNotice] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<VideoJob | null>(null);
  const [connected, setConnected] = useState(true);
  const hasActiveJobs = jobs.some((job) => ["queued", "analyzing"].includes(job.status));

  const refresh = useCallback(async () => {
    try {
      const next = await getJobs();
      setJobs(next);
      setConnected(true);
      setSelectedId((current) => current && next.some((job) => job.id === current) ? current : next[0]?.id || null);
    } catch (error) {
      setConnected(false);
      setNotice((error as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, hasActiveJobs ? 800 : 2400);
    return () => window.clearInterval(timer);
  }, [refresh, hasActiveJobs]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem("video-inspector-theme", theme);
    const color = theme === "dark" ? "#171c1c" : "#f4f6f7";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", color);
  }, [theme]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedId) params.set("job", selectedId);
    if (view !== "overview") params.set("view", view);
    if (filter !== "all") params.set("filter", filter);
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, [selectedId, view, filter]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    function guard(event: BeforeUnloadEvent) {
      if (uploading || hlsAdding) event.preventDefault();
    }
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [uploading, hlsAdding]);

  async function handleFiles(files: File[]) {
    if (!files.length) return;
    setUploading(true);
    setUploadProgress(0);
    try {
      const created = await uploadVideos(files, setUploadProgress);
      await refresh();
      setSelectedId(created[0]?.id || null);
      setNotice(`已加入 ${created.length} 个检测任务`);
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  async function handleHlsFolder(files: File[]) {
    if (!files.length) return;
    setHlsAdding(true);
    setHlsProgress(0);
    try {
      const created = await uploadHlsDirectory(files, setHlsProgress);
      await refresh();
      setSelectedId(created.id);
      setNotice("已加入 HLS 检测任务");
    } catch (error) {
      setNotice((error as Error).message);
    } finally {
      setHlsAdding(false);
      setHlsProgress(0);
    }
  }

  async function handleCancel(job: VideoJob) {
    try {
      await cancelJob(job.id);
      await refresh();
      setNotice("检测已取消");
    } catch (error) {
      setNotice((error as Error).message);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    try {
      await deleteJob(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
      setNotice("检测记录已删除");
    } catch (error) {
      setNotice((error as Error).message);
    }
  }

  const selected = jobs.find((job) => job.id === selectedId) || null;
  const selectedStatus = selected ? `${selected.filename}：${selected.status}` : "";

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Video Inspector 首页" translate="no">
          <span className="brand-mark"><FilmStrip size={22} weight="fill" aria-hidden="true" /></span>
          <span><strong>Video Inspector</strong><small>本地视频质检</small></span>
        </a>
        <div className="topbar-actions">
          {!connected && <span className="connection-error" role="status">服务未连接</span>}
          {jobs.length > 0 && <UploadDropzone compact disabled={uploading || hlsAdding} onFiles={handleFiles} />}
          {jobs.length > 0 && (
            <HlsFolderPicker compact disabled={uploading} busy={hlsAdding} onFiles={handleHlsFolder} />
          )}
          <button
            className="icon-button"
            type="button"
            aria-label={theme === "dark" ? "切换浅色模式" : "切换深色模式"}
            title={theme === "dark" ? "浅色模式" : "深色模式"}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? <Sun size={19} aria-hidden="true" /> : <Moon size={19} aria-hidden="true" />}
          </button>
        </div>
      </header>

      {(uploading || hlsAdding) && (
        <div className="upload-strip" role="status" aria-live="polite">
          <span>{hlsAdding ? "正在读取 HLS 文件夹…" : "正在上传到本机服务…"}</span>
          <progress max="100" value={hlsAdding ? hlsProgress : uploadProgress} aria-label="上传进度" />
          <strong>{hlsAdding ? hlsProgress : uploadProgress}%</strong>
        </div>
      )}

      {jobs.length === 0 ? (
        <main className="first-run" id="main-content">
          <div className="first-run-copy">
            <h1>把视频放上检片台</h1>
            <p>检测画质参数、黑屏、静音、冻结画面和解码异常。文件始终留在这台电脑。</p>
          </div>
          <UploadDropzone disabled={uploading || hlsAdding} onFiles={handleFiles} />
          <HlsFolderPicker disabled={uploading} busy={hlsAdding} onFiles={handleHlsFolder} />
          <div className="detection-index" aria-label="可检测项目">
            <span>技术参数</span><span>黑屏</span><span>静音</span><span>冻结</span><span>解码完整性</span>
          </div>
        </main>
      ) : (
        <div className="workspace">
          <JobQueue jobs={jobs} selectedId={selectedId} filter={filter} onFilter={setFilter} onSelect={setSelectedId} />
          <InspectorPanel job={selected} view={view} onView={setView} onCancel={handleCancel} onDelete={setDeleteTarget} />
        </div>
      )}

      <div className="toast-region" aria-live="polite" aria-atomic="true">
        {notice && <div className="toast">{notice}</div>}
      </div>
      <div className="visually-hidden" aria-live="polite" aria-atomic="true">{selectedStatus}</div>
      <ConfirmDialog open={Boolean(deleteTarget)} filename={deleteTarget?.filename || ""} onCancel={() => setDeleteTarget(null)} onConfirm={confirmDelete} />
    </div>
  );
}
