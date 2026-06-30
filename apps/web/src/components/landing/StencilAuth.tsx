// Split-panel auth shell for the Stencil-styled sign-in / sign-up pages.
// Left: branding panel with drifting clip frames + testimonial. Right: the
// real Clerk widget (passed as children). Ported from signin.html — design
// only; the auth flow is entirely Clerk's.
import Link from "next/link";
import { cn } from "@/lib/utils";
import "./landing.css";
import "./auth.css";

const AUTH_FRAMES = [
  "linear-gradient(135deg, #1d3540, #2a4a52)",
  "linear-gradient(150deg, #d4814c, #8a3a1a)",
  "linear-gradient(120deg, #6c7a8e, #2e3848)",
  "linear-gradient(170deg, #e8a872, #4e3624)",
  "linear-gradient(125deg, #ff4d1f, #8a2a08)",
  "linear-gradient(110deg, #2ec4b6, #1d3540)",
];

const FRAME_LAYOUT = [
  { x: 4, y: 4, w: 220, h: 124, dx: 1.6, dy: 0.9, rot: -2, dur: 14 },
  { x: 56, y: 10, w: 180, h: 320, dx: -1.2, dy: 1.4, rot: 3, dur: 18 },
  { x: 14, y: 36, w: 152, h: 152, dx: 0.8, dy: -1.1, rot: 1, dur: 22 },
  { x: 64, y: 56, w: 240, h: 135, dx: -1.4, dy: 0.7, rot: 2, dur: 16 },
  { x: -4, y: 68, w: 200, h: 250, dx: 1.5, dy: 1.2, rot: 4, dur: 19 },
  { x: 44, y: 78, w: 180, h: 100, dx: -0.7, dy: -0.9, rot: -2, dur: 13 },
];

function AuthBackdrop() {
  return (
    <>
      {FRAME_LAYOUT.map((f, i) => (
        <div
          key={i}
          className="auth-frame"
          style={
            {
              left: f.x + "%",
              top: f.y + "%",
              width: f.w + "px",
              height: f.h + "px",
              background: AUTH_FRAMES[i % AUTH_FRAMES.length],
              opacity: 0.45,
              "--dx": f.dx + "%",
              "--dy": f.dy + "%",
              "--rot": f.rot + "deg",
              "--dur": f.dur + "s",
              animationDelay: -i * 1.1 + "s",
            } as React.CSSProperties
          }
        >
          <div className="timecode">
            <span>C{String(i + 1).padStart(2, "0")}</span>
            <span>00:00:{String(i * 2).padStart(2, "0")}:00</span>
          </div>
          <div className="stripe" />
        </div>
      ))}
    </>
  );
}

export function StencilAuth({
  mode,
  className,
  children,
}: {
  mode: "signin" | "signup";
  className?: string;
  children: React.ReactNode;
}) {
  const signup = mode === "signup";
  return (
    <div className={cn("stencil", className)} data-theme="dark">
      <div className="auth-layout">
        <div className="auth-side">
          <Link className="auth-logo" href="/">
            <span className="logo-mark">
              <em>S</em>tencil
            </span>
          </Link>
          <AuthBackdrop />
          <div className="auth-side-content">
            <span className="mono accent">§ Issue №01 · May 2026</span>
            <div>
              <h2>
                {signup ? (
                  <>
                    Let’s <em>get</em>
                    <br />
                    you started.
                  </>
                ) : (
                  <>
                    Welcome <em>back.</em>
                  </>
                )}
              </h2>
            </div>
            <div>
              <p className="quote">
                “I went from spending Sunday afternoons editing a reel to spending Sunday afternoons shooting
                more reels. Stencil saved my weekends.”
              </p>
              <p className="who">— Aanya M · creator · 89k followers</p>
            </div>
          </div>
        </div>

        <div className="auth-form-side">
          <div className="auth-clerk">{children}</div>
        </div>
      </div>
    </div>
  );
}
