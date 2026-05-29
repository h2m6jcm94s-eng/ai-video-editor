"use client";

import type { Project, Slot, CutList } from "@ai-video-editor/shared-types";
import { useState } from "react";
import { Play, Scissors, Music, Type, Palette } from "lucide-react";

interface TimelinePreviewProps {
  project: Project;
  cutList?: CutList | null;
}

export function TimelinePreview({ project, cutList }: TimelinePreviewProps) {
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null);
  const slots: Slot[] = cutList?.slots ?? [];
  const totalDuration = slots.reduce((sum, s) => sum + s.durationS, 0);

  if (!cutList || slots.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow-lg p-6 space-y-4">
        <h3 className="font-semibold text-slate-900">Generated Cut List</h3>
        <p className="text-sm text-slate-500">No cut list generated yet.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-900">Generated Cut List</h3>
        <div className="flex items-center space-x-4 text-sm text-slate-500">
          <span className="flex items-center space-x-1">
            <Scissors className="w-4 h-4" />
            <span>{slots.length} cuts</span>
          </span>
          <span className="flex items-center space-x-1">
            <Music className="w-4 h-4" />
            <span>{Math.round(cutList.globals?.tempo_bpm ?? 120)} BPM</span>
          </span>
        </div>
      </div>

      {/* Timeline visualization */}
      <div className="relative h-24 bg-slate-50 rounded-lg overflow-hidden">
        <div className="absolute inset-0 flex">
          {slots.map((slot) => {
            const widthPct = totalDuration > 0 ? (slot.durationS / totalDuration) * 100 : 0;
            return (
              <button
                key={slot.index}
                onClick={() => setSelectedSlot(slot.index)}
                className={`relative h-full border-r border-white/50 transition hover:brightness-95 ${
                  selectedSlot === slot.index ? "ring-2 ring-indigo-500 z-10" : ""
                }`}
                style={{
                  width: `${widthPct}%`,
                  backgroundColor:
                    slot.section === "intro"
                      ? "#c7d2fe"
                      : slot.section === "verse"
                      ? "#a5b4fc"
                      : slot.section === "prechorus"
                      ? "#818cf8"
                      : slot.section === "drop"
                      ? "#6366f1"
                      : "#4f46e5",
                }}
              >
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs font-medium text-white/90 truncate px-1">
                    {slot.targetShotType}
                  </span>
                </div>
                {slot.transitionIn !== "hard_cut" && (
                  <div className="absolute left-0 top-0 bottom-0 w-1 bg-white/40" />
                )}
                {slot.transitionOut !== "hard_cut" && (
                  <div className="absolute right-0 top-0 bottom-0 w-1 bg-white/40" />
                )}
              </button>
            );
          })}
        </div>

        {/* Beat markers */}
        <div className="absolute bottom-0 left-0 right-0 h-2 flex">
          {Array.from({ length: Math.ceil(totalDuration * 2) }).map((_, i) => (
            <div
              key={i}
              className="flex-1 border-r border-white/30"
              style={{
                backgroundColor: slots.some(
                  (s) => Math.abs(s.startS - i * 0.5) < 0.1
                )
                  ? "rgba(255,255,255,0.6)"
                  : "transparent",
              }}
            />
          ))}
        </div>
      </div>

      {/* Section labels */}
      <div className="flex text-xs text-slate-500">
        <span className="flex-1">Intro</span>
        <span className="flex-1">Verse</span>
        <span className="flex-1">Pre-Chorus</span>
        <span className="flex-1 text-right">Drop</span>
      </div>

      {/* Selected slot detail */}
      {selectedSlot !== null && slots[selectedSlot] && (
        <div className="border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-lg font-bold text-indigo-600">
                #{slots[selectedSlot].index + 1}
              </span>
              <span className="text-sm font-medium text-slate-700">
                {slots[selectedSlot].targetShotType}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              {project.styleTier !== "cuts_only" && (
                <Palette className="w-4 h-4 text-slate-400" />
              )}
              {project.styleTier === "with_text" || project.styleTier === "full_style" ? (
                <Type className="w-4 h-4 text-slate-400" />
              ) : null}
              <span className="text-xs text-slate-500">
                {slots[selectedSlot].durationS.toFixed(1)}s
              </span>
            </div>
          </div>

          <div className="text-sm text-slate-600">
            {slots[selectedSlot].subjectHint}
          </div>

          <div className="flex items-center space-x-4 text-xs">
            <div className="flex items-center space-x-1">
              <span className="text-slate-400">Energy:</span>
              <div className="w-16 h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-green-400 to-red-500"
                  style={{ width: `${slots[selectedSlot].energyLevel * 100}%` }}
                />
              </div>
            </div>
            <div className="flex items-center space-x-1">
              <span className="text-slate-400">Confidence:</span>
              <span
                className={`font-medium ${
                  (slots[selectedSlot].confidence || 0) > 0.85
                    ? "text-green-600"
                    : (slots[selectedSlot].confidence || 0) > 0.7
                    ? "text-yellow-600"
                    : "text-red-600"
                }`}
              >
                {((slots[selectedSlot].confidence || 0) * 100).toFixed(0)}%
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {slots[selectedSlot].requiredTags?.map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded text-xs"
              >
                {tag}
              </span>
            ))}
          </div>

          <div className="flex items-center space-x-2 pt-2">
            <button className="flex items-center space-x-1 px-3 py-1.5 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700 transition">
              <Play className="w-3 h-3" />
              <span>Preview Clip</span>
            </button>
            {project.mode === "assisted" && (
              <button className="px-3 py-1.5 border border-slate-200 text-slate-700 rounded text-sm hover:bg-slate-50 transition">
                Change Clip
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
