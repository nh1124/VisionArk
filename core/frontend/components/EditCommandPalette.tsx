"use client";

import React, { useEffect, useState } from "react";
import { Command } from "cmdk";
import {
    Wand2,
    FileText,
    Languages,
    MessageSquare,
    Zap,
    Search,
    Brain,
    X,
    Command as CmdIcon
} from "lucide-react";

interface EditCommandPaletteProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onSelectAction: (action: string) => void;
}

export default function EditCommandPalette({
    open,
    onOpenChange,
    onSelectAction
}: EditCommandPaletteProps) {
    const [inputValue, setInputValue] = useState("");

    useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                onOpenChange(!open);
            }
        };

        document.addEventListener("keydown", down);
        return () => document.removeEventListener("keydown", down);
    }, [onOpenChange, open]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && inputValue.trim()) {
            onSelectAction(inputValue);
            setInputValue("");
        }
    };

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] bg-black/40 backdrop-blur-sm px-4" onClick={() => onOpenChange(false)}>
            <div
                className="w-full max-w-xl bg-gray-900 border border-gray-800 rounded-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                <Command className="flex flex-col h-full" onKeyDown={handleKeyDown}>
                    <div className="flex items-center px-4 py-3 border-b border-gray-800 gap-3">
                        <Search className="text-gray-500" size={18} />
                        <Command.Input
                            value={inputValue}
                            onValueChange={setInputValue}
                            placeholder="Ask AI to edit canvas content..."
                            className="flex-1 bg-transparent border-none outline-none text-gray-200 placeholder:text-gray-600 text-sm"
                            autoFocus
                        />
                        <button onClick={() => onOpenChange(false)} className="text-gray-500 hover:text-white p-1 rounded-md transition-colors">
                            <X size={16} />
                        </button>
                    </div>

                    <Command.List className="max-h-[300px] overflow-y-auto p-2 scrollbar-hide">
                        <Command.Empty className="px-4 py-3 text-sm text-gray-500">No results found.</Command.Empty>

                        <Command.Group heading="QUICK ACTIONS" className="px-2 py-1 text-[10px] font-bold text-gray-600 tracking-widest uppercase">
                            <Command.Item
                                onSelect={() => onSelectAction("Summarize")}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-300 aria-selected:bg-gray-800 aria-selected:text-cyan-400 cursor-pointer transition-all"
                            >
                                <FileText size={16} />
                                <span>Summarize Content</span>
                                <span className="ml-auto text-xs text-gray-600">AI</span>
                            </Command.Item>

                            <Command.Item
                                onSelect={() => onSelectAction("Translate")}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-300 aria-selected:bg-gray-800 aria-selected:text-cyan-400 cursor-pointer transition-all"
                            >
                                <Languages size={16} />
                                <span>Translate to Japanese</span>
                                <span className="ml-auto text-xs text-gray-600">AI</span>
                            </Command.Item>

                            <Command.Item
                                onSelect={() => onSelectAction("Professional Tone")}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-300 aria-selected:bg-gray-800 aria-selected:text-cyan-400 cursor-pointer transition-all"
                            >
                                <Zap size={16} />
                                <span>Make Tone Professional</span>
                                <span className="ml-auto text-xs text-gray-600">AI</span>
                            </Command.Item>
                        </Command.Group>

                        <div className="h-px bg-gray-800 my-2 mx-2" />

                        <Command.Group heading="ADVANCED" className="px-2 py-1 text-[10px] font-bold text-gray-600 tracking-widest uppercase">
                            <Command.Item
                                onSelect={() => onSelectAction("Analyze")}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-300 aria-selected:bg-gray-800 aria-selected:text-cyan-400 cursor-pointer transition-all"
                            >
                                <Brain size={16} />
                                <span>Analyze for Improvements</span>
                            </Command.Item>

                            <Command.Item
                                onSelect={() => onSelectAction("Format")}
                                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-300 aria-selected:bg-gray-800 aria-selected:text-cyan-400 cursor-pointer transition-all"
                            >
                                <Wand2 size={16} />
                                <span>Reformat Documentation</span>
                            </Command.Item>
                        </Command.Group>
                    </Command.List>

                    <div className="px-4 py-2.5 border-t border-gray-800 bg-gray-900/50 flex items-center justify-between">
                        <div className="flex gap-4">
                            <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
                                <span className="px-1 py-0.5 bg-gray-800 border border-gray-700 rounded text-gray-400">↑↓</span>
                                <span>Navigate</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
                                <span className="px-1 py-0.5 bg-gray-800 border border-gray-700 rounded text-gray-400">Enter</span>
                                <span>Select</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-gray-600">
                            <CmdIcon size={10} />
                            <span>Vision Ark UI</span>
                        </div>
                    </div>
                </Command>
            </div>
        </div>
    );
}
