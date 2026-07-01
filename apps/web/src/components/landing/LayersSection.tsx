"use client";

// Stencil Layers — interactive picker. Six toggleable layers, each with a mini
// animated preview. Cuts/timing is always-on (locked). Footer tallies render
// time + cost based on what's enabled. Ported from cinema-layers.jsx.

import { useMemo, useState } from "react";
import { LAYERS } from "./data";
import { asset } from "./images";

type LayerId = "cuts" | "transitions" | "grade" | "text" | "motion" | "beat";

export function LayersSection({ onCta }: { onCta?: () => void }) {
  const [enabled, setEnabled] = useState<Record<LayerId, boolean>>({
    cuts: true,
    transitions: true,
    grade: true,
    text: false,
    motion: false,
    beat: true,
  });

  const toggle = (id: string) => {
    if (id === "cuts") return; // locked
    setEnabled((e) => ({ ...e, [id]: !e[id as LayerId] }));
  };

  const totals = useMemo(() => {
    let cost = 0;
    let time = 0;
    let on = 0;
    LAYERS.forEach((l) => {
      if (enabled[l.id as LayerId]) {
        cost += l.cost;
        time += l.time;
        on++;
      }
    });
    return {
      cost: (cost / 100).toFixed(2),
      time: `${Math.floor(time / 60)}m ${time % 60}s`,
      on,
    };
  }, [enabled]);

  return (
    <section id="layers" className="section container">
      <div className="section-head">
        <span className="num">§ 02 · Pick your layers</span>
        <h2>
          Choose what to <em>borrow.</em>
        </h2>
        <p className="descr">
          Every reference video has six things Stencil can lift:{" "}
          <em>cuts, transitions, grade, text, camera motion, and beat sync.</em> Take all of them — or just
          one. The picker is the prompt.
        </p>
      </div>

      <div className="layers-grid">
        {LAYERS.map((layer) => {
          const isOn = enabled[layer.id as LayerId];
          return (
            <div
              key={layer.id}
              className={"layer-card" + (isOn ? " on" : "") + (layer.locked ? " locked" : "")}
              onClick={() => toggle(layer.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  toggle(layer.id);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <div className="layer-card-head">
                <span className="layer-short">{layer.short}</span>
                <LayerToggle on={isOn} locked={!!layer.locked} />
              </div>

              <div className="layer-preview">
                <LayerPreview id={layer.id} on={isOn} />
              </div>

              <div className="layer-meta">
                <div className="layer-name">
                  <em>{layer.name}</em>
                </div>
                <p className="layer-desc">{layer.desc}</p>
                <div className="layer-detail">
                  <span>{layer.detail}</span>
                  <span>+${(layer.cost / 100).toFixed(2)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="layers-summary">
        <div className="lsum-cell">
          <div className="lsum-k">Layers active</div>
          <div className="lsum-v">{totals.on} / 6</div>
        </div>
        <div className="lsum-cell">
          <div className="lsum-k">Render time</div>
          <div className="lsum-v">{totals.time}</div>
        </div>
        <div className="lsum-cell">
          <div className="lsum-k">Cost per render</div>
          <div className="lsum-v accent">${totals.cost}</div>
        </div>
        <div className="lsum-cell lsum-cta">
          <button type="button" className="btn btn-primary" onClick={onCta}>
            Render this preset →
          </button>
        </div>
      </div>
    </section>
  );
}

function LayerToggle({ on, locked }: { on: boolean; locked: boolean }) {
  return (
    <span className={"layer-toggle" + (on ? " on" : "") + (locked ? " locked" : "")}>
      <span className="layer-toggle-knob" />
      <span className="layer-toggle-lbl">{locked ? "LOCKED" : on ? "ON" : "OFF"}</span>
    </span>
  );
}

function LayerPreview({ id, on }: { id: string; on: boolean }) {
  if (id === "cuts") return <CutsPreview on={on} />;
  if (id === "transitions") return <TransitionsPreview on={on} />;
  if (id === "grade") return <GradePreview on={on} />;
  if (id === "text") return <TextPreview on={on} />;
  if (id === "motion") return <MotionPreview on={on} />;
  if (id === "beat") return <BeatPreview on={on} />;
  return null;
}

function CutsPreview({ on }: { on: boolean }) {
  const shots = [
    { w: 22, c: "#1d3540" },
    { w: 18, c: "#d4814c" },
    { w: 14, c: "#1e4248" },
    { w: 28, c: "#dc6428" },
    { w: 18, c: "#3a5860" },
  ];
  let x = 8;
  return (
    <svg viewBox="0 0 200 96" width="100%" height="100%" preserveAspectRatio="none">
      <rect width="200" height="96" fill="rgba(0,0,0,0.2)" />
      {shots.map((s, i) => {
        const el = (
          <g key={i}>
            <rect
              x={x}
              y={28}
              width={s.w * 1.6}
              height={40}
              fill={on ? s.c : "var(--bg)"}
              stroke={on ? "transparent" : "var(--hairline)"}
              opacity={on ? 0.85 : 0.4}
            />
            {on && i > 0 && <line x1={x} x2={x} y1={20} y2={76} stroke="var(--accent)" strokeWidth="1.2" />}
          </g>
        );
        x += s.w * 1.6 + 2;
        return el;
      })}
      <text
        x="8"
        y="14"
        fontFamily="JetBrains Mono"
        fontSize="7.5"
        fill={on ? "var(--accent)" : "var(--fg-muted)"}
        letterSpacing="0.16em"
      >
        {on ? "24 SHOTS · 5 SECTIONS" : "— DISABLED —"}
      </text>
      <text
        x="8"
        y="88"
        fontFamily="JetBrains Mono"
        fontSize="6.5"
        fill="var(--fg-muted)"
        letterSpacing="0.14em"
      >
        REF/CUT
      </text>
    </svg>
  );
}

function TransitionsPreview({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 200 96" width="100%" height="100%" preserveAspectRatio="none">
      <rect width="200" height="96" fill="rgba(0,0,0,0.2)" />
      <rect
        x="8"
        y="22"
        width="86"
        height="56"
        fill={on ? "#1d3540" : "var(--bg)"}
        stroke={on ? "transparent" : "var(--hairline)"}
        opacity={on ? 0.9 : 0.4}
      />
      <rect
        x="106"
        y="22"
        width="86"
        height="56"
        fill={on ? "#dc6428" : "var(--bg)"}
        stroke={on ? "transparent" : "var(--hairline)"}
        opacity={on ? 0.9 : 0.4}
      />
      {on && (
        <>
          {[0, 1, 2, 3, 4].map((i) => (
            <rect key={i} x={94 + i * 2} y="22" width="1.5" height="56" fill="#fff" opacity={0.18 + i * 0.12}>
              <animate
                attributeName="opacity"
                values={`${0.1 + i * 0.12};${0.6 - i * 0.08};${0.1 + i * 0.12}`}
                dur="1.6s"
                repeatCount="indefinite"
                begin={`${i * 0.05}s`}
              />
            </rect>
          ))}
          <rect x="108" y="32" width="80" height="3" fill="#ff4d1f" opacity="0.7">
            <animate attributeName="x" values="106;110;108" dur="0.4s" repeatCount="indefinite" />
          </rect>
          <rect x="108" y="58" width="80" height="3" fill="#2ec4b6" opacity="0.7">
            <animate attributeName="x" values="110;106;108" dur="0.4s" repeatCount="indefinite" />
          </rect>
        </>
      )}
      <text
        x="8"
        y="14"
        fontFamily="JetBrains Mono"
        fontSize="7.5"
        fill={on ? "var(--accent)" : "var(--fg-muted)"}
        letterSpacing="0.16em"
      >
        {on ? "WHIP · ZOOM · GLITCH · RAMP" : "— DISABLED —"}
      </text>
      <text
        x="8"
        y="88"
        fontFamily="JetBrains Mono"
        fontSize="6.5"
        fill="var(--fg-muted)"
        letterSpacing="0.14em"
      >
        REF/TRN
      </text>
    </svg>
  );
}

function GradePreview({ on }: { on: boolean }) {
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: "rgba(0,0,0,0.2)",
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", inset: "22px 102px 14px 8px", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: `url(${asset("demo-before.jpg")})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            filter: "grayscale(1) brightness(0.85)",
            opacity: on ? 0.9 : 0.45,
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 4,
            left: 6,
            fontFamily: "var(--mono)",
            fontSize: 7,
            color: "rgba(255,255,255,0.85)",
            letterSpacing: "0.18em",
            textShadow: "0 1px 2px rgba(0,0,0,0.7)",
          }}
        >
          RAW
        </div>
      </div>
      <div style={{ position: "absolute", inset: "22px 8px 14px 102px", overflow: "hidden" }}>
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: on ? `url(${asset("demo-after.jpg")})` : `url(${asset("demo-before.jpg")})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            filter: on ? "none" : "grayscale(1) brightness(0.85)",
            opacity: on ? 1 : 0.45,
            transition: "filter .3s, opacity .3s",
          }}
        />
        <div
          style={{
            position: "absolute",
            top: 4,
            left: 6,
            fontFamily: "var(--mono)",
            fontSize: 7,
            color: "rgba(255,255,255,0.95)",
            letterSpacing: "0.18em",
            textShadow: "0 1px 2px rgba(0,0,0,0.7)",
          }}
        >
          {on ? "GRADED" : "RAW"}
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          top: 22,
          bottom: 14,
          left: "50%",
          width: 1,
          background: "rgba(255,255,255,0.4)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 4,
          left: 8,
          fontFamily: "var(--mono)",
          fontSize: 7.5,
          color: on ? "var(--accent)" : "var(--fg-muted)",
          letterSpacing: "0.16em",
          textTransform: "uppercase",
        }}
      >
        {on ? "33³ LUT · TEAL/ORANGE · MATCHED" : "— DISABLED —"}
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 2,
          left: 8,
          fontFamily: "var(--mono)",
          fontSize: 6.5,
          color: "var(--fg-muted)",
          letterSpacing: "0.14em",
        }}
      >
        REF/LUT
      </div>
    </div>
  );
}

function TextPreview({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 200 96" width="100%" height="100%" preserveAspectRatio="none">
      <rect width="200" height="96" fill="rgba(0,0,0,0.2)" />
      <rect
        x="8"
        y="22"
        width="184"
        height="56"
        fill={on ? "#1a2228" : "var(--bg)"}
        stroke={on ? "transparent" : "var(--hairline)"}
        opacity={on ? 0.9 : 0.4}
      />
      {on && (
        <>
          <text
            x="100"
            y="48"
            fontFamily="Instrument Serif"
            fontStyle="italic"
            fontSize="22"
            fill="#fff"
            textAnchor="middle"
          >
            MIDNIGHT
            <animate
              attributeName="opacity"
              values="0;1;1;0"
              keyTimes="0;0.2;0.8;1"
              dur="2.4s"
              repeatCount="indefinite"
            />
          </text>
          <text
            x="100"
            y="66"
            fontFamily="JetBrains Mono"
            fontSize="7"
            fill="var(--accent)"
            textAnchor="middle"
            letterSpacing="0.22em"
          >
            DRIVE — ’86
            <animate
              attributeName="opacity"
              values="0;0;1;0"
              keyTimes="0;0.4;0.7;1"
              dur="2.4s"
              repeatCount="indefinite"
            />
          </text>
        </>
      )}
      <text
        x="8"
        y="14"
        fontFamily="JetBrains Mono"
        fontSize="7.5"
        fill={on ? "var(--accent)" : "var(--fg-muted)"}
        letterSpacing="0.16em"
      >
        {on ? "KINETIC TYPE · EDITABLE" : "— DISABLED —"}
      </text>
      <text
        x="8"
        y="88"
        fontFamily="JetBrains Mono"
        fontSize="6.5"
        fill="var(--fg-muted)"
        letterSpacing="0.14em"
      >
        REF/TXT
      </text>
    </svg>
  );
}

function MotionPreview({ on }: { on: boolean }) {
  return (
    <svg viewBox="0 0 200 96" width="100%" height="100%" preserveAspectRatio="none">
      <rect width="200" height="96" fill="rgba(0,0,0,0.2)" />
      <rect
        x="8"
        y="22"
        width="184"
        height="56"
        fill={on ? "#1d3540" : "var(--bg)"}
        stroke={on ? "transparent" : "var(--hairline)"}
        opacity={on ? 0.85 : 0.4}
      />
      {on && (
        <>
          <rect
            x="60"
            y="32"
            width="80"
            height="36"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="1"
            opacity="0.6"
          >
            <animate attributeName="x" values="60;40;60" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="y" values="32;26;32" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="width" values="80;120;80" dur="2.2s" repeatCount="indefinite" />
            <animate attributeName="height" values="36;48;36" dur="2.2s" repeatCount="indefinite" />
          </rect>
          <circle cx="100" cy="50" r="3" fill="#fff">
            <animate attributeName="cx" values="80;120;80" dur="2.2s" repeatCount="indefinite" />
          </circle>
        </>
      )}
      <text
        x="8"
        y="14"
        fontFamily="JetBrains Mono"
        fontSize="7.5"
        fill={on ? "var(--accent)" : "var(--fg-muted)"}
        letterSpacing="0.16em"
      >
        {on ? "PUSH · SHAKE · RAMP · FREEZE" : "— DISABLED —"}
      </text>
      <text
        x="8"
        y="88"
        fontFamily="JetBrains Mono"
        fontSize="6.5"
        fill="var(--fg-muted)"
        letterSpacing="0.14em"
      >
        REF/MOT
      </text>
    </svg>
  );
}

function BeatPreview({ on }: { on: boolean }) {
  const bars = 32;
  return (
    <svg viewBox="0 0 200 96" width="100%" height="100%" preserveAspectRatio="none">
      <rect width="200" height="96" fill="rgba(0,0,0,0.2)" />
      {Array.from({ length: bars }).map((_, i) => {
        const h = 8 + Math.abs(Math.sin(i * 0.5) * 24) + Math.abs(Math.sin(i * 0.2) * 14);
        return (
          <rect
            key={i}
            x={8 + i * 5.8}
            y={(96 - h) / 2}
            width="2"
            height={h}
            fill={on && i % 4 === 0 ? "var(--accent)" : on ? "var(--fg-dim)" : "var(--fg-muted)"}
            opacity={on ? (i % 4 === 0 ? 0.95 : 0.55) : 0.3}
          />
        );
      })}
      {on &&
        Array.from({ length: 8 }).map((_, i) => (
          <line
            key={i}
            x1={8 + i * 23.2}
            x2={8 + i * 23.2}
            y1="76"
            y2="86"
            stroke="var(--accent)"
            strokeWidth="1"
          />
        ))}
      <text
        x="8"
        y="14"
        fontFamily="JetBrains Mono"
        fontSize="7.5"
        fill={on ? "var(--accent)" : "var(--fg-muted)"}
        letterSpacing="0.16em"
      >
        {on ? "124 BPM · DOWNBEATS LOCKED" : "— DISABLED —"}
      </text>
      <text
        x="8"
        y="92"
        fontFamily="JetBrains Mono"
        fontSize="6.5"
        fill="var(--fg-muted)"
        letterSpacing="0.14em"
      >
        REF/BPM
      </text>
    </svg>
  );
}
