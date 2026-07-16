import type { CutList } from "@ai-video-editor/shared-types";
import {
  EDIT_VERB,
  type EditVerb,
  type ParsedCommand,
  parsedCommandSchema,
} from "@ai-video-editor/shared-types";

export interface VerbMatcher {
  verb: EditVerb;
  patterns: RegExp[];
  paramExtractor: (prompt: string, cutList?: CutList) => ParsedCommand["params"] | null;
  confidence: number;
}

function parseSlotIndex(match: string, cutList?: CutList): number {
  const lower = match.toLowerCase();
  if (lower === "first") return 0;
  if (lower === "last") {
    const len = cutList?.slots?.length ?? 1;
    return Math.max(0, len - 1);
  }
  if (lower === "next") return Math.min(1, (cutList?.slots?.length ?? 1) - 1);
  return Math.max(0, parseInt(match, 10));
}

function parseDuration(prompt: string): number | undefined {
  const m = prompt.match(/(\d+(?:\.\d+)?)\s*(?:second|seconds|sec|s)\b/i);
  return m ? parseFloat(m[1]) : undefined;
}

const matchers: VerbMatcher[] = [
  {
    verb: "trim_slot",
    patterns: [
      /trim\s+(?:slot\s+)?(\d+|first|last|next)\b/i,
      /make\s+(?:slot\s+)?(\d+|first|last)\s+(?:shorter|longer)\b/i,
    ],
    paramExtractor: (prompt, cutList) => {
      const m = prompt.match(/(?:slot\s+)?(\d+|first|last|next)\b/i);
      if (!m) return null;
      return {
        slotIndex: parseSlotIndex(m[1], cutList),
        durationS: parseDuration(prompt),
      };
    },
    confidence: 0.9,
  },
  {
    verb: "zoom_in",
    patterns: [/zoom\s+in/i, /add\s+a?\s*zoom[-\s]?in/i, /punch\s+in/i],
    paramExtractor: (prompt, cutList) => {
      const m = prompt.match(/(?:slot|clip)\s+(\d+|first|last|next)\b/i);
      return { slotIndex: m ? parseSlotIndex(m[1], cutList) : 0 };
    },
    confidence: 0.85,
  },
  {
    verb: "apply_filter",
    patterns: [
      /apply\s+(?:a\s+)?(film[-\s]?grain|vignette|glitch|shake|color[-\s]?pop|chromatic[-\s]?aberration)\s+(?:filter\s+)?(?:to|on)/i,
      /add\s+(?:a\s+)?(film[-\s]?grain|vignette|glitch|shake|color[-\s]?pop|chromatic[-\s]?aberration)\s+(?:filter\s+)?(?:to|on)/i,
    ],
    paramExtractor: (prompt, cutList) => {
      const typeMatch = prompt.match(
        /(film[-\s]?grain|vignette|glitch|shake|color[-\s]?pop|chromatic[-\s]?aberration)/i,
      );
      const slotMatch = prompt.match(/(?:slot|clip)\s+(\d+|first|last|next)\b/i);
      if (!typeMatch) return null;
      const typeMap: Record<string, string> = {
        filmgrain: "film_grain",
        "film-grain": "film_grain",
        vignette: "vignette",
        glitch: "glitch",
        shake: "shake",
        colorpop: "color_pop",
        "color-pop": "color_pop",
        chromaticaberration: "chromatic_aberration",
        "chromatic-aberration": "chromatic_aberration",
      };
      const normalized = typeMatch[1].toLowerCase().replace(/[-\s]/g, "");
      return {
        slotIndex: slotMatch ? parseSlotIndex(slotMatch[1], cutList) : 0,
        effectType: typeMap[normalized] ?? normalized,
      };
    },
    confidence: 0.85,
  },
  {
    verb: "add_text_overlay",
    patterns: [
      /add\s+text\s+["']?([^"']+)["']?/i,
      /text\s+["']?([^"']+)["']?/i,
      /add\s+a?\s*(title|caption)\s+["']?([^"']+)["']?/i,
    ],
    paramExtractor: (prompt) => {
      const m =
        prompt.match(/add\s+text\s+["']?([^"']+)["']?/i) ||
        prompt.match(/text\s+["']?([^"']+)["']?/i) ||
        prompt.match(/add\s+a?\s*(?:title|caption)\s+["']?([^"']+)["']?/i);
      if (!m) return null;
      const duration = parseDuration(prompt) ?? 2;
      return { text: m[1].trim(), startS: 0, durationS: duration };
    },
    confidence: 0.85,
  },
  {
    verb: "set_transition",
    patterns: [
      /(?:set|use|change)\s+(?:the\s+)?transition\s+(?:to\s+)?(fade|dissolve|slide|zoom|hard[-\s]?cut)/i,
      /transition\s+(?:to\s+)?(fade|dissolve|slide|zoom|hard[-\s]?cut)/i,
    ],
    paramExtractor: (prompt, cutList) => {
      const m = prompt.match(/(?:fade|dissolve|slide|zoom|hard[-\s]?cut)/i);
      if (!m) return null;
      const normalized = m[0].toLowerCase().replace("-", "_");
      const slotMatch = prompt.match(/(?:slot|clip)\s+(\d+|first|last|next)\b/i);
      return {
        slotIndex: slotMatch ? parseSlotIndex(slotMatch[1], cutList) : undefined,
        transition: normalized,
      };
    },
    confidence: 0.8,
  },
  {
    verb: "change_tempo",
    patterns: [/speed\s+up/i, /slow\s+down/i, /change\s+(?:the\s+)?tempo/i, /make\s+it\s+(?:faster|slower)/i],
    paramExtractor: (prompt) => {
      const direction = /slow|slower/.test(prompt) ? "slower" : "faster";
      return { direction };
    },
    confidence: 0.75,
  },
];

export function parseCommand(prompt: string, cutList?: CutList): ParsedCommand | null {
  const normalized = prompt.trim();
  if (!normalized) return null;

  for (const matcher of matchers) {
    for (const pattern of matcher.patterns) {
      if (pattern.test(normalized)) {
        const params = matcher.paramExtractor(normalized, cutList);
        if (params !== null) {
          return parsedCommandSchema.parse({
            verb: matcher.verb,
            params,
            confidence: matcher.confidence,
            matchedPhrase: normalized,
          });
        }
      }
    }
  }
  return null;
}

export function listVerbs(): EditVerb[] {
  return [...EDIT_VERB];
}
