"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { Bot, Plus, Pencil, Trash2, X, GitBranch, Check } from "lucide-react";
import { Tooltip } from "@/components/Tooltip";

interface Skill {
    name: string;
    description: string;
    tools: string[];
}

interface AgentRecord {
    id: string;
    display_name: string;
    description: string | null;
    skill_ids: string[];
    graph_id: string | null;
    status: string;
    created_at: string | null;
    updated_at: string | null;
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function AgentModal({
    agent,
    skills,
    onClose,
    onSave,
}: {
    agent: AgentRecord | null;
    skills: Skill[];
    onClose: () => void;
    onSave: (data: {
        display_name: string;
        description: string;
        skill_ids: string[];
        graph_id: string | null;
    }) => Promise<void>;
}) {
    const [displayName, setDisplayName] = useState(agent?.display_name ?? "");
    const [description, setDescription] = useState(agent?.description ?? "");
    const [selectedSkills, setSelectedSkills] = useState<Set<string>>(
        new Set(agent?.skill_ids ?? [])
    );
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    const toggleSkill = (name: string) => {
        setSelectedSkills((prev) => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
        });
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!displayName.trim()) {
            setError("Display name is required.");
            return;
        }
        setSaving(true);
        setError("");
        try {
            await onSave({
                display_name: displayName.trim(),
                description: description.trim(),
                skill_ids: Array.from(selectedSkills),
                graph_id: null,
            });
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Save failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg mx-4 shadow-2xl max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-gray-800 flex-shrink-0">
                    <h2 className="text-lg font-bold text-white">
                        {agent ? "Edit Agent" : "New Agent"}
                    </h2>
                    <button
                        onClick={onClose}
                        className="text-gray-500 hover:text-white transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto">
                    {/* Display Name */}
                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1">
                            Display Name <span className="text-red-400">*</span>
                        </label>
                        <input
                            type="text"
                            value={displayName}
                            onChange={(e) => setDisplayName(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                            placeholder="e.g. Research Agent"
                        />
                    </div>

                    {/* Description */}
                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1">
                            Description
                        </label>
                        <textarea
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            rows={2}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors resize-none"
                            placeholder="Short description of what this agent does"
                        />
                    </div>

                    {/* Graph — locked to direct_assistant (future feature) */}
                    <div>
                        <div className="flex items-center gap-1.5 mb-1">
                            <GitBranch size={11} className="text-gray-500" />
                            <span className="text-xs font-medium text-gray-400">Graph</span>
                            <Tooltip
                                text="グラフはエージェントの実行フローを決定します。現在は direct_assistant のみ対応しており、将来的にカスタムグラフを選択できるようになる予定です。"
                                position="right"
                            />
                            <span className="text-[10px] text-amber-500/60 border border-amber-500/20 rounded px-1 ml-0.5">
                                coming soon
                            </span>
                        </div>
                        <div className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-500 flex items-center justify-between cursor-not-allowed select-none">
                            <span>direct_assistant (Default)</span>
                            <span className="text-[10px] text-gray-600">locked</span>
                        </div>
                    </div>

                    {/* Skills */}
                    <div>
                        <div className="flex items-center gap-1.5 mb-2">
                            <span className="text-xs font-medium text-gray-400">Skills</span>
                            <Tooltip
                                text="スキルはエージェントが使用できるツールセットを定義します。何も選択しない場合、すべてのスキルが有効になります。用途に特化させたい場合に絞り込んでください。"
                                position="right"
                            />
                        </div>
                        <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                            {skills.map((skill) => {
                                const checked = selectedSkills.has(skill.name);
                                return (
                                    <button
                                        key={skill.name}
                                        type="button"
                                        onClick={() => toggleSkill(skill.name)}
                                        className={`w-full flex items-start gap-3 p-2.5 rounded-lg text-left border transition-colors ${
                                            checked
                                                ? "border-cyan-500/50 bg-cyan-500/5"
                                                : "border-gray-700 hover:border-gray-600"
                                        }`}
                                    >
                                        <div
                                            className={`mt-0.5 w-4 h-4 flex-shrink-0 rounded border flex items-center justify-center transition-colors ${
                                                checked
                                                    ? "bg-cyan-500 border-cyan-500"
                                                    : "border-gray-600 bg-transparent"
                                            }`}
                                        >
                                            {checked && <Check size={10} className="text-white" />}
                                        </div>
                                        <div className="min-w-0">
                                            <span className="text-sm font-medium text-white">
                                                {skill.name}
                                            </span>
                                            {skill.description && (
                                                <p className="text-xs text-gray-500 mt-0.5">
                                                    {skill.description}
                                                </p>
                                            )}
                                            {skill.tools?.length > 0 && (
                                                <p className="text-[10px] text-gray-600 mt-0.5 truncate">
                                                    {skill.tools.join(", ")}
                                                </p>
                                            )}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {error && <p className="text-sm text-red-400">{error}</p>}

                    <div className="flex justify-end gap-2 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={saving}
                            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 text-white rounded-lg text-sm font-semibold transition-colors"
                        >
                            {saving ? "Saving..." : "Save"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AgentsPage() {
    const [agents, setAgents] = useState<AgentRecord[]>([]);
    const [skills, setSkills] = useState<Skill[]>([]);
    const [loading, setLoading] = useState(true);
    const [modalOpen, setModalOpen] = useState(false);
    const [editingAgent, setEditingAgent] = useState<AgentRecord | null>(null);
    const [deletingId, setDeletingId] = useState<string | null>(null);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [agentsRes, skillsRes] = await Promise.all([
                apiFetch("/api/agents/registry"),
                apiFetch("/api/agents/skills"),
            ]);
            const agentsData = await agentsRes.json();
            const skillsData = await skillsRes.json();
            setAgents(agentsData.agents ?? []);
            setSkills(skillsData.skills ?? []);
        } catch (err) {
            console.error("Failed to load agents:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async (data: {
        display_name: string;
        description: string;
        skill_ids: string[];
        graph_id: string | null;
    }) => {
        if (editingAgent) {
            const res = await apiFetch(`/api/agents/registry/${editingAgent.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error("Failed to update agent");
        } else {
            const res = await apiFetch("/api/agents/registry", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(data),
            });
            if (!res.ok) throw new Error("Failed to create agent");
        }
        setModalOpen(false);
        setEditingAgent(null);
        await loadData();
    };

    const handleDelete = async (agentId: string) => {
        setDeletingId(agentId);
        try {
            await apiFetch(`/api/agents/registry/${agentId}`, { method: "DELETE" });
            await loadData();
        } catch (err) {
            console.error("Failed to delete agent:", err);
        } finally {
            setDeletingId(null);
        }
    };

    const graphName = (id: string | null) => id ?? "direct_assistant";

    return (
        <div className="h-screen flex flex-col bg-gray-950">
            {/* Header */}
            <div className="bg-gray-900 border-b border-gray-800 p-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Bot size={24} className="text-cyan-400" />
                        <div>
                            <h1 className="text-2xl font-bold text-white">Agents</h1>
                            <p className="text-gray-400 text-sm mt-0.5">
                                Manage reusable agents across all your projects
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={() => {
                            setEditingAgent(null);
                            setModalOpen(true);
                        }}
                        className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors"
                    >
                        <Plus size={16} />
                        New Agent
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
                {loading ? (
                    <div className="flex items-center justify-center h-full gap-3">
                        <div className="w-8 h-8 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin" />
                        <p className="text-gray-400">Loading agents...</p>
                    </div>
                ) : agents.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
                        <Bot size={48} className="text-gray-700" />
                        <p className="text-gray-500 text-lg">No agents yet</p>
                        <p className="text-gray-600 text-sm max-w-xs">
                            Create your first agent to assign skills and reuse it across projects.
                        </p>
                        <button
                            onClick={() => {
                                setEditingAgent(null);
                                setModalOpen(true);
                            }}
                            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors mt-2"
                        >
                            <Plus size={16} />
                            New Agent
                        </button>
                    </div>
                ) : (
                    <div className="max-w-4xl mx-auto grid gap-4 sm:grid-cols-2">
                        {agents.map((agent) => (
                            <div
                                key={agent.id}
                                className="bg-gray-900 border border-gray-800 rounded-2xl p-5 flex flex-col gap-3 hover:border-gray-700 transition-colors"
                            >
                                {/* Header row */}
                                <div className="flex items-start justify-between gap-2">
                                    <div className="flex items-center gap-2 min-w-0">
                                        <Bot size={18} className="text-cyan-400 flex-shrink-0" />
                                        <span className="font-semibold text-white truncate">
                                            {agent.display_name}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-1 flex-shrink-0">
                                        <button
                                            onClick={() => {
                                                setEditingAgent(agent);
                                                setModalOpen(true);
                                            }}
                                            className="p-1.5 text-gray-500 hover:text-cyan-400 hover:bg-gray-800 rounded-lg transition-colors"
                                            title="Edit"
                                        >
                                            <Pencil size={14} />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(agent.id)}
                                            disabled={deletingId === agent.id}
                                            className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors"
                                            title="Delete"
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                    </div>
                                </div>

                                {/* Description */}
                                {agent.description && (
                                    <p className="text-sm text-gray-400 leading-snug">
                                        {agent.description}
                                    </p>
                                )}

                                {/* Graph badge */}
                                <div className="flex items-center gap-1.5">
                                    <GitBranch size={11} className="text-gray-600" />
                                    <span className="text-[11px] text-gray-500">
                                        {graphName(agent.graph_id)}
                                    </span>
                                    {agent.graph_id && agent.graph_id !== "direct_assistant" && (
                                        <span className="text-[9px] text-amber-500/70 border border-amber-500/20 rounded px-1">
                                            stored · pinned in engine
                                        </span>
                                    )}
                                </div>

                                {/* Skills */}
                                {agent.skill_ids.length > 0 ? (
                                    <div className="flex flex-wrap gap-1.5">
                                        {agent.skill_ids.map((s) => (
                                            <span
                                                key={s}
                                                className="px-2 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-full text-xs font-medium"
                                            >
                                                {s}
                                            </span>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-xs text-gray-600 italic">No skills assigned — all skills active</p>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Modal */}
            {modalOpen && (
                <AgentModal
                    agent={editingAgent}
                    skills={skills}
                    onClose={() => {
                        setModalOpen(false);
                        setEditingAgent(null);
                    }}
                    onSave={handleSave}
                />
            )}
        </div>
    );
}
