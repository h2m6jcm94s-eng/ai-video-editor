// Static image map for the Stencil landing page.
// Images live co-located in ./assets/img and are imported so Next.js
// fingerprints + optimizes them. Components reference them by filename
// via `asset("foo.jpg")` — mirroring the original design's `assets/img/foo.jpg`.

import demoAfter from "./assets/img/demo-after.jpg";
import demoBefore from "./assets/img/demo-before.jpg";
import featureAi from "./assets/img/feature-ai.jpg";
import featureCollaborate from "./assets/img/feature-collaborate.jpg";
import featureDistribute from "./assets/img/feature-distribute.jpg";
import featureStyle from "./assets/img/feature-style.jpg";
import heroEditor from "./assets/img/hero-editor.jpg";
import usecaseFashion from "./assets/img/usecase-fashion.jpg";
import usecaseFitness from "./assets/img/usecase-fitness.jpg";
import usecaseGaming from "./assets/img/usecase-gaming.jpg";
import usecaseRealestate from "./assets/img/usecase-realestate.jpg";
import usecaseSports from "./assets/img/usecase-sports.jpg";
import usecaseTiktok from "./assets/img/usecase-tiktok.jpg";
import usecaseTravel from "./assets/img/usecase-travel.jpg";
import usecaseWedding from "./assets/img/usecase-wedding.jpg";

const IMAGES: Record<string, { src: string }> = {
  "demo-after.jpg": demoAfter,
  "demo-before.jpg": demoBefore,
  "feature-ai.jpg": featureAi,
  "feature-collaborate.jpg": featureCollaborate,
  "feature-distribute.jpg": featureDistribute,
  "feature-style.jpg": featureStyle,
  "hero-editor.jpg": heroEditor,
  "usecase-fashion.jpg": usecaseFashion,
  "usecase-fitness.jpg": usecaseFitness,
  "usecase-gaming.jpg": usecaseGaming,
  "usecase-realestate.jpg": usecaseRealestate,
  "usecase-sports.jpg": usecaseSports,
  "usecase-tiktok.jpg": usecaseTiktok,
  "usecase-travel.jpg": usecaseTravel,
  "usecase-wedding.jpg": usecaseWedding,
};

/** Resolve a landing image filename to its bundled URL. */
export function asset(filename: string): string {
  return IMAGES[filename]?.src ?? "";
}
