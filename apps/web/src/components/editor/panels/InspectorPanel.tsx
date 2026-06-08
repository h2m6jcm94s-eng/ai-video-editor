// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
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
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import type { Slot, Overlay, CutList, PreviewEffects } from "@/types/api";

const TRANSITIONS = ["hard_cut", "dissolve", "fade", "wipe_right", "wipe_left", "whip"] as const;

const previewEffectsSchema = z.object({
  brightness: z.number().min(0).max(2),
  contrast: z.number().min(0).max(2),
  saturation: z.number().min(0).max(2),
  blur: z.number().min(0).max(10),
  sepia: z.number().min(0).max(1),
  hueRotate: z.number().min(0).max(360),
});

const slotSchema = z.object({
  startS: z.number().min(0),
  duration_s: z.number().min(0.1),
  transitionIn: z.enum(TRANSITIONS),
  transitionOut: z.enum(TRANSITIONS),
  targetShotType: z.string().max(255),
});

const overlaySchema = z.object({
  text: z.string().max(2000),
  x: z.number(),
  y: z.number(),
});

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

  const effectsForm = useForm<z.infer<typeof previewEffectsSchema>>({
    resolver: zodResolver(previewEffectsSchema),
    defaultValues: effects,
    mode: "onChange",
  });

  useEffect(() => {
    effectsForm.reset(effects);
  }, [effectsForm, effects]);

  const slotForm = useForm<z.infer<typeof slotSchema>>({
    resolver: zodResolver(slotSchema),
    defaultValues: {
      startS: selectedSlot?.startS ?? 0,
      duration_s: selectedSlot?.duration_s ?? 0,
      transitionIn: (selectedSlot?.transitionIn as typeof TRANSITIONS[number]) ?? "hard_cut",
      transitionOut: (selectedSlot?.transitionOut as typeof TRANSITIONS[number]) ?? "hard_cut",
      targetShotType: selectedSlot?.targetShotType ?? "",
    },
    mode: "onChange",
  });

  useEffect(() => {
    if (selectedSlot && selectedSlotIndex !== null) {
      slotForm.reset({
        startS: selectedSlot.startS,
        duration_s: selectedSlot.duration_s,
        transitionIn: (selectedSlot.transitionIn as typeof TRANSITIONS[number]) ?? "hard_cut",
        transitionOut: (selectedSlot.transitionOut as typeof TRANSITIONS[number]) ?? "hard_cut",
        targetShotType: selectedSlot.targetShotType ?? "",
      });
    }
  }, [selectedSlot, selectedSlotIndex, slotForm]);

  const overlayForm = useForm<z.infer<typeof overlaySchema>>({
    resolver: zodResolver(overlaySchema),
    defaultValues: {
      text: selectedOverlay?.text ?? "",
      x: selectedOverlay?.x ?? 0,
      y: selectedOverlay?.y ?? 0,
    },
    mode: "onChange",
  });

  useEffect(() => {
    if (selectedOverlay) {
      overlayForm.reset({
        text: selectedOverlay.text ?? "",
        x: selectedOverlay.x ?? 0,
        y: selectedOverlay.y ?? 0,
      });
    }
  }, [selectedOverlay, overlayForm]);

  const updateEffect = (patch: Partial<PreviewEffects>) => {
    const next = { ...effects, ...patch };
    const parsed = previewEffectsSchema.safeParse(next);
    if (parsed.success) onUpdateEffects?.(parsed.data);
  };

  const updateSlotField = <K extends keyof z.infer<typeof slotSchema>>(
    field: K,
    value: z.infer<typeof slotSchema>[K]
  ) => {
    if (selectedSlotIndex === null) return;
    const current = slotForm.getValues();
    const next = { ...current, [field]: value };
    const parsed = slotSchema.safeParse(next);
    if (parsed.success) onUpdateSlot(selectedSlotIndex, { [field]: value });
  };

  const updateOverlayField = <K extends keyof z.infer<typeof overlaySchema>>(
    field: K,
    value: z.infer<typeof overlaySchema>[K]
  ) => {
    if (!selectedOverlay) return;
    const current = overlayForm.getValues();
    const next = { ...current, [field]: value };
    const parsed = overlaySchema.safeParse(next);
    if (parsed.success) onUpdateOverlay(selectedOverlay.id, { [field]: value });
  };

  return (
    <div className="w-[280px] border-l border-zinc-800 flex flex-col bg-zinc-950 shrink-0">
      <div className="h-10 border-b border-zinc-800 flex items-center px-3 text-xs font-medium text-zinc-400">
        Inspector
      </div>
      <ScrollArea className="flex-1 p-3">
        {onUpdateEffects && (
          <div className="space-y-3 mb-4 pb-4 border-b border-zinc-800">
            <h3 className="text-sm font-medium">Effects</h3>
            <EffectSlider label="Brightness" value={effects.brightness} min={0} max={2} step={0.05} onChange={(v) => updateEffect({ brightness: v })} />
            <EffectSlider label="Contrast" value={effects.contrast} min={0} max={2} step={0.05} onChange={(v) => updateEffect({ contrast: v })} />
            <EffectSlider label="Saturation" value={effects.saturation} min={0} max={2} step={0.05} onChange={(v) => updateEffect({ saturation: v })} />
            <EffectSlider label="Blur" value={effects.blur} min={0} max={10} step={0.5} onChange={(v) => updateEffect({ blur: v })} />
            <EffectSlider label="Sepia" value={effects.sepia} min={0} max={1} step={0.05} onChange={(v) => updateEffect({ sepia: v })} />
            <EffectSlider label="Hue Rotate" value={effects.hueRotate} min={0} max={360} step={5} onChange={(v) => updateEffect({ hueRotate: v })} />
            <button
              onClick={() => updateEffect({ brightness: 1, contrast: 1, saturation: 1, blur: 0, sepia: 0, hueRotate: 0 })}
              className="w-full py-1 text-[10px] bg-zinc-800 hover:bg-zinc-700 rounded transition text-zinc-400"
            >
              Reset
            </button>
          </div>
        )}

        {selectedSlot && selectedSlotIndex !== null && (
          <Form {...slotForm}>
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Slot {selectedSlotIndex}</h3>
              <FormField
                control={slotForm.control}
                name="startS"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Start (s)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step={0.1}
                        className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                        {...field}
                        onChange={(e) => {
                          const v = parseFloat(e.target.value);
                          field.onChange(v);
                          updateSlotField("startS", v);
                        }}
                      />
                    </FormControl>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <FormField
                control={slotForm.control}
                name="duration_s"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Duration (s)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step={0.1}
                        className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                        {...field}
                        onChange={(e) => {
                          const v = parseFloat(e.target.value);
                          field.onChange(v);
                          updateSlotField("duration_s", v);
                        }}
                      />
                    </FormControl>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <FormField
                control={slotForm.control}
                name="transitionIn"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Transition In</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        updateSlotField("transitionIn", v as typeof TRANSITIONS[number]);
                      }}
                    >
                      <FormControl>
                        <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {TRANSITIONS.map((t) => (
                          <SelectItem key={t} value={t} className="text-xs">
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <FormField
                control={slotForm.control}
                name="transitionOut"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Transition Out</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        updateSlotField("transitionOut", v as typeof TRANSITIONS[number]);
                      }}
                    >
                      <FormControl>
                        <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {TRANSITIONS.map((t) => (
                          <SelectItem key={t} value={t} className="text-xs">
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <FormField
                control={slotForm.control}
                name="targetShotType"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Shot Type</FormLabel>
                    <FormControl>
                      <Input
                        className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                        {...field}
                        onChange={(e) => {
                          field.onChange(e.target.value);
                          updateSlotField("targetShotType", e.target.value);
                        }}
                      />
                    </FormControl>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <div className="space-y-2">
                <Label className="text-xs">Speed</Label>
                <Input type="number" step={0.1} value={1} readOnly className="bg-zinc-900 border-zinc-800 h-8 text-xs opacity-50" />
              </div>
            </div>
          </Form>
        )}

        {selectedOverlay && (
          <Form {...overlayForm}>
            <div className="space-y-4 mt-4 border-t border-zinc-800 pt-4">
              <h3 className="text-sm font-medium">Overlay</h3>
              <FormField
                control={overlayForm.control}
                name="text"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="text-xs">Text</FormLabel>
                    <FormControl>
                      <Input
                        className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                        {...field}
                        onChange={(e) => {
                          field.onChange(e.target.value);
                          updateOverlayField("text", e.target.value);
                        }}
                      />
                    </FormControl>
                    <FormMessage className="text-[10px]" />
                  </FormItem>
                )}
              />
              <div className="grid grid-cols-2 gap-2">
                <FormField
                  control={overlayForm.control}
                  name="x"
                  render={({ field }) => (
                    <FormItem className="space-y-2">
                      <FormLabel className="text-xs">X</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                          {...field}
                          onChange={(e) => {
                            const v = parseFloat(e.target.value);
                            field.onChange(v);
                            updateOverlayField("x", v);
                          }}
                        />
                      </FormControl>
                      <FormMessage className="text-[10px]" />
                    </FormItem>
                  )}
                />
                <FormField
                  control={overlayForm.control}
                  name="y"
                  render={({ field }) => (
                    <FormItem className="space-y-2">
                      <FormLabel className="text-xs">Y</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                          {...field}
                          onChange={(e) => {
                            const v = parseFloat(e.target.value);
                            field.onChange(v);
                            updateOverlayField("y", v);
                          }}
                        />
                      </FormControl>
                      <FormMessage className="text-[10px]" />
                    </FormItem>
                  )}
                />
              </div>
            </div>
          </Form>
        )}

        {!selectedSlot && !selectedOverlay && (
          <p className="text-xs text-zinc-600 text-center py-8">Select a clip or overlay to edit properties</p>
        )}
      </ScrollArea>
    </div>
  );
}
