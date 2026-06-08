"use client";

import { useEffect, useState, useCallback } from "react";
import { Command } from "cmdk";
import { Search, Wand2, Play, Pause, Settings, Film, Type, Music, Zap, RotateCcw, Save } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";

export interface CommandAction {
  id: string;
  title: string;
  shortcut?: string;
  icon: React.ReactNode;
  section: string;
  perform: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actions: CommandAction[];
}

export function CommandPalette({ open, onOpenChange, actions }: CommandPaletteProps) {
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const grouped = actions.reduce((acc, action) => {
    acc[action.section] = acc[action.section] || [];
    acc[action.section].push(action);
    return acc;
  }, {} as Record<string, CommandAction[]>);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 gap-0 bg-zinc-950 border-zinc-800 text-zinc-100 max-w-lg overflow-hidden">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <Command
          label="Command palette"
          className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-zinc-500 [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-0 [&_[cmdk-group]]:px-2 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3 [&_[cmdk-item]_svg]:h-4 [&_[cmdk-item]_svg]:w-4"
        >
          <div className="flex items-center border-b border-zinc-800 px-3">
            <Search className="h-4 w-4 text-zinc-500 mr-2" />
            <Command.Input
              value={search}
              onValueChange={setSearch}
              placeholder="Type a command or search..."
              className="flex-1 bg-transparent h-12 text-sm outline-none placeholder:text-zinc-600 text-zinc-100"
            />
          </div>
          <Command.List className="max-h-[420px] overflow-y-auto py-2">
            <Command.Empty className="py-8 text-center text-sm text-zinc-500">
              No commands found.
            </Command.Empty>
            {Object.entries(grouped).map(([section, items]) => (
              <Command.Group
                key={section}
                heading={section}
                className="px-2 text-xs font-medium text-zinc-500 uppercase tracking-wider mb-1 mt-2"
              >
                {items.map((action) => (
                  <Command.Item
                    key={action.id}
                    value={`${action.title} ${action.section}`}
                    onSelect={() => {
                      action.perform();
                      onOpenChange(false);
                    }}
                    className="flex items-center justify-between px-2 py-2 rounded-md text-sm text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100 cursor-pointer aria-selected:bg-zinc-900 aria-selected:text-zinc-100"
                  >
                    <div className="flex items-center gap-2">
                      {action.icon}
                      <span>{action.title}</span>
                    </div>
                    {action.shortcut && (
                      <kbd className="text-[10px] bg-zinc-900 border border-zinc-800 rounded px-1.5 py-0.5 text-zinc-500">
                        {action.shortcut}
                      </kbd>
                    )}
                  </Command.Item>
                ))}
              </Command.Group>
            ))}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

export function useCommandPalette(actions: CommandAction[]) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return { open, setOpen, CommandPalette: () => <CommandPalette open={open} onOpenChange={setOpen} actions={actions} /> };
}
