"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface SuggestedTask {
    task_name: string;
    workload: number;
    spoke: string;
    notes?: string;
    rule_type: string;
}

interface TaskDecomposerProps {
    onSelectTask: (task: SuggestedTask) => void;
    onCreateAll?: (tasks: SuggestedTask[]) => void;
    defaultContext?: string;
}

export default function TaskDecomposer({
    onSelectTask,
    onCreateAll,
    defaultContext = ""
}: TaskDecomposerProps) {
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [suggestions, setSuggestions] = useState<SuggestedTask[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState(false);

    const handleDecompose = async () => {
        if (!input.trim()) return;

        setLoading(true);
        setError(null);
        setSuggestions([]);

        try {
            const response = await apiFetch("/api/decompose", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    task_description: input,
                    max_subtasks: 5,
                    context: defaultContext || undefined
                })
            });

            if (!response.ok) {
                throw new Error("Failed to decompose task");
            }

            const data = await response.json();
            setSuggestions(data.suggested_tasks || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Decomposition failed");
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleDecompose();
        }
    };

    return (
        <div className="space-y-4">
            {/* Toggle Button */}
            <button
                type="button"
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-2 text-sm font-medium text-purple-400 hover:text-purple-300 transition-colors"
            >
                <span className="text-lg">✨</span>
                {expanded ? "Hide AI Decomposition" : "Suggest Subtasks with AI"}
                <svg
                    className={`w-4 h-4 transition-transform ${expanded ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {expanded && (
                <div className="bg-gray-800/40 border border-purple-500/20 rounded-xl p-5 space-y-4 animate-in slide-in-from-top-2 duration-200">
                    {/* Input Section */}
                    <div>
                        <label className="block text-xs font-bold text-gray-500 uppercase tracking-widest mb-2">
                            Describe your goal
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                placeholder="e.g., Plan a vacation to Japan, Move to a new apartment..."
                                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 text-sm"
                                disabled={loading}
                            />
                            <button
                                type="button"
                                onClick={handleDecompose}
                                disabled={loading || !input.trim()}
                                className="px-5 py-2 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 disabled:from-gray-700 disabled:to-gray-700 rounded-lg font-medium transition-all text-sm flex items-center gap-2 whitespace-nowrap"
                            >
                                {loading ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        Thinking...
                                    </>
                                ) : (
                                    <>
                                        <span>🤖</span>
                                        Decompose
                                    </>
                                )}
                            </button>
                        </div>
                    </div>

                    {/* Error State */}
                    {error && (
                        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center gap-2">
                            <span>⚠️</span>
                            {error}
                        </div>
                    )}

                    {/* Suggestions */}
                    {suggestions.length > 0 && (
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">
                                    Suggested Subtasks
                                </span>
                                {onCreateAll && suggestions.length > 1 && (
                                    <button
                                        type="button"
                                        onClick={() => onCreateAll(suggestions)}
                                        className="text-xs font-medium text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
                                    >
                                        <span>📋</span>
                                        Create All ({suggestions.length})
                                    </button>
                                )}
                            </div>

                            <div className="grid gap-2">
                                {suggestions.map((task, idx) => (
                                    <div
                                        key={idx}
                                        className="group bg-gray-900/50 border border-gray-700 hover:border-purple-500/50 rounded-lg p-4 flex items-center justify-between transition-all cursor-pointer"
                                        onClick={() => onSelectTask(task)}
                                    >
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-3">
                                                <span className="text-sm font-medium text-white truncate">
                                                    {task.task_name}
                                                </span>
                                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-800 text-gray-400 uppercase">
                                                    {task.spoke}
                                                </span>
                                            </div>
                                            {task.notes && (
                                                <p className="text-xs text-gray-500 mt-1 truncate">
                                                    {task.notes}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 pl-4">
                                            <div className="flex items-center gap-1">
                                                <span className="text-xs text-gray-500">Impact:</span>
                                                <span className={`text-sm font-bold tabular-nums ${task.workload >= 7 ? 'text-red-400' :
                                                        task.workload >= 4 ? 'text-amber-400' :
                                                            'text-emerald-400'
                                                    }`}>
                                                    {task.workload}
                                                </span>
                                            </div>
                                            <button
                                                type="button"
                                                className="opacity-0 group-hover:opacity-100 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 rounded-lg text-xs font-medium transition-all"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onSelectTask(task);
                                                }}
                                            >
                                                Use
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Empty State */}
                    {!loading && suggestions.length === 0 && !error && input.trim() === "" && (
                        <div className="text-center py-6 text-gray-500">
                            <p className="text-sm">
                                Enter a high-level goal and AI will suggest specific, actionable subtasks.
                            </p>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
