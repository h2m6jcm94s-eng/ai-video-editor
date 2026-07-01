"use client";

// Interactive pipeline diagram — click/hover a stage, see the detail.
// Auto-advances on an interval, paused on hover. Ported from cinema-pipeline.jsx.

import { useEffect, useState } from "react";
import { PIPELINE } from "./data";

export function PipelinePanel() {
  const [active, setActive] = useState(0);
  const [auto, setAuto] = useState(true);
  const stage = PIPELINE[active];

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(() => {
      setActive((a) => (a + 1) % PIPELINE.length);
    }, 3800);
    return () => clearInterval(id);
  }, [auto]);

  return (
    <div className="pipeline-frame" onMouseEnter={() => setAuto(false)} onMouseLeave={() => setAuto(true)}>
      <div className="pipeline-stages">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            padding: "0 14px 12px",
            borderBottom: "1px solid var(--hairline)",
            marginBottom: 8,
          }}
        >
          <span className="mono">Pipeline · 6 stages</span>
          <span className="mono">~2m 24s · total</span>
        </div>
        {PIPELINE.map((p, i) => (
          <div
            key={p.id}
            className={"stage" + (i === active ? " active" : "")}
            onClick={() => setActive(i)}
            onMouseEnter={() => setActive(i)}
          >
            <span className="ix">{p.ix}</span>
            <div>
              <div className="nm">{p.name}</div>
              <div className="nm-sub">{p.subtitle}</div>
            </div>
            <span className="lat">{p.latency}</span>
          </div>
        ))}
      </div>

      <div className="pipeline-detail">
        <div className="mono accent">
          Stage {stage.ix} · {stage.name}
        </div>
        <h4>
          <em>{stage.headline.split(" ").slice(0, 2).join(" ")}</em>{" "}
          {stage.headline.split(" ").slice(2).join(" ")}
        </h4>
        <p>{stage.body}</p>
        <div className="detail-grid">
          {stage.keys.map((k, i) => (
            <div key={i} className="item">
              <div className="k">{k.k}</div>
              <div className="v">{k.v}</div>
            </div>
          ))}
        </div>
        <div className="pipeline-art">
          <StageArt id={stage.id} key={stage.id} />
        </div>
      </div>
    </div>
  );
}

function StageArt({ id }: { id: string }) {
  if (id === "ingest") return <IngestArt />;
  if (id === "style") return <StyleArt />;
  if (id === "embed") return <EmbedArt />;
  if (id === "cutlist") return <CutlistArt />;
  if (id === "match") return <MatchArt />;
  if (id === "render") return <RenderArt />;
  return null;
}

function IngestArt() {
  const bars = 64;
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%" preserveAspectRatio="none">
      {Array.from({ length: bars }).map((_, i) => {
        const h = 20 + Math.abs(Math.sin(i * 0.42) * 38) + Math.abs(Math.sin(i * 0.13) * 24);
        return (
          <rect
            key={i}
            x={6 + i * 6}
            y={(140 - h) / 2}
            width={3}
            height={h}
            fill="var(--fg-dim)"
            opacity={0.55}
          >
            <animate
              attributeName="opacity"
              values="0.55;0.9;0.55"
              dur="2s"
              begin={`${i * 0.03}s`}
              repeatCount="indefinite"
            />
          </rect>
        );
      })}
      {Array.from({ length: 8 }).map((_, i) => (
        <line
          key={i}
          x1={20 + i * 48}
          x2={20 + i * 48}
          y1={10}
          y2={130}
          stroke="var(--accent)"
          strokeWidth="1"
          opacity="0.8"
        />
      ))}
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        BEATS · DOWNBEATS · ENERGY
      </text>
    </svg>
  );
}

function StyleArt() {
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%">
      <defs>
        <linearGradient id="before" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#9aa4b0" />
          <stop offset="50%" stopColor="#6e6a64" />
          <stop offset="100%" stopColor="#2a2c30" />
        </linearGradient>
        <linearGradient id="after" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#1b3a48" />
          <stop offset="50%" stopColor="#5a4030" />
          <stop offset="100%" stopColor="#e87440" />
        </linearGradient>
      </defs>
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--fg-muted)"
        letterSpacing="0.18em"
      >
        BEFORE
      </text>
      <rect x="14" y="30" width="170" height="36" fill="url(#before)" />
      <text
        x="14"
        y="86"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        AFTER · 33³ LUT
      </text>
      <rect x="14" y="94" width="170" height="36" fill="url(#after)" />
      <g transform="translate(196, 70)">
        <line x1="0" y1="0" x2="30" y2="0" stroke="var(--accent)" strokeWidth="1.5" />
        <path d="M 30 -5 L 38 0 L 30 5 Z" fill="var(--accent)" />
      </g>
      <g transform="translate(252, 24)" stroke="var(--fg-dim)" strokeWidth="1" fill="none">
        {[0, 1, 2, 3].map((i) => (
          <g key={i} opacity={0.4 + i * 0.18}>
            {[0, 1, 2, 3].map((j) => (
              <g key={j}>
                <polygon
                  points={`${30 + i * 22},${20 + j * 22} ${50 + i * 22},${10 + j * 22} ${72 + i * 22},${20 + j * 22} ${52 + i * 22},${30 + j * 22}`}
                  stroke="var(--fg-dim)"
                />
              </g>
            ))}
          </g>
        ))}
        <text
          x="0"
          y="100"
          fontFamily="JetBrains Mono"
          fontSize="9"
          fill="var(--accent)"
          letterSpacing="0.18em"
        >
          33×33×33
        </text>
      </g>
    </svg>
  );
}

function EmbedArt() {
  const dots = Array.from({ length: 48 }).map((_, i) => ({
    cx: 40 + Math.cos(i * 0.7) * (30 + (i % 7) * 8) + ((i * 7) % 320),
    cy: 70 + Math.sin(i * 0.9) * (24 + (i % 5) * 6),
    r: 2 + (i % 3),
    delay: i * 0.04,
  }));
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%">
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        EMBEDDING SPACE · 512d → 2d
      </text>
      {dots.map((d, i) => (
        <circle
          key={i}
          cx={Math.max(20, Math.min(380, d.cx))}
          cy={d.cy}
          r={d.r}
          fill={i % 4 === 0 ? "var(--accent)" : "var(--fg-dim)"}
          opacity="0.6"
        >
          <animate
            attributeName="r"
            values={`${d.r};${d.r + 1};${d.r}`}
            dur="3s"
            begin={`${d.delay}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
      <g transform="translate(200, 70)" stroke="var(--accent)" strokeWidth="1.5">
        <line x1="-8" y1="0" x2="8" y2="0" />
        <line x1="0" y1="-8" x2="0" y2="8" />
        <circle r="14" fill="none" strokeDasharray="3 3" />
      </g>
    </svg>
  );
}

function CutlistArt() {
  const lines = [
    `{ "globals": { "bpm": 124, "key": "F#m" },`,
    `  "slots": [`,
    `    { "i": 0, "dur": 1.95, "shot": "wide",   "in": "fade" },`,
    `    { "i": 1, "dur": 1.95, "shot": "medium", "motion": "push" },`,
    `    { "i": 2, "dur": 1.60, "shot": "close",  "energy": 0.62 },`,
    `    { "i": 3, "dur": 2.00, "shot": "wide",   "motion": "track" } ],`,
    `  "overlays": [{ "text": "MIDNIGHT", "anim": "wbw" }] }`,
  ];
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%">
      {lines.map((l, i) => (
        <text
          key={i}
          x="12"
          y={20 + i * 17}
          fontFamily="JetBrains Mono"
          fontSize="10"
          fill={i === 3 ? "var(--accent)" : "var(--fg-dim)"}
          letterSpacing="0.01em"
        >
          {l}
          {i === 3 && (
            <animate attributeName="opacity" values="0.4;1;0.4" dur="1.6s" repeatCount="indefinite" />
          )}
        </text>
      ))}
    </svg>
  );
}

function MatchArt() {
  const left = [0, 1, 2, 3, 4];
  const right = [0, 1, 2, 3];
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%">
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--fg-muted)"
        letterSpacing="0.18em"
      >
        SLOTS
      </text>
      <text
        x="346"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        CLIPS
      </text>
      {left.map((i) => (
        <g key={"l" + i}>
          <circle cx={50} cy={36 + i * 18} r="4" fill="var(--accent)" />
          <text
            x="22"
            y={40 + i * 18}
            fontFamily="JetBrains Mono"
            fontSize="9"
            fill="var(--fg-muted)"
            textAnchor="middle"
          >
            {String(i + 1).padStart(2, "0")}
          </text>
        </g>
      ))}
      {right.map((i) => (
        <g key={"r" + i}>
          <circle cx={350} cy={48 + i * 22} r="5" fill="var(--fg-dim)" />
          <text x="378" y={52 + i * 22} fontFamily="JetBrains Mono" fontSize="9" fill="var(--fg-muted)">
            C0{i + 1}
          </text>
        </g>
      ))}
      {left.map((i) => {
        const j = (i * 3) % right.length;
        const isBest = i % 2 === 0;
        return (
          <line
            key={"e" + i}
            x1={54}
            y1={36 + i * 18}
            x2={346}
            y2={48 + j * 22}
            stroke={isBest ? "var(--accent)" : "var(--fg-muted)"}
            strokeWidth={isBest ? 1.4 : 0.6}
            opacity={isBest ? 0.85 : 0.35}
          >
            <animate
              attributeName="opacity"
              values={`${isBest ? 0.5 : 0.2};${isBest ? 1 : 0.4};${isBest ? 0.5 : 0.2}`}
              dur="2.2s"
              begin={`${i * 0.2}s`}
              repeatCount="indefinite"
            />
          </line>
        );
      })}
    </svg>
  );
}

function RenderArt() {
  return (
    <svg viewBox="0 0 400 140" width="100%" height="100%">
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        FFMPEG · FILTER CHAIN
      </text>
      {["trim", "setpts", "lut3d", "drawtext", "xfade", "h264_nvenc"].map((step, i) => (
        <g key={step} transform={`translate(${14 + i * 64}, 36)`}>
          <rect width="56" height="22" fill="none" stroke="var(--fg-dim)" />
          <text
            x="28"
            y="15"
            fontFamily="JetBrains Mono"
            fontSize="8.5"
            fill="var(--fg-dim)"
            textAnchor="middle"
          >
            {step}
          </text>
          {i < 5 && <line x1="56" y1="11" x2="64" y2="11" stroke="var(--accent)" strokeWidth="1" />}
        </g>
      ))}
      <text
        x="14"
        y="88"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--fg-muted)"
        letterSpacing="0.18em"
      >
        RENDERING · 720p MASTER
      </text>
      <rect x="14" y="98" width="372" height="6" fill="var(--hairline)" />
      <rect x="14" y="98" width="86" height="6" fill="var(--accent)">
        <animate attributeName="width" values="14;360;14" dur="6s" repeatCount="indefinite" />
      </rect>
      <text x="386" y="124" fontFamily="JetBrains Mono" fontSize="9" fill="var(--accent)" textAnchor="end">
        frame 840/1800
      </text>
    </svg>
  );
}
