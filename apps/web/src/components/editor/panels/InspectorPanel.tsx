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
import type { Slot, Overlay } from "@/types/api";

interface InspectorPanelProps {
  selectedSlot: Slot | null;
  selectedSlotIndex: number | null;
  selectedOverlayId: string | null;
  overlays: Overlay[];
  onUpdateSlot: (index: number, slot: Partial<Slot>) => void;
  onUpdateOverlay: (id: string, overlay: Partial<Overlay>) => void;
  onSelectOverlay: (id: string | null) => void;
}

export function InspectorPanel({
  selectedSlot,
  selectedSlotIndex,
  selectedOverlayId,
  overlays,
  onUpdateSlot,
  onUpdateOverlay,
  onSelectOverlay,
}: InspectorPanelProps) {
  const selectedOverlay = overlays.find((o) => o.id === selectedOverlayId);

  return (
    <div className="w-[280px] border-l border-zinc-800 flex flex-col bg-zinc-950 shrink-0">
      <div className="h-10 border-b border-zinc-800 flex items-center px-3 text-xs font-medium text-zinc-400">
        Inspector
      </div>
      <ScrollArea className="flex-1 p-3">
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
