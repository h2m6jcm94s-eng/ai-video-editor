// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Slot, Overlay, CutList, PreviewEffects } from "@/types/api";

interface InspectorPanelProps {
  selectedSlot: Slot | null;
  selectedSlotIndex: number | null;
  selectedOverlayId: string | null;
  overlays: Overlay[];
  cutList?: CutList | null;
  onUpdateSlot: (index: number, slot: Partial<Slot>) => void;
  onUpdateOverlay: (id: string, overlay: Partial<Overlay>) => void;
  onSelectOverlay: (id: string | null) => void;
  onUpdateEffects?: (effects: PreviewEffects) => void;
}

function EffectSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between">
        <Label className="text-[10px] text-zinc-400">{label}</Label>
        <span className="text-[10px] text-zinc-500">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-cyan-500"
      />
    </div>
  );
}

export function InspectorPanel({
  selectedSlot,
  selectedSlotIndex,
  selectedOverlayId,
  overlays,
  cutList,
  onUpdateSlot,
  onUpdateOverlay,
  onSelectOverlay,
  onUpdateEffects,
}: InspectorPanelProps) {
  const selectedOverlay = overlays.find((o) => o.id === selectedOverlayId);
  const effects: PreviewEffects = cutList?.globals?.effects ?? {
    brightness: 1,
    contrast: 1,
    saturation: 1,
    blur: 0,
    sepia: 0,
    hueRotate: 0,
  };

  return (
    <div className="w-[280px] border-l border-zinc-800 flex flex-col bg-zinc-950 shrink-0">
      <div className="h-10 border-b border-zinc-800 flex items-center px-3 text-xs font-medium text-zinc-400">
        Inspector
      </div>
      <ScrollArea className="flex-1 p-3">
        {/* Global Effects */}
        {onUpdateEffects && (
          <div className="space-y-3 mb-4 pb-4 border-b border-zinc-800">
            <h3 className="text-sm font-medium">Effects</h3>
            <EffectSlider label="Brightness" value={effects.brightness} min={0} max={2} step={0.05} onChange={(v) => onUpdateEffects({ ...effects, brightness: v })} />
            <EffectSlider label="Contrast" value={effects.contrast} min={0} max={2} step={0.05} onChange={(v) => onUpdateEffects({ ...effects, contrast: v })} />
            <EffectSlider label="Saturation" value={effects.saturation} min={0} max={2} step={0.05} onChange={(v) => onUpdateEffects({ ...effects, saturation: v })} />
            <EffectSlider label="Blur" value={effects.blur} min={0} max={10} step={0.5} onChange={(v) => onUpdateEffects({ ...effects, blur: v })} />
            <EffectSlider label="Sepia" value={effects.sepia} min={0} max={1} step={0.05} onChange={(v) => onUpdateEffects({ ...effects, sepia: v })} />
            <EffectSlider label="Hue Rotate" value={effects.hueRotate} min={0} max={360} step={5} onChange={(v) => onUpdateEffects({ ...effects, hueRotate: v })} />
            <button
              onClick={() => onUpdateEffects({ brightness: 1, contrast: 1, saturation: 1, blur: 0, sepia: 0, hueRotate: 0 })}
              className="w-full py-1 text-[10px] bg-zinc-800 hover:bg-zinc-700 rounded transition text-zinc-400"
            >
              Reset
            </button>
          </div>
        )}

        {selectedSlot && selectedSlotIndex !== null && (
          <div className="space-y-4">
            <h3 className="text-sm font-medium">Slot {selectedSlotIndex}</h3>
            <div className="space-y-2">
              <Label className="text-xs">Start (s)</Label>
              <Input
                type="number"
                step={0.1}
                value={selectedSlot.start_s}
                onChange={(e) => onUpdateSlot(selectedSlotIndex, { start_s: parseFloat(e.target.value) })}
                className="bg-zinc-900 border-zinc-800 h-8 text-xs"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Duration (s)</Label>
              <Input
                type="number"
                step={0.1}
                value={selectedSlot.duration_s}
                onChange={(e) => onUpdateSlot(selectedSlotIndex, { duration_s: parseFloat(e.target.value) })}
                className="bg-zinc-900 border-zinc-800 h-8 text-xs"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Transition In</Label>
              <Select
                value={selectedSlot.transition_in}
                onValueChange={(v) => onUpdateSlot(selectedSlotIndex, { transition_in: v })}
              >
                <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["hard_cut", "dissolve", "fade", "wipe_right", "wipe_left", "whip"].map((t) => (
                    <SelectItem key={t} value={t} className="text-xs">
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Transition Out</Label>
              <Select
                value={selectedSlot.transition_out}
                onValueChange={(v) => onUpdateSlot(selectedSlotIndex, { transition_out: v })}
              >
                <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["hard_cut", "dissolve", "fade", "wipe_right", "wipe_left", "whip"].map((t) => (
                    <SelectItem key={t} value={t} className="text-xs">
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Shot Type</Label>
              <Input
                value={selectedSlot.target_shot_type}
                onChange={(e) => onUpdateSlot(selectedSlotIndex, { target_shot_type: e.target.value })}
                className="bg-zinc-900 border-zinc-800 h-8 text-xs"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Speed</Label>
              <Input
                type="number"
                step={0.1}
                value={1}
                readOnly
                className="bg-zinc-900 border-zinc-800 h-8 text-xs opacity-50"
              />
            </div>
          </div>
        )}

        {selectedOverlay && (
          <div className="space-y-4 mt-4 border-t border-zinc-800 pt-4">
            <h3 className="text-sm font-medium">Overlay</h3>
            <div className="space-y-2">
              <Label className="text-xs">Text</Label>
              <Input
                value={selectedOverlay.text || ""}
                onChange={(e) => onUpdateOverlay(selectedOverlay.id, { text: e.target.value })}
                className="bg-zinc-900 border-zinc-800 h-8 text-xs"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-2">
                <Label className="text-xs">X</Label>
                <Input
                  type="number"
                  value={selectedOverlay.x}
                  onChange={(e) => onUpdateOverlay(selectedOverlay.id, { x: parseFloat(e.target.value) })}
                  className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Y</Label>
                <Input
                  type="number"
                  value={selectedOverlay.y}
                  onChange={(e) => onUpdateOverlay(selectedOverlay.id, { y: parseFloat(e.target.value) })}
                  className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                />
              </div>
            </div>
          </div>
        )}

        {!selectedSlot && !selectedOverlay && (
          <p className="text-xs text-zinc-600 text-center py-8">Select a clip or overlay to edit properties</p>
        )}
      </ScrollArea>
    </div>
  );
}
