// Stencil typeface stack, shared by the landing page and the auth pages.
// The CSS variables are consumed by landing.css / auth.css
// (--font-stencil-serif / -body / -mono).
import { Instrument_Serif, JetBrains_Mono, Newsreader } from "next/font/google";

export const stencilSerif = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-stencil-serif",
  display: "swap",
});

export const stencilBody = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-stencil-body",
  display: "swap",
});

export const stencilMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-stencil-mono",
  display: "swap",
});

/** Space-joined font CSS-variable classes to drop on the `.stencil` wrapper. */
export const stencilFontVars = `${stencilSerif.variable} ${stencilBody.variable} ${stencilMono.variable}`;
