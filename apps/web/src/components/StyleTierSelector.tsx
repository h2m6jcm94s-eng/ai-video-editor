"use client";

import type { StyleTier, EditMode } from "@ai-video-editor/shared-types";
import { Scissors, Palette, Type, Sparkles, Bot, UserCheck } from "lucide-react";

interface Props {
  value: StyleTier;
  onChange: (tier: StyleTier) => void;
  mode: EditMode;
  onModeChange: (mode: EditMode) => void;
}

const tiers = [
  {
    id: "cuts_only" as StyleTier,
    label: "Cut Timing",
    description: "Beat-synced cuts and basic transitions",
    icon: Scissors,
    renderTime: "~1-2 min",
  },
  {
    id: "with_color" as StyleTier,
    label: "+ Color Grade",
    description: "Add reference LUT to your clips",
    icon: Palette,
    renderTime: "~2-3 min",
  },
  {
    id: "with_text" as StyleTier,
    label: "+ Text Overlays",
    description: "Kinetic typography from reference",
    icon: Type,
    renderTime: "~2-3 min",
  },
  {
    id: "full_style" as StyleTier,
    label: "Full Style Transfer",
    description: "Effects, motion, transitions, overlays, LUT",
    icon: Sparkles,
    renderTime: "~3-4 min",
  },
];

export function StyleTierSelector({ value, onChange, mode, onModeChange }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-slate-700">Edit Mode</label>
        <div className="flex bg-slate-100 rounded-lg p-1">
          <button
            onClick={() => onModeChange("auto")}
            className={`flex items-center space-x-1 px-3 py-1.5 rounded-md text-sm font-medium transition ${
              mode === "auto"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Bot className="w-4 h-4" />
            <span>Auto</span>
          </button>
          <button
            onClick={() => onModeChange("assisted")}
            className={`flex items-center space-x-1 px-3 py-1.5 rounded-md text-sm font-medium transition ${
              mode === "assisted"
                ? "bg-white text-indigo-600 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <UserCheck className="w-4 h-4" />
            <span>Assisted</span>
          </button>
        </div>
      </div>

      <label className="text-sm font-medium text-slate-700">Style Tier</label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {tiers.map((tier) => {
          const Icon = tier.icon;
          const selected = value === tier.id;
          return (
            <button
              key={tier.id}
              onClick={() => onChange(tier.id)}
              className={`flex items-start space-x-3 p-4 rounded-lg border-2 text-left transition ${
                selected
                  ? "border-indigo-500 bg-indigo-50"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <Icon
                className={`w-5 h-5 mt-0.5 ${
                  selected ? "text-indigo-600" : "text-slate-400"
                }`}
              />
              <div className="flex-1">
                <div
                  className={`font-medium text-sm ${
                    selected ? "text-indigo-900" : "text-slate-700"
                  }`}
                >
                  {tier.label}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">{tier.description}</div>
                <div className="text-xs text-slate-400 mt-1">{tier.renderTime}</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
