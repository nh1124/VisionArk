"use client";

import { useState, useEffect } from "react";
import { use } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import MarkdownRenderer from "@/components/MarkdownRenderer";

interface Skill {
    id: string;
    name: string;
    description: string;
    is_active: boolean;
}

interface Node {
    id: string;
    display_name: string;
    role_name: string;
    node_type: string;
}

export default function ProjectSettingsPage({
    params,
}: {
    params: Promise<{ projectId: string }>;
}) {
    const { projectId } = use(params);
    const [activeTab, setActiveTab] = useState<"instructions" | "skills">("instructions");
    const [prompt, setPrompt] = useState("");
    const [initialPrompt, setInitialPrompt] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saveStatus, setSaveStatus] = useState("");
    const [isEditing, setIsEditing] = useState(false);

    // Skills & Nodes state
    const [allSkills, setAllSkills] = useState<Skill[]>([]);
    const [nodes, setNodes] = useState<Node[]>([]);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [assignedSkillIds, setAssignedSkillIds] = useState<string[]>([]);

    useEffect(() => {
        loadData();
    }, [projectId]);

    const loadData = async () => {
        setLoading(true);
        try {
            // Load Prompt
            const promptRes = await apiFetch(`/api/agents/project/${projectId}/prompt`);
            const promptData = await promptRes.json();
            setPrompt(promptData.content || "");
            setInitialPrompt(promptData.content || "");

            // Load All Skills
            const skillsRes = await apiFetch("/api/skills");
            const skillsData = await skillsRes.json();
            setAllSkills(skillsData.filter((s: Skill) => s.is_active));

            // Load Project Nodes
            const nodesRes = await apiFetch(`/api/agents/project/${projectId}/nodes`);
            const nodesData = await nodesRes.json();
            setNodes(nodesData);

            // Default to main PROJECT node
            const mainNode = nodesData.find((n: Node) => n.node_type === "PROJECT");
            if (mainNode) {
                setSelectedNodeId(mainNode.id);
                loadNodeSkills(mainNode.id);
            } else if (nodesData.length > 0) {
                setSelectedNodeId(nodesData[0].id);
                loadNodeSkills(nodesData[0].id);
            }

        } catch (error) {
            console.error("Failed to load settings data:", error);
            setSaveStatus("❌ Failed to load settings");
        } finally {
            setLoading(false);
        }
    };

    const loadNodeSkills = async (nodeId: string) => {
        try {
            const nodeSkillsRes = await apiFetch(`/api/skills/node/${nodeId}`);
            const nodeSkillsData = await nodeSkillsRes.json();
            setAssignedSkillIds(nodeSkillsData.map((s: Skill) => s.id));
        } catch (error) {
            console.error("Failed to load node skills:", error);
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

    const toggleSkill = async (skillId: string) => {
        if (!selectedNodeId) return;

        const newIds = assignedSkillIds.includes(skillId)
            ? assignedSkillIds.filter(id => id !== skillId)
            : [...assignedSkillIds, skillId];

        setSaving(true);
        try {
            const res = await apiFetch(`/api/skills/node/${selectedNodeId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(newIds),
            });
            if (res.ok) {
                setAssignedSkillIds(newIds);
                setSaveStatus("✅ Skills updated");
                setTimeout(() => setSaveStatus(""), 2000);
            }
        } catch (err) {
            console.error("Failed to update skills:", err);
            setSaveStatus("❌ Update failed");
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
                        {activeTab === "instructions" && (
                            isEditing ? (
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
                            )
                        )}
                    </div>
                </div>

                {/* Tabs */}
                <div className="flex gap-8 mt-6">
                    <button
                        onClick={() => setActiveTab("instructions")}
                        className={`pb-2 px-1 text-sm font-bold uppercase tracking-widest transition-all ${activeTab === 'instructions' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
                    >
                        Instructions
                    </button>
                    <button
                        onClick={() => setActiveTab("skills")}
                        className={`pb-2 px-1 text-sm font-bold uppercase tracking-widest transition-all ${activeTab === 'skills' ? 'text-cyan-400 border-b-2 border-cyan-400' : 'text-gray-500 hover:text-gray-300'}`}
                    >
                        Skills ({assignedSkillIds.length})
                    </button>
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
                    <div className="max-w-4xl mx-auto">
                        {activeTab === "instructions" ? (
                            <div className="space-y-8">
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
                                        <div className="space-y-4">
                                            <textarea
                                                value={prompt}
                                                onChange={(e) => setPrompt(e.target.value)}
                                                className="w-full min-h-[400px] bg-gray-900/50 border border-gray-700 rounded-xl p-6 text-gray-200 font-mono text-sm focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-all resize-y"
                                                placeholder="Enter instructions for this agent..."
                                            />
                                        </div>
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
                        ) : (
                            <div className="flex gap-8">
                                {/* Left Side: Node List */}
                                <div className="w-64 shrink-0 space-y-2">
                                    <h2 className="text-[10px] font-bold text-gray-600 uppercase tracking-widest mb-4 px-2">
                                        Agent Nodes
                                    </h2>
                                    {nodes.map(node => (
                                        <button
                                            key={node.id}
                                            onClick={() => {
                                                setSelectedNodeId(node.id);
                                                loadNodeSkills(node.id);
                                            }}
                                            className={`w-full text-left p-3 rounded-xl border transition-all ${selectedNodeId === node.id
                                                ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400 font-bold shadow-[0_0_15px_rgba(34,211,238,0.05)]'
                                                : 'bg-gray-900/30 border-gray-800 text-gray-500 hover:border-gray-700 hover:text-gray-300'
                                                }`}
                                        >
                                            <div className="flex flex-col">
                                                <span className="text-sm truncate">{node.display_name}</span>
                                                <span className="text-[10px] opacity-60 uppercase">{node.role_name}</span>
                                            </div>
                                        </button>
                                    ))}
                                </div>

                                {/* Right Side: Skills Grid */}
                                <div className="flex-1 space-y-6">
                                    <div className="flex items-center justify-between border-b border-gray-800 pb-2">
                                        <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                                            <span className="text-cyan-500">◈</span> Assigned Skills
                                        </h2>
                                        <span className="text-xs text-gray-500">
                                            {selectedNodeId ? `Configuring ${nodes.find(n => n.id === selectedNodeId)?.display_name}` : 'Select a node'}
                                        </span>
                                    </div>

                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {allSkills.length > 0 ? (
                                            allSkills.map(skill => (
                                                <div
                                                    key={skill.id}
                                                    onClick={() => !saving && selectedNodeId && toggleSkill(skill.id)}
                                                    className={`p-5 rounded-2xl border transition-all cursor-pointer group relative overflow-hidden ${assignedSkillIds.includes(skill.id)
                                                        ? 'bg-cyan-500/5 border-cyan-500/40'
                                                        : 'bg-gray-900/40 border-gray-800 hover:border-gray-700'}`}
                                                >
                                                    <div className="flex justify-between items-start mb-2">
                                                        <h3 className={`font-bold transition-colors ${assignedSkillIds.includes(skill.id) ? 'text-cyan-400' : 'text-gray-300 group-hover:text-white'}`}>
                                                            {skill.name}
                                                        </h3>
                                                        <div className={`w-5 h-5 rounded-full border flex items-center justify-center transition-all ${assignedSkillIds.includes(skill.id) ? 'bg-cyan-500 border-cyan-500' : 'border-gray-700'}`}>
                                                            {assignedSkillIds.includes(skill.id) && <span className="text-[10px] text-black font-bold">✓</span>}
                                                        </div>
                                                    </div>
                                                    <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                                                        {skill.description}
                                                    </p>

                                                    {/* Active indicator bar */}
                                                    {assignedSkillIds.includes(skill.id) && (
                                                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-cyan-500"></div>
                                                    )}
                                                </div>
                                            ))
                                        ) : (
                                            <div className="col-span-2 py-12 text-center bg-gray-900/20 rounded-2xl border border-dashed border-gray-800">
                                                <p className="text-gray-500 italic">No skills available. Skills must be active to appear here.</p>
                                            </div>
                                        )}
                                    </div>

                                    <div className="mt-8 p-4 bg-cyan-900/10 border border-cyan-800/20 rounded-xl flex items-start gap-4">
                                        <div className="w-10 h-10 rounded-full bg-cyan-500/20 flex items-center justify-center shrink-0">
                                            <span className="text-cyan-400">⚡</span>
                                        </div>
                                        <div className="text-xs text-gray-400 leading-relaxed">
                                            <p className="font-bold text-cyan-400 mb-1">How skills work:</p>
                                            <p>Attached skills inject specialized instructions and tool guidelines directly into the agent&apos;s system prompt. This allows the agent to behave as a specialist without cluttering the main system instructions.</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
