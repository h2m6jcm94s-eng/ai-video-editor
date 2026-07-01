"use client";

// Stencil landing page — root composition. Ported from cinema-app.jsx (+ the
// gap/tier widgets) into the app's component tree. Marketing CTAs route into
// Clerk: "Sign in" → /sign-in, conversion actions → /sign-up, "Open app" →
// /dashboard (which bounces unauthenticated users to /sign-in via middleware).

import Link from "next/link";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { COMPETITOR_COLS, COMPETITORS, TIERS, USE_CASES } from "./data";
import { HeroBackdrop } from "./HeroBackdrop";
import { asset } from "./images";
import { LayersSection } from "./LayersSection";
import { PipelinePanel } from "./PipelinePanel";
import { StudioWidget } from "./StudioWidget";
import "./landing.css";

export function LandingPage({ className }: { className?: string }) {
  const router = useRouter();
  const goSignUp = () => router.push("/sign-up");

  return (
    <div className={cn("stencil", className)} data-theme="dark">
      <TopBar />
      <main>
        <Hero />
        <UseCaseStrip />
        <HowItWorks />
        <LayersSection onCta={goSignUp} />
        <GapSection />
        <PipelineSection />
        <TiersSection />
        <CTA onSubmit={goSignUp} />
        <Footer />
      </main>
    </div>
  );
}

function TopBar() {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="logo">
          <span className="logo-mark">
            <em style={{ fontStyle: "italic", color: "var(--accent)" }}>S</em>tencil
          </span>
          <span className="logo-word">· REF.STYLE.CUT</span>
        </div>
        <nav className="nav">
          <a href="#how">How it works</a>
          <a href="#layers">Layers</a>
          <a href="#pipeline">Pipeline</a>
          <a href="#tiers">Tiers</a>
          <Link href="/pricing">Pricing</Link>
        </nav>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link className="btn-quiet mono" href="/sign-in" style={{ fontSize: "0.7rem" }}>
            Sign in
          </Link>
          <Link className="nav-cta" href="/dashboard">
            Open app →
          </Link>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="container hero">
      <HeroBackdrop />
      <div className="hero-meta">
        <div className="hero-meta-left">
          <span className="tape">
            <span className="dot" />
            Now in private beta · v0.3.1
          </span>
          <span className="mono">Issue №01 — May 2026</span>
        </div>
        <span className="mono">A reference is a stencil.</span>
      </div>

      <h1 className="hero-headline">
        Recut <em>any</em> video
        <br />
        in <em>any</em> style.
      </h1>

      <div className="hero-sub">
        <p>
          Drop in a reference video — a reel, a short, a music video, a commercial. Stencil parses its{" "}
          <em style={{ color: "var(--fg)" }}>cuts, transitions, color grade, text overlays</em>, and camera
          motion, then composes the same edit with <em style={{ color: "var(--fg)" }}>your</em> clips, on top
          of <em style={{ color: "var(--fg)" }}>your</em> song. Reels, shorts, ads, music videos — up to five
          minutes. No timeline, no keyframes, no editor needed.
        </p>
        <div>
          <div className="info-card">
            <span className="k">Reference</span>
            <span className="v">
              <em style={{ color: "var(--accent)" }}>~5 min</em> · MP4 / MOV
            </span>
            <span className="k">Your clips</span>
            <span className="v num">10 — 200 files</span>
            <span className="k">Your audio</span>
            <span className="v">song · voiceover · ≤6 min</span>
            <span className="k">Output</span>
            <span className="v">9:16 · 1:1 · 16:9</span>
            <span className="k">Render time</span>
            <span className="v num">1 – 4 min · 720p</span>
            <span className="k">Cost / render</span>
            <span className="v num">$0.39 – $0.78</span>
          </div>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#cta">
              Start a render →
            </a>
            <a className="btn btn-ghost" href="#how">
              See how it works
            </a>
          </div>
        </div>
      </div>

      <StudioWidget />
    </section>
  );
}

function UseCaseStrip() {
  return (
    <section className="usecase-strip" aria-label="What Stencil makes">
      <div className="container usecase-inner">
        <span className="mono usecase-lead">Built for</span>
        <div className="usecase-rail">
          {USE_CASES.map((u, i) => (
            <div className="usecase-chip" key={i}>
              {u.thumb && (
                <span
                  className="usecase-thumb"
                  style={{ backgroundImage: `url(${asset(u.thumb)})` }}
                  aria-hidden="true"
                />
              )}
              <span className="usecase-tag">{u.tag}</span>
              <span className="usecase-sub">{u.sub}</span>
              <span className="usecase-note">{u.note}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="section container">
      <div className="section-head">
        <span className="num">§ 01 · Workflow</span>
        <h2>
          <em>Three</em> uploads.
          <br />
          One render.
        </h2>
        <p className="descr">
          Stencil is a pipeline disguised as three drop-zones. You provide the inputs; Stencil emits a
          beat-accurate cut graded and overlaid like the reference, with your footage in the frame.
        </p>
      </div>

      <div className="steps">
        <Step
          n="01"
          title="Reference"
          body="A short video whose cut feel, color, transitions, and overlays you want to borrow. Up to five minutes. Stencil parses it once; the analysis is cached for re-renders."
          ArtComp={ReferenceArt}
        />
        <Step
          n="02"
          title="Your clips"
          body="Drag in your roll — phone footage, b-roll, takes from a shoot, or stock. Stencil segments, embeds, and indexes each clip into a searchable space."
          ArtComp={ClipsArt}
        />
        <Step
          n="03"
          title="Your audio"
          body="A song, a voiceover, or both. Stencil reads its beats, downbeats, sections, and energy curve, and snaps every cut and transition onto its grid."
          ArtComp={SongArt}
        />
      </div>
    </section>
  );
}

function Step({
  n,
  title,
  body,
  ArtComp,
}: {
  n: string;
  title: string;
  body: string;
  ArtComp: React.ComponentType;
}) {
  return (
    <div className="step">
      <span className="step-num">Step {n}</span>
      <h3>
        <em>{title}</em>
      </h3>
      <p>{body}</p>
      <div className="step-art">
        <ArtComp />
      </div>
    </div>
  );
}

function ReferenceArt() {
  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        background: "var(--bg-elev)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url(${asset("feature-ai.jpg")})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: 0.85,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(180deg, rgba(10,9,8,0.15) 0%, rgba(10,9,8,0.75) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 14,
          right: 14,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: "var(--mono)",
          fontSize: 9,
          letterSpacing: "0.18em",
          color: "rgba(255,255,255,0.85)",
          textTransform: "uppercase",
        }}
      >
        <span>
          <span
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "var(--accent)",
              marginRight: 6,
              verticalAlign: "middle",
              boxShadow: "0 0 8px var(--accent)",
            }}
          />
          PARSING · REF/01
        </span>
        <span style={{ color: "rgba(255,255,255,0.65)" }}>FRM 74931</span>
      </div>
      <span
        style={{
          position: "absolute",
          top: 28,
          left: 14,
          width: 14,
          height: 14,
          borderLeft: "1px solid var(--accent)",
          borderTop: "1px solid var(--accent)",
        }}
      />
      <span
        style={{
          position: "absolute",
          top: 28,
          right: 14,
          width: 14,
          height: 14,
          borderRight: "1px solid var(--accent)",
          borderTop: "1px solid var(--accent)",
        }}
      />
      <span
        style={{
          position: "absolute",
          bottom: 38,
          left: 14,
          width: 14,
          height: 14,
          borderLeft: "1px solid var(--accent)",
          borderBottom: "1px solid var(--accent)",
        }}
      />
      <span
        style={{
          position: "absolute",
          bottom: 38,
          right: 14,
          width: 14,
          height: 14,
          borderRight: "1px solid var(--accent)",
          borderBottom: "1px solid var(--accent)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 14,
          right: 14,
          bottom: 12,
          display: "grid",
          gridTemplateColumns: "repeat(8, 1fr)",
          gap: 3,
        }}
      >
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <div
            key={i}
            style={{
              height: 14,
              background: i === 4 ? "var(--accent)" : "rgba(255,255,255,0.18)",
              borderTop: i === 4 ? "none" : "1px solid rgba(255,255,255,0.3)",
            }}
          />
        ))}
      </div>
      <div
        style={{
          position: "absolute",
          bottom: 30,
          left: 14,
          fontFamily: "var(--mono)",
          fontSize: 8,
          letterSpacing: "0.18em",
          color: "rgba(255,255,255,0.6)",
          textTransform: "uppercase",
        }}
      >
        24 SHOTS · 5 SECTIONS · 124 BPM
      </div>
    </div>
  );
}

function ClipsArt() {
  const clips = [
    { img: "usecase-travel.jpg", id: "C01" },
    { img: "usecase-tiktok.jpg", id: "C02" },
    { img: "usecase-fashion.jpg", id: "C03" },
    { img: "usecase-fitness.jpg", id: "C04" },
    { img: "usecase-wedding.jpg", id: "C05" },
    { img: "usecase-realestate.jpg", id: "C06" },
    { img: "usecase-sports.jpg", id: "C07" },
    { img: "usecase-gaming.jpg", id: "C08" },
  ];
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gridTemplateRows: "repeat(2, 1fr)",
        gap: 4,
        padding: 10,
        height: "100%",
        background: "var(--bg-elev)",
      }}
    >
      {clips.map((c, i) => (
        <div
          key={i}
          style={{
            backgroundImage: `url(${asset(c.img)})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            position: "relative",
            boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.5)",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "linear-gradient(180deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.6) 100%)",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: 3,
              left: 5,
              fontFamily: "var(--mono)",
              fontSize: 8,
              color: "rgba(255,255,255,0.9)",
              letterSpacing: "0.12em",
              textShadow: "0 1px 3px rgba(0,0,0,0.8)",
            }}
          >
            {c.id}
          </div>
        </div>
      ))}
    </div>
  );
}

function SongArt() {
  const bars = 48;
  return (
    <svg viewBox="0 0 320 200" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
      <rect width="320" height="200" fill="var(--bg-elev)" />
      <text
        x="14"
        y="22"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--accent)"
        letterSpacing="0.18em"
      >
        124 BPM · F# MINOR
      </text>
      {Array.from({ length: bars }).map((_, i) => {
        const h = 14 + Math.abs(Math.sin(i * 0.41) * 60) + Math.abs(Math.sin(i * 0.18) * 30);
        return (
          <rect
            key={i}
            x={14 + i * 6.2}
            y={(200 - h) / 2 + 10}
            width="2.6"
            height={h}
            fill={i % 4 === 0 ? "var(--accent)" : "var(--fg-dim)"}
            opacity={i % 4 === 0 ? 0.95 : 0.65}
          />
        );
      })}
      {Array.from({ length: 8 }).map((_, i) => (
        <line
          key={i}
          x1={14 + i * 36}
          x2={14 + i * 36}
          y1={170}
          y2={180}
          stroke="var(--accent)"
          strokeWidth="1"
        />
      ))}
      <text
        x="306"
        y="194"
        fontFamily="JetBrains Mono"
        fontSize="9"
        fill="var(--fg-muted)"
        letterSpacing="0.18em"
        textAnchor="end"
      >
        SECTIONS · 5
      </text>
    </svg>
  );
}

function GapSection() {
  return (
    <section id="gap" className="section container" style={{ paddingTop: 60 }}>
      <div className="section-head">
        <span className="num">§ 03 · The gap</span>
        <h2>
          Nobody else <em>ships this.</em>
        </h2>
        <p className="descr">
          Generative tools make new pixels. Highlight extractors mine your existing footage. Template
          platforms are hand-authored. None of them take an arbitrary reference and impose its edit on{" "}
          <em>your</em> material. That’s the wedge.
        </p>
      </div>
      <GapMatrix />
      <div
        style={{
          marginTop: 24,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: "var(--mono)",
          fontSize: "0.7rem",
          textTransform: "uppercase",
          letterSpacing: "0.18em",
          color: "var(--fg-muted)",
        }}
      >
        <span>✓ ships · ~ partial · — does not</span>
        <span>Survey · April 2026</span>
      </div>
    </section>
  );
}

function GapMatrix() {
  return (
    <div className="gap-grid">
      <div className="gap-row">
        <div className="gap-cell head" />
        {COMPETITOR_COLS.map((c) => (
          <div key={c.k} className="gap-cell head">
            {c.label}
          </div>
        ))}
      </div>
      {COMPETITORS.map((row, i) => (
        <div className="gap-row" key={i}>
          <div className={"gap-cell" + (row.us ? " us" : "")}>
            <span
              style={{
                fontFamily: row.us ? "var(--serif)" : "var(--mono)",
                fontStyle: row.us ? "italic" : "normal",
                fontSize: row.us ? "1.05rem" : "0.78rem",
                color: row.us ? "var(--accent)" : "var(--fg)",
                letterSpacing: row.us ? "-0.01em" : "0.08em",
              }}
            >
              {row.name}
            </span>
          </div>
          {COMPETITOR_COLS.map((col) => {
            const val = row[col.k];
            const cls = "gap-cell" + (row.us ? " us" : "");
            return (
              <div key={col.k} className={cls}>
                {val === "✓" && <span className="check">✓</span>}
                {val === "~" && <span className="partial">~</span>}
                {val === "✗" && <span className="nope">—</span>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function PipelineSection() {
  return (
    <section id="pipeline" className="section container">
      <div className="section-head">
        <span className="num">§ 04 · Under the hood</span>
        <h2>
          Six stages.
          <br />
          One <em>contract.</em>
        </h2>
        <p className="descr">
          The cut-list — a versioned JSON schema — is the contract between the parsing pipeline and the render
          engine. Every model upstream and every codec downstream can be swapped without touching the
          compiler. That’s how Stencil rides out the next 18 months of model releases.
        </p>
      </div>
      <PipelinePanel />
    </section>
  );
}

function TiersSection() {
  return (
    <section id="tiers" className="section container">
      <div className="section-head">
        <span className="num">§ 05 · Packaged tiers</span>
        <h2>
          Pick how much of the
          <br />
          reference to <em>borrow.</em>
        </h2>
        <p className="descr">
          Stencil ships in four tiers. Cut-only is fast and cheap; full transfer emulates motion, ramps, and
          freezes. Each tier adds on top of the prior. Try the timing first, render the grade second, layer
          the typography last.
        </p>
      </div>
      <TierGrid />
    </section>
  );
}

function TierGrid() {
  return (
    <div className="tiers">
      {TIERS.map((tier, i) => {
        const first = tier.name.split(" ")[0];
        const rest = tier.name.length > first.length ? " " + tier.name.split(" ").slice(1).join(" ") : "";
        return (
          <div
            key={i}
            className="tier"
            style={
              tier.accent ? { background: "color-mix(in oklab, var(--accent) 9%, transparent)" } : undefined
            }
          >
            <div className="tier-num">{tier.n}</div>
            <div className="tier-name">
              <em>{first}</em>
              {rest}
            </div>
            <div style={{ color: "var(--fg-dim)", fontSize: 15, lineHeight: 1.5 }}>{tier.headline}</div>
            <ul>
              {tier.features.map((f, j) => (
                <li key={j} className={f.on ? "" : "off"}>
                  {f.t}
                </li>
              ))}
            </ul>
            <div className="tier-foot">
              <span>render · {tier.render}</span>
              <span className={tier.accent ? "tag accent" : "tag"}>{tier.cost} / render</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CTA({ onSubmit }: { onSubmit: () => void }) {
  return (
    <section id="cta" className="cta container">
      <div className="cta-grid">
        <div>
          <span className="eyebrow">§ 06 · Get on the list</span>
          <h2 style={{ marginTop: 18 }}>
            Bring a
            <br />
            <em>reference.</em>
          </h2>
          <p style={{ marginTop: 24, color: "var(--fg-dim)", fontSize: 18, maxWidth: 480, lineHeight: 1.5 }}>
            Private beta, May 2026. First 500 waitlist sign-ups get three free renders at every layer enabled
            — Real-ESRGAN upscale included. <em style={{ color: "var(--fg)" }}>Stencil Courses</em> — short
            classes on shooting for reels, shorts, and ads — ship later this summer.
          </p>
        </div>
        <div>
          <span className="mono">Waitlist</span>
          <form
            className="cta-form"
            onSubmit={(e) => {
              e.preventDefault();
              onSubmit();
            }}
          >
            <input type="email" placeholder="name@studio.tld" required />
            <button type="submit">Start free →</button>
          </form>
          <div
            style={{
              marginTop: 18,
              display: "flex",
              justifyContent: "space-between",
              fontFamily: "var(--mono)",
              fontSize: "0.66rem",
              textTransform: "uppercase",
              letterSpacing: "0.18em",
              color: "var(--fg-muted)",
            }}
          >
            <span>1,284 in queue</span>
            <span>est. invite · 9 days</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer container">
      <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
        <span style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 18, color: "var(--fg)" }}>
          Stencil
        </span>
        <span>© 2026 · all rights reserved</span>
      </div>
      <div style={{ display: "flex", gap: 24 }}>
        <Link href="/pricing">Pricing</Link>
        <a href="#how">How it works</a>
        <a href="#tiers">Tiers</a>
        <a href="#pipeline">Pipeline</a>
      </div>
    </footer>
  );
}
