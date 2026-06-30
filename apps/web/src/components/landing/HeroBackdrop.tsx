"use client";

// Floating video-frame backdrop for the hero — a parallax field of "clips"
// (different aspect ratios, real footage thumbnails, timecode + label badges)
// slowly drifting. Ported from cinema-hero-bg.jsx.

import { useMemo } from "react";
import { asset } from "./images";

const FRAME_LABELS = [
  { id: "C01", lbl: "festival wide", tc: "00:00:04:12", ar: 16 / 9, img: "demo-after.jpg" },
  { id: "C02", lbl: "city POV", tc: "00:00:01:18", ar: 9 / 16, img: "usecase-tiktok.jpg" },
  { id: "C03", lbl: "house party", tc: "00:00:02:22", ar: 16 / 9, img: "demo-before.jpg" },
  { id: "C04", lbl: "raw → graded", tc: "00:00:00:14", ar: 16 / 9, img: "feature-style.jpg" },
  { id: "C05", lbl: "Iceland vlog", tc: "00:00:05:08", ar: 16 / 9, img: "usecase-travel.jpg" },
  { id: "C06", lbl: "fashion / strut", tc: "00:00:01:02", ar: 9 / 16, img: "usecase-fashion.jpg" },
  { id: "C07", lbl: "kettlebell", tc: "00:00:00:18", ar: 9 / 16, img: "usecase-fitness.jpg" },
  { id: "C08", lbl: "court / dunk", tc: "00:00:00:10", ar: 9 / 16, img: "usecase-sports.jpg" },
  { id: "C09", lbl: "FPS / glitch", tc: "00:00:03:14", ar: 16 / 9, img: "usecase-gaming.jpg" },
  { id: "C10", lbl: "ai analysis", tc: "00:00:02:04", ar: 16 / 9, img: "feature-ai.jpg" },
  { id: "C11", lbl: "cliffside vow", tc: "00:00:01:08", ar: 9 / 16, img: "usecase-wedding.jpg" },
  { id: "C12", lbl: "Malibu listing", tc: "00:00:02:18", ar: 16 / 9, img: "usecase-realestate.jpg" },
];

export function HeroBackdrop() {
  const frames = useMemo(() => {
    // Hand-tuned positions for a cinematic moodboard scatter.
    // We avoid the center band where the headline sits.
    const layout = [
      { x: 2, y: 4, base: 188, depth: 0.55, dx: 1.6, dy: 0.9, dur: 14, rot: -2 },
      { x: 18, y: 62, base: 132, depth: 0.62, dx: -1.2, dy: 1.4, dur: 18, rot: 3 },
      { x: -2, y: 38, base: 132, depth: 0.42, dx: 0.8, dy: -1.1, dur: 22, rot: 1 },
      { x: 22, y: -2, base: 132, depth: 0.5, dx: -0.9, dy: 1.2, dur: 16, rot: -3 },
      { x: 68, y: 2, base: 172, depth: 0.58, dx: -1.4, dy: 0.7, dur: 20, rot: 2 },
      { x: 86, y: 18, base: 116, depth: 0.55, dx: 1.1, dy: -1.0, dur: 15, rot: -1 },
      { x: 72, y: 56, base: 124, depth: 0.62, dx: 1.5, dy: 1.2, dur: 19, rot: 4 },
      { x: 90, y: 78, base: 108, depth: 0.45, dx: -0.7, dy: -0.9, dur: 13, rot: -2 },
      { x: -4, y: 82, base: 164, depth: 0.55, dx: 1.0, dy: -1.3, dur: 17, rot: 2 },
      { x: 36, y: 90, base: 136, depth: 0.4, dx: -1.6, dy: 0.6, dur: 21, rot: -4 },
      { x: 56, y: 92, base: 116, depth: 0.45, dx: 0.6, dy: -1.4, dur: 16, rot: 1 },
      { x: 58, y: -8, base: 124, depth: 0.4, dx: -1.2, dy: 1.1, dur: 24, rot: 3 },
    ];
    return layout.map((l, i) => {
      const meta = FRAME_LABELS[i % FRAME_LABELS.length];
      const w = l.base;
      const h = Math.round(w / meta.ar);
      return { ...l, ...meta, w, h, i };
    });
  }, []);

  return (
    <div className="hero-bg" aria-hidden="true">
      <div className="hero-bg-scrim" />
      {frames.map((f) => (
        <div
          key={f.i}
          className="hero-frame"
          style={
            {
              left: f.x + "%",
              top: f.y + "%",
              width: f.w + "px",
              height: f.h + "px",
              opacity: f.depth,
              transform: `rotate(${f.rot}deg)`,
              "--dx": f.dx + "%",
              "--dy": f.dy + "%",
              "--dur": f.dur + "s",
              "--delay": -f.i * 0.7 + "s",
            } as React.CSSProperties
          }
        >
          <div className="hero-frame-inner" style={{ backgroundImage: `url(${asset(f.img)})` }}>
            <div className="hero-frame-badge">
              <span>{f.id}</span>
              <span className="dot-mini" />
              <span>{f.tc}</span>
            </div>
            <div className="hero-frame-label">{f.lbl}</div>
            <div className="hero-frame-stripe" />
            {f.i % 3 === 0 && (
              <>
                <span className="bracket tl" />
                <span className="bracket tr" />
                <span className="bracket bl" />
                <span className="bracket br" />
              </>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
