"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Send, Loader2 } from "lucide-react";

export default function NewProjectPage() {
    const [prompt, setPrompt] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const router = useRouter();

    const suggestionChips = [
        "Research project planning",
        "Python automation",
        "Data analysis",
        "Feature design",
        "Documentation",
        "Code review",
    ];

    const handleSubmit = async (inputPrompt?: string) => {
        const finalPrompt = inputPrompt || prompt;
        if (!finalPrompt.trim()) return;

        setLoading(true);
        setError("");

        try {
            const response = await apiFetch("/api/agents/project/create-from-prompt", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: finalPrompt }),
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || "Failed to create project");
            }

            const data = await response.json();
            router.push(`/projects/${data.project_id}?task_id=${data.task_id}`);
        } catch (err: any) {
            console.error("Error creating project:", err);
            setError(err.message || "Failed to create project.");
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-full px-4">
            <div className="w-full max-w-2xl space-y-8">
                {/* Greeting - Minimal & Stylish */}
                <h1 className="text-4xl md:text-5xl font-bold text-center bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
                    New Project
                </h1>

                {/* Input Area */}
                <div className="relative">
                    <div className="bg-gray-900/80 border border-gray-700/50 rounded-2xl p-4 backdrop-blur-sm focus-within:border-cyan-500/50 focus-within:ring-1 focus-within:ring-cyan-500/20 transition-all">
                        <textarea
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="What would you like to work on?"
                            disabled={loading}
                            rows={2}
                            className="w-full bg-transparent text-white placeholder-gray-500 resize-none focus:outline-none text-lg"
                        />
                        <div className="flex items-center justify-end mt-3 pt-3 border-t border-gray-800/50">
                            <button
                                onClick={() => handleSubmit()}
                                disabled={loading || !prompt.trim()}
                                className="flex items-center gap-2 px-5 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-800 disabled:text-gray-500 rounded-xl font-semibold text-sm transition-all shadow-lg shadow-cyan-900/20 disabled:shadow-none"
                            >
                                {loading ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        Creating...
                                    </>
                                ) : (
                                    <>
                                        <Send className="w-4 h-4" />
                                        Start
                                    </>
                                )}
                            </button>
                        </div>
                    </div>

                    {error && (
                        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
                            {error}
                        </div>
                    )}
                </div>

                {/* Suggestion Chips - Compact Grid */}
                <div className="flex flex-wrap justify-center gap-2">
                    {suggestionChips.map((chip, idx) => (
                        <button
                            key={idx}
                            onClick={() => {
                                setPrompt(chip);
                                handleSubmit(chip);
                            }}
                            disabled={loading}
                            className="px-3 py-1.5 bg-gray-800/40 hover:bg-gray-700/50 border border-gray-700/40 hover:border-cyan-500/30 rounded-full text-xs text-gray-400 hover:text-cyan-400 transition-all disabled:opacity-50"
                        >
                            {chip}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
}
