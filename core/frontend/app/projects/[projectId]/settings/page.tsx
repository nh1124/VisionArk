"use client";

import { useState, useEffect } from "react";
import { use } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import MarkdownRenderer from "@/components/MarkdownRenderer";

export default function ProjectSettingsPage({
    params,
}: {
    params: Promise<{ projectId: string }>;
}) {
    const { projectId } = use(params);
    const [prompt, setPrompt] = useState("");
    const [initialPrompt, setInitialPrompt] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState("");
    const [isEditing, setIsEditing] = useState(false);

    useEffect(() => {
        loadData();
    }, [projectId]);

    const loadData = async () => {
        setLoading(true);
        try {
            const promptRes = await apiFetch(`/api/agents/project/${projectId}/prompt`);
            const promptData = await promptRes.json();
            setPrompt(promptData.content || "");
            setInitialPrompt(promptData.content || "");
        } catch (error) {
            console.error("Failed to load settings data:", error);
            setSaveStatus("❌ Failed to load settings");
        } finally {
            setLoading(false);
        }
    };

    const savePrompt = async () => {
        setSaving(true);
        setSaveStatus("");
        try {
            const response = await apiFetch(`/api/agents/project/${projectId}/prompt`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: prompt }),
            });

            if (response.ok) {
                setSaveStatus("✅ Saved successfully!");
                setInitialPrompt(prompt);
                setIsEditing(false);
                setTimeout(() => setSaveStatus(""), 3000);
            } else {
                setSaveStatus("❌ Save failed");
            }
        } catch (error) {
            console.error("Save error:", error);
            setSaveStatus("❌ Save failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="h-screen flex flex-col bg-gray-950">
            {/* Header */}
            <div className="bg-gray-900 border-b border-gray-800 p-6">
                <div className="flex items-center justify-between">
                    <div>
                        <Link
                            href={`/projects/${projectId}`}
                            className="text-sm text-gray-400 hover:text-cyan-400 mb-2 inline-block transition-colors"
                        >
                            ← Back to Project
                        </Link>
                        <h1 className="text-2xl font-bold text-cyan-400">
                            Project Settings
                        </h1>
                        <p className="text-gray-400 text-sm mt-1">
                            {projectId}
                        </p>
                    </div>
                    <div className="flex items-center gap-4">
                        {saveStatus && (
                            <span className="text-sm font-medium animate-pulse">{saveStatus}</span>
                        )}
                        {isEditing ? (
                            <div className="flex gap-2">
                                <button
                                    onClick={() => {
                                        setPrompt(initialPrompt);
                                        setIsEditing(false);
                                    }}
                                    className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors text-sm"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={savePrompt}
                                    disabled={saving || loading}
                                    className="px-6 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 text-white rounded-lg transition-colors font-semibold"
                                >
                                    {saving ? "Saving..." : "💾 Save Changes"}
                                </button>
                            </div>
                        ) : (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="px-6 py-2 bg-gray-800 hover:bg-gray-700 text-cyan-400 border border-cyan-400/20 rounded-lg transition-all hover:shadow-[0_0_15px_rgba(34,211,238,0.2)] font-semibold"
                            >
                                📝 Edit Prompt
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-y-auto p-6">
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4">
                        <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin"></div>
                        <p className="text-gray-400">Loading settings...</p>
                    </div>
                ) : (
                    <div className="max-w-4xl mx-auto space-y-8">
                        <div className="space-y-4">
                            <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                                <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <span className="text-cyan-500">◈</span> Current System Instructions
                                </h2>
                                {!isEditing && (
                                    <span className="text-[10px] text-gray-600 bg-gray-900 border border-gray-800 px-2 py-0.5 rounded leading-none">ReadOnly</span>
                                )}
                            </div>

                            {isEditing ? (
                                <textarea
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    className="w-full min-h-[400px] bg-gray-900/50 border border-gray-700 rounded-xl p-6 text-gray-200 font-mono text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all resize-y"
                                    placeholder="Enter instructions for this agent..."
                                />
                            ) : (
                                <div className="bg-gray-900/30 border border-gray-800/50 rounded-2xl p-8 transition-all hover:bg-gray-900/40">
                                    {initialPrompt ? (
                                        <MarkdownRenderer content={initialPrompt} />
                                    ) : (
                                        <div className="text-center py-12">
                                            <p className="text-gray-600 italic">No custom instructions defined yet.</p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
