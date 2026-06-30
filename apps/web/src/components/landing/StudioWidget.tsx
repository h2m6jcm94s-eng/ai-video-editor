"use client";

// Interactive scrubbable timeline — the hero "studio" widget.
// Reference track → user clips → stenciled result, with playhead and live readout.
// Ported from cinema-timeline.jsx.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ASSIGNMENTS,
  BEAT_TIMES,
  BEATS_PER_SEC,
  DEMO_BPM,
  DEMO_DURATION,
  REF_SHOTS,
  type RefShot,
  SECTIONS,
  TRANSITION_AT,
  TRANSITIONS,
  USER_CLIPS,
} from "./data";

function fmtTime(t: number) {
  const s = Math.floor(t);
  const f = Math.floor((t - s) * 24); // 24fps
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}:${String(f).padStart(2, "0")}`;
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

export function StudioWidget() {
  const [t, setT] = useState(8.3);
  const [playing, setPlaying] = useState(true);
  const lastRef = useRef(0);

  // Auto-play loop
  useEffect(() => {
    if (!playing) return;
    let id: number;
    const tick = (now: number) => {
      const dt = (now - lastRef.current) / 1000;
      lastRef.current = now;
      setT((prev) => {
        const next = prev + dt;
        return next >= DEMO_DURATION ? 0 : next;
      });
      id = requestAnimationFrame(tick);
    };
    lastRef.current = performance.now();
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [playing]);

  const curShotIdx = useMemo(() => REF_SHOTS.findIndex((s) => t >= s.start && t < s.end), [t]);
  const curShot = curShotIdx >= 0 ? REF_SHOTS[curShotIdx] : REF_SHOTS[0];
  const curAssign = ASSIGNMENTS[curShotIdx >= 0 ? curShotIdx : 0];
  const curClip = USER_CLIPS.find((c) => c.id === curAssign.clipId);
  const curSection = SECTIONS.find((s) => t >= s.start && t < s.end) || SECTIONS[0];
  const curBeatIdx = Math.floor(t * BEATS_PER_SEC);

  const energy = useMemo(() => {
    if (t < 5.5) return 0.32;
    if (t < 12) return 0.48;
    if (t < 15.5) return 0.68 + Math.sin(t * 3) * 0.05;
    if (t < 24) return 0.92 + Math.sin(t * 6) * 0.04;
    return 0.42;
  }, [t]);

  const pct = (t / DEMO_DURATION) * 100;

  const handleScrub = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    setT(x * DEMO_DURATION);
  }, []);

  const startDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    setPlaying(false);
    const trackEl = e.currentTarget;
    handleScrub(e);
    const move = (ev: MouseEvent) => {
      const rect = trackEl.getBoundingClientRect();
      const x = clamp((ev.clientX - rect.left) / rect.width, 0, 1);
      setT(x * DEMO_DURATION);
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  const totalClipDur = USER_CLIPS.reduce((s, c) => s + c.duration, 0);

  const clipPositions = useMemo(() => {
    let cursor = 0;
    return USER_CLIPS.map((c) => {
      const left = (cursor / totalClipDur) * 100;
      const w = (c.duration / totalClipDur) * 100;
      cursor += c.duration;
      return { left, w, ...c };
    });
  }, [totalClipDur]);

  return (
    <div className="studio">
      <div className="studio-chrome">
        <div className="chrome-left">
          <span className="pill on">REC</span>
          <span className="pill">project · midnight-drive-edit</span>
          <span className="pill">9:16</span>
          <span className="pill">tier · full transfer</span>
        </div>
        <div className="chrome-right">
          <span className="pill">{DEMO_BPM} BPM</span>
          <span className="pill">F# minor</span>
          <span className="pill">24 fps · 720p</span>
        </div>
      </div>

      <div className="studio-body">
        <div className="studio-stage">
          <SectionRibbon t={t} />
          <TrackGroup keyLabel="REF/A" label="Reference" sub="parsed shot timeline" shots={REF_SHOTS} t={t} />
          <TransitionsTrack t={t} />
          <BeatStrip t={t} />
          <ClipLibrary curClipId={curAssign?.clipId} clipPositions={clipPositions} />
          <ResultTrack t={t} />

          <div className="studio-controls">
            <button
              className="control-btn primary"
              onClick={() => setPlaying((p) => !p)}
              aria-label="play/pause"
            >
              {playing ? (
                <svg width="11" height="12" viewBox="0 0 11 12" fill="none">
                  <rect x="0" y="0" width="3.5" height="12" fill="currentColor" />
                  <rect x="7.5" y="0" width="3.5" height="12" fill="currentColor" />
                </svg>
              ) : (
                <svg width="11" height="12" viewBox="0 0 11 12" fill="none">
                  <path d="M0 0L11 6L0 12V0Z" fill="currentColor" />
                </svg>
              )}
            </button>
            <button className="control-btn" onClick={() => setT(0)} aria-label="restart">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M0 0V12L9 6L0 0Z" fill="currentColor" transform="rotate(180 6 6)" />
                <rect x="0" y="0" width="2" height="12" fill="currentColor" />
              </svg>
            </button>
            <div className="scrubber-wrap">
              <div className="scrubber-track" onMouseDown={startDrag}>
                <div className="scrubber-fill" style={{ width: pct + "%" }} />
                <div className="scrubber-thumb" style={{ left: pct + "%" }} />
              </div>
            </div>
            <div className="time-readout">{fmtTime(t)} / 00:30:00</div>
          </div>
        </div>

        <div className="studio-readout">
          <div className="readout-section">
            <h4>Now playing</h4>
            <div className="big" style={{ color: "var(--accent)" }}>
              <em>Shot</em> {String((curShotIdx >= 0 ? curShotIdx : 0) + 1).padStart(2, "0")}{" "}
              <span style={{ color: "var(--fg-dim)", fontStyle: "normal" }}>/ {REF_SHOTS.length}</span>
            </div>
          </div>

          <div className="readout-section">
            <h4>Reference</h4>
            <div className="row">
              <span>type</span>
              <span>{curShot.type}</span>
            </div>
            <div className="row">
              <span>motion</span>
              <span>{curShot.motion}</span>
            </div>
            <div className="row">
              <span>duration</span>
              <span>{(curShot.end - curShot.start).toFixed(2)}s</span>
            </div>
            <div className="row">
              <span>section</span>
              <span>{curSection.name}</span>
            </div>
          </div>

          <div className="readout-section">
            <h4>Match</h4>
            <div className="row">
              <span>clip</span>
              <span>
                {curClip?.id} · {curClip?.label}
              </span>
            </div>
            <div className="row">
              <span>confidence</span>
              <span style={{ color: curAssign.confidence > 0.85 ? "var(--accent)" : "var(--fg)" }}>
                {(curAssign.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="row">
              <span>beat</span>
              <span>
                {curBeatIdx + 1}/{BEAT_TIMES.length}
              </span>
            </div>
            <div className="row">
              <span>energy</span>
              <span>{energy.toFixed(2)}</span>
            </div>
          </div>

          <div className="readout-section" style={{ marginTop: "auto" }}>
            <h4>Cut-list emit</h4>
            <pre
              style={{
                fontFamily: "var(--mono)",
                fontSize: "10.5px",
                color: "var(--fg-dim)",
                lineHeight: 1.55,
                background: "var(--bg)",
                border: "1px solid var(--hairline)",
                padding: "10px 12px",
                borderRadius: 2,
                overflow: "auto",
                maxHeight: 120,
              }}
            >
              {`{ "index": ${curShotIdx + 1},
  "start_s": ${curShot.start.toFixed(2)},
  "dur_s":   ${(curShot.end - curShot.start).toFixed(2)},
  "beat_ix": ${curBeatIdx},
  "shot":    "${curShot.type}",
  "motion":  "${curShot.motion}",
  "clip":    "${curClip?.id}",
  "energy":  ${energy.toFixed(2)} }`}
            </pre>
          </div>
        </div>
      </div>

      <div className="studio-foot">
        <span>STENCIL · live demo · 30s preview</span>
        <span style={{ display: "inline-flex", gap: 14 }}>
          <span>tempo · {DEMO_BPM}</span>
          <span>shots · {REF_SHOTS.length}</span>
          <span>section · {curSection.name}</span>
        </span>
      </div>
    </div>
  );
}

function SectionRibbon({ t }: { t: number }) {
  return (
    <div>
      <div className="track-label">
        <span>
          <span className="lbl-key">SCT</span> · sections
        </span>
        <span style={{ color: "var(--fg-muted)" }}>verse · prechorus · drop · outro</span>
      </div>
      <div
        style={{
          display: "flex",
          height: 18,
          marginTop: 4,
          border: "1px solid var(--hairline)",
          borderRadius: 2,
          overflow: "hidden",
        }}
      >
        {SECTIONS.map((s, i) => {
          const w = ((s.end - s.start) / DEMO_DURATION) * 100;
          const active = t >= s.start && t < s.end;
          return (
            <div
              key={i}
              style={{
                width: w + "%",
                background: s.color,
                borderRight: i < SECTIONS.length - 1 ? "1px solid rgba(0,0,0,0.5)" : "none",
                display: "flex",
                alignItems: "center",
                paddingLeft: 8,
                fontFamily: "var(--mono)",
                fontSize: "0.6rem",
                textTransform: "uppercase",
                letterSpacing: "0.18em",
                color: active ? "#fff" : "rgba(255,255,255,0.5)",
                transition: "color .2s",
              }}
            >
              {s.name}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TrackGroup({
  keyLabel,
  label,
  sub,
  shots,
  t,
}: {
  keyLabel: string;
  label: string;
  sub: string;
  shots: RefShot[];
  t: number;
}) {
  return (
    <div className="track-group">
      <div className="track-label">
        <span>
          <span className="lbl-key">{keyLabel}</span> · {label}
        </span>
        <span style={{ color: "var(--fg-muted)" }}>{sub}</span>
      </div>
      <div className="track tall">
        {shots.map((s, i) => {
          const left = (s.start / DEMO_DURATION) * 100;
          const w = ((s.end - s.start) / DEMO_DURATION) * 100;
          const active = t >= s.start && t < s.end;
          return (
            <div
              key={i}
              className="track-shot"
              style={{
                left: left + "%",
                width: w + "%",
                background: s.tone,
                outline: active ? "1px solid #fff" : "none",
                outlineOffset: "-1px",
                opacity: active ? 1 : 0.78,
              }}
            >
              <span style={{ opacity: w > 3 ? 1 : 0 }}>{s.type}</span>
            </div>
          );
        })}
        <div className="playhead" style={{ left: (t / DEMO_DURATION) * 100 + "%" }} />
      </div>
    </div>
  );
}

function BeatStrip({ t }: { t: number }) {
  return (
    <div>
      <div className="track-label">
        <span>
          <span className="lbl-key">BT</span> · beat grid
        </span>
        <span style={{ color: "var(--fg-muted)" }}>{DEMO_BPM} BPM · 4/4 · downbeats orange</span>
      </div>
      <div
        style={{
          position: "relative",
          height: 22,
          marginTop: 4,
          borderTop: "1px solid var(--hairline)",
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        {BEAT_TIMES.map((bt, i) => {
          const left = (bt / DEMO_DURATION) * 100;
          const isDownbeat = i % 4 === 0;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: left + "%",
                top: isDownbeat ? 4 : 8,
                width: 1,
                height: isDownbeat ? 14 : 8,
                background: isDownbeat ? "var(--accent)" : "var(--fg-muted)",
                opacity: isDownbeat ? 1 : 0.65,
              }}
            />
          );
        })}
        <div className="playhead" style={{ left: (t / DEMO_DURATION) * 100 + "%" }} />
      </div>
    </div>
  );
}

function ClipLibrary({
  curClipId,
  clipPositions,
}: {
  curClipId: string | undefined;
  clipPositions: ({ left: number; w: number } & (typeof USER_CLIPS)[number])[];
}) {
  return (
    <div className="track-group">
      <div className="track-label">
        <span>
          <span className="lbl-key">LIB</span> · your clips
        </span>
        <span style={{ color: "var(--fg-muted)" }}>{USER_CLIPS.length} indexed · Marengo 3</span>
      </div>
      <div className="track" style={{ display: "flex", padding: 0 }}>
        {clipPositions.map((c) => {
          const active = c.id === curClipId;
          return (
            <div
              key={c.id}
              style={{
                width: c.w + "%",
                background: c.grad,
                borderRight: "1px solid rgba(0,0,0,0.4)",
                position: "relative",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                padding: "6px 8px",
                opacity: active ? 1 : 0.42,
                outline: active ? "1px solid var(--accent)" : "none",
                outlineOffset: -1,
                transition: "opacity .2s, outline-color .2s",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: "0.6rem",
                  color: "#fff",
                  letterSpacing: "0.14em",
                }}
              >
                {c.id}
              </div>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: "0.58rem",
                  color: "rgba(255,255,255,0.78)",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                }}
              >
                {c.label}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ResultTrack({ t }: { t: number }) {
  return (
    <div className="track-group">
      <div className="track-label">
        <span>
          <span className="lbl-key">OUT</span> · stencil
        </span>
        <span style={{ color: "var(--accent)" }}>your clips · reference timing · reference grade</span>
      </div>
      <div className="track tall">
        {REF_SHOTS.map((s, i) => {
          const a = ASSIGNMENTS[i];
          const clip = USER_CLIPS.find((c) => c.id === a.clipId);
          const left = (s.start / DEMO_DURATION) * 100;
          const w = ((s.end - s.start) / DEMO_DURATION) * 100;
          const active = t >= s.start && t < s.end;
          return (
            <div
              key={i}
              className="track-shot"
              style={{
                left: left + "%",
                width: w + "%",
                background: clip?.grad || "var(--bg)",
                outline: active ? "1.5px solid var(--accent)" : "none",
                outlineOffset: -1,
                opacity: active ? 1 : 0.7,
              }}
            >
              <span style={{ opacity: w > 3 ? 1 : 0, color: "#fff" }}>{clip?.id}</span>
            </div>
          );
        })}
        <div className="playhead" style={{ left: (t / DEMO_DURATION) * 100 + "%" }} />
      </div>
    </div>
  );
}

const TRANSITION_COLOR: Record<string, string> = {
  hard: "#f5f1e8",
  whip: "#2ec4b6",
  crosszoom: "#ff4d1f",
  glitch: "#ff8a5b",
  ramp: "#dc6428",
  freeze: "#6c7a8e",
};
const TRANSITION_LABEL: Record<string, string> = {
  hard: "CUT",
  whip: "WHIP",
  crosszoom: "ZOOM",
  glitch: "GLCH",
  ramp: "RAMP",
  freeze: "FRZ",
};

function TransitionsTrack({ t }: { t: number }) {
  return (
    <div className="track-group">
      <div className="track-label">
        <span>
          <span className="lbl-key">TRN</span> · transitions
        </span>
        <span style={{ color: "var(--fg-muted)" }}>
          {TRANSITIONS.length} styles · {TRANSITION_AT.length} placements
        </span>
      </div>
      <div className="track" style={{ height: 28, position: "relative" }}>
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "50%",
            height: 1,
            background: "var(--hairline)",
          }}
        />
        {TRANSITION_AT.map((tr, i) => {
          const shot = REF_SHOTS[tr.afterShotIdx];
          if (!shot) return null;
          const boundary = shot.end;
          const left = (boundary / DEMO_DURATION) * 100;
          const isActive = t > boundary - 0.25 && t < boundary + 0.25;
          const color = TRANSITION_COLOR[tr.type] || "var(--fg-dim)";
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: left + "%",
                top: 4,
                bottom: 4,
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 2,
              }}
            >
              <div
                style={{
                  width: tr.type === "hard" ? 1.5 : 3.5,
                  height: "100%",
                  background: color,
                  opacity: isActive ? 1 : 0.7,
                  boxShadow: isActive ? `0 0 6px ${color}` : "none",
                  transition: "opacity .15s, box-shadow .15s",
                }}
              />
              {tr.type !== "hard" && (
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 7.5,
                    letterSpacing: "0.14em",
                    color: isActive ? color : "var(--fg-muted)",
                    position: "absolute",
                    top: -10,
                    whiteSpace: "nowrap",
                  }}
                >
                  {TRANSITION_LABEL[tr.type]}
                </span>
              )}
            </div>
          );
        })}
        <div className="playhead" style={{ left: (t / DEMO_DURATION) * 100 + "%" }} />
      </div>
    </div>
  );
}
