"use client";

import { useState, useEffect } from "react";
import { use } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import { Bot } from "lucide-react";
import { Tooltip } from "@/components/Tooltip";

interface AgentRecord {
    id: string;
    display_name: string;
    description: string | null;
    skill_ids: string[];
}

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

    // Agent settings state
    const [allAgents, setAllAgents] = useState<AgentRecord[]>([]);
    const [enabledAgentIds, setEnabledAgentIds] = useState<Set<string>>(new Set());
    const [defaultAgentId, setDefaultAgentId] = useState<string>("");
    const [agentSaving, setAgentSaving] = useState(false);
    const [agentSaveStatus, setAgentSaveStatus] = useState("");

    useEffect(() => {
        loadData();
    }, [projectId]);

    const loadData = async () => {
        setLoading(true);
        try {
            const [promptRes, agentsRes, enabledRes] = await Promise.all([
                apiFetch(`/api/agents/project/${projectId}/prompt`),
                apiFetch("/api/agents/registry"),
                apiFetch(`/api/agents/project/${projectId}/enabled-agents`),
            ]);
            const promptData = await promptRes.json();
            setPrompt(promptData.content || "");
            setInitialPrompt(promptData.content || "");

            const agentsData = await agentsRes.json();
            setAllAgents(agentsData.agents ?? []);

            const enabledData = await enabledRes.json();
            const enabledIds = new Set<string>(enabledData.enabled_agent_ids ?? []);
            setEnabledAgentIds(enabledIds);
            const loadedDefault = enabledData.default_agent_id ?? "";
            if (loadedDefault) {
                setDefaultAgentId(loadedDefault);
            } else if (enabledIds.size > 0) {
                setDefaultAgentId(Array.from(enabledIds)[0]);
            } else {
                setDefaultAgentId("");
            }
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

    const toggleEnabledAgent = (agentId: string) => {
        setEnabledAgentIds((prev) => {
            const next = new Set(prev);
            if (next.has(agentId)) {
                next.delete(agentId);
                // Move default when the current default gets disabled.
                if (defaultAgentId === agentId) {
                    setDefaultAgentId(next.size > 0 ? Array.from(next)[0] : "");
                }
            } else {
                next.add(agentId);
                // Auto-assign default when enabling first agent.
                if (!defaultAgentId) {
                    setDefaultAgentId(agentId);
                }
            }
            return next;
        });
    };

    const hasEnabledAgents = enabledAgentIds.size > 0;
    const defaultInEnabled = !!defaultAgentId && enabledAgentIds.has(defaultAgentId);
    const agentSaveBlocked = !hasEnabledAgents || !defaultInEnabled;

    const saveAgentSettings = async () => {
        if (agentSaveBlocked) return;
        setAgentSaving(true);
        setAgentSaveStatus("");
        try {
            const response = await apiFetch(
                `/api/agents/project/${projectId}/enabled-agents`,
                {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        enabled_agent_ids: Array.from(enabledAgentIds),
                        default_agent_id: defaultAgentId,
                    }),
                }
            );
            if (response.ok) {
                setAgentSaveStatus("✅ Saved successfully!");
                setTimeout(() => setAgentSaveStatus(""), 3000);
            } else {
                const err = await response.json();
                setAgentSaveStatus(`❌ ${err.detail || "Save failed"}`);
            }
        } catch (error) {
            console.error("Agent save error:", error);
            setAgentSaveStatus("❌ Save failed");
        } finally {
            setAgentSaving(false);
        }
    };

    return (
        <div className="h-screen flex flex-col bg-gray-950 overflow-y-auto">
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
            <div className="flex-1 p-6">
                {loading ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4">
                        <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin"></div>
                        <p className="text-gray-400">Loading settings...</p>
                    </div>
                ) : (
                    <div className="max-w-4xl mx-auto space-y-10">
                        {/* System Instructions Section */}
                        <div className="space-y-4">
                            <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                                <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <span className="text-cyan-500">◈</span> Current System Instructions
                                    <Tooltip
                                        text="このプロジェクトのAIに与える基本的な指示です。エージェントの人格・役割・制約などを自由に記述できます。"
                                        position="right"
                                    />
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
                                        <div className="max-h-48 overflow-y-auto pr-1">
                                            <MarkdownRenderer content={initialPrompt} />
                                        </div>
                                    ) : (
                                        <div className="text-center py-12">
                                            <p className="text-gray-600 italic">No custom instructions defined yet.</p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* Agent Settings Section */}
                        <div className="space-y-4">
                            <div className="flex items-center border-b border-gray-800 pb-2">
                                <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                    <Bot size={14} className="text-cyan-500" />
                                    Agent Settings
                                    <Tooltip
                                        text="プロジェクトで使用するエージェントを設定します。エージェントはスキル（使えるツールセット）を持ち、タスク実行時にデフォルトエージェントのスキルが適用されます。"
                                        position="right"
                                    />
                                </h2>
                            </div>

                            {allAgents.length === 0 ? (
                                <div className="bg-gray-900/30 border border-gray-800/50 rounded-2xl p-8 text-center">
                                    <p className="text-gray-500 text-sm">
                                        No agents defined yet.{" "}
                                        <Link href="/agents" className="text-cyan-400 hover:underline">
                                            Create agents
                                        </Link>{" "}
                                        to assign them to this project.
                                    </p>
                                </div>
                            ) : (
                                <div className="bg-gray-900/30 border border-gray-800/50 rounded-2xl p-6 space-y-5">
                                    {/* Enabled Agents */}
                                    <div>
                                        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                                            Enabled Agents
                                            <Tooltip
                                                text="このプロジェクトで利用可能にするエージェントを選択します。有効化されたエージェントのみデフォルト候補になれます。"
                                                position="right"
                                            />
                                        </h3>
                                        <div className="space-y-2">
                                            {allAgents.map((agent) => {
                                                const enabled = enabledAgentIds.has(agent.id);
                                                return (
                                                    <label
                                                        key={agent.id}
                                                        className={`flex items-start gap-3 p-3 rounded-xl cursor-pointer border transition-colors ${
                                                            enabled
                                                                ? "border-cyan-500/40 bg-cyan-500/5"
                                                                : "border-gray-700 hover:border-gray-600"
                                                        }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={enabled}
                                                            onChange={() => toggleEnabledAgent(agent.id)}
                                                            className="mt-0.5 accent-cyan-500"
                                                        />
                                                        <div className="min-w-0">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                                <span className="text-sm font-medium text-white">
                                                                    {agent.display_name}
                                                                </span>
                                                                {agent.skill_ids.length > 0 && (
                                                                    <div className="flex flex-wrap gap-1">
                                                                        {agent.skill_ids.map((s) => (
                                                                            <span
                                                                                key={s}
                                                                                className="px-1.5 py-0 bg-gray-800 text-gray-400 rounded text-[10px]"
                                                                            >
                                                                                {s}
                                                                            </span>
                                                                        ))}
                                                                    </div>
                                                                )}
                                                            </div>
                                                            {agent.description && (
                                                                <p className="text-xs text-gray-500 mt-0.5">
                                                                    {agent.description}
                                                                </p>
                                                            )}
                                                        </div>
                                                    </label>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Default Agent */}
                                    <div>
                                        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                                            Default Agent
                                            <Tooltip
                                                text="チャット実行時に使用するエージェントです。未設定の場合はすべてのスキルが有効になります。有効化されたエージェントの中から選択してください。"
                                                position="right"
                                            />
                                        </h3>
                                        <select
                                            value={defaultAgentId}
                                            onChange={(e) => setDefaultAgentId(e.target.value)}
                                            disabled={!hasEnabledAgents}
                                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 transition-colors"
                                        >
                                            {!hasEnabledAgents && (
                                                <option value="">Select enabled agents first</option>
                                            )}
                                            {allAgents
                                                .filter((a) => enabledAgentIds.has(a.id))
                                                .map((a) => (
                                                    <option key={a.id} value={a.id}>
                                                        {a.display_name}
                                                    </option>
                                                ))}
                                        </select>
                                        {!hasEnabledAgents && (
                                            <p className="text-xs text-amber-400 mt-1">
                                                Enable at least one agent.
                                            </p>
                                        )}
                                        {hasEnabledAgents && agentSaveBlocked && (
                                            <p className="text-xs text-amber-400 mt-1">
                                                The selected default agent must be included in enabled agents.
                                            </p>
                                        )}
                                    </div>

                                    {/* Save Button */}
                                    <div className="flex items-center gap-4 pt-2">
                                        <button
                                            onClick={saveAgentSettings}
                                            disabled={agentSaving || agentSaveBlocked}
                                            className="px-5 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded-lg text-sm font-semibold transition-colors"
                                        >
                                            {agentSaving ? "Saving..." : "💾 Save Agent Settings"}
                                        </button>
                                        {agentSaveStatus && (
                                            <span className="text-sm animate-pulse">{agentSaveStatus}</span>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
