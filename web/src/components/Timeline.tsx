import type { AnalysisResult, TimeSegment } from "../types";

interface Lane {
  code: string;
  label: string;
  className: string;
  segments: TimeSegment[];
}

function timecode(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${remaining.toFixed(1).padStart(4, "0")}`;
}

export function Timeline({ result }: { result: AnalysisResult }) {
  const duration = result.metadata.duration || 1;
  const byCode = (code: string) => result.findings.find((item) => item.code === code)?.segments || [];
  const lanes: Lane[] = [
    { code: "black", label: "黑屏", className: "black", segments: byCode("BLACK_SCREEN") },
    { code: "silence", label: "静音", className: "silence", segments: byCode("SILENCE") },
    { code: "freeze", label: "冻结", className: "freeze", segments: byCode("FREEZE_FRAME") },
  ];
  const ticks = Array.from({ length: 5 }, (_, index) => (duration * index) / 4);

  return (
    <section className="timeline-section" aria-labelledby="timeline-title">
      <div className="section-heading-row">
        <h2 id="timeline-title">检片时间尺</h2>
        <span>{timecode(duration)}</span>
      </div>
      <div className="timeline" role="img" aria-label="黑屏、静音与冻结片段时间分布">
        <div className="timeline-ticks" aria-hidden="true">
          <span />
          {ticks.map((tick) => <span key={tick}>{timecode(tick)}</span>)}
        </div>
        {lanes.map((lane) => (
          <div className="timeline-lane" key={lane.code}>
            <span className="lane-label">{lane.label}</span>
            <div className="lane-track">
              {lane.segments.map((segment, index) => (
                <span
                  key={`${segment.start}-${index}`}
                  className={`timeline-segment segment-${lane.className}`}
                  style={{
                    left: `${Math.max(0, (segment.start / duration) * 100)}%`,
                    width: `${Math.max(0.45, (segment.duration / duration) * 100)}%`,
                  }}
                  title={`${lane.label} ${timecode(segment.start)} 至 ${timecode(segment.end)}`}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
