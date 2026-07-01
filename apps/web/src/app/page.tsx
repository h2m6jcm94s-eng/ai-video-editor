// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { stencilFontVars } from "@/components/landing/fonts";
import { LandingPage } from "@/components/landing/LandingPage";

export const metadata = {
  title: "Stencil — Recut anything in any style",
  description:
    "Drop in a reference video; Stencil parses its cuts, grade, transitions, and text, then composes the same edit with your clips and your song.",
};

export default function Home() {
  return <LandingPage className={stencilFontVars} />;
}
