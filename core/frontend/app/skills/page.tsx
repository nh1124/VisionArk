"use client";

import React, { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { Sparkles, Search, BookOpen, Clock, CheckCircle, XCircle, ChevronRight, Edit3, Trash2 } from "lucide-react";
import SkillEditor from "./components/SkillEditor";

interface Skill {
    id: string;
    name: string;
    description: string;
    is_active: boolean;
    is_draft: boolean;
    created_at: string;
    content: string;
}

export default function SkillsPage() {
    const [skills, setSkills] = useState<Skill[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
    const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(new Set());

    useEffect(() => {
        fetchSkills();
    }, []);

    const fetchSkills = async () => {
        try {
            const response = await apiFetch("/api/skills");
            if (response.ok) {
                const data = await response.json();
                setSkills(data.map((s: any) => ({
                    ...s,
                    content: s.content || ""
                })));
            }
        } catch (error) {
            console.error("Failed to fetch skills:", error);
        } finally {
            setLoading(false);
        }
    };

    const toggleSkill = async (skill: Skill) => {
        try {
            const response = await apiFetch(`/api/skills/${skill.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: skill.name,
                    description: skill.description,
                    content: (skill as any).content || "", // Skill object might not have content in list view, but API handles it
                    is_active: !skill.is_active
                })
            });
            if (response.ok) {
                setSkills(skills.map(s => s.id === skill.id ? { ...s, is_active: !s.is_active } : s));
            }
        } catch (error) {
            console.error("Failed to toggle skill:", error);
        }
    };

    const handleSaveSkill = async (updatedSkill: Skill) => {
        try {
            const response = await apiFetch(`/api/skills/${updatedSkill.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: updatedSkill.name,
                    description: updatedSkill.description,
                    content: (updatedSkill as any).content,
                    is_active: updatedSkill.is_active
                })
            });
            if (response.ok) {
                setSkills(skills.map(s => s.id === updatedSkill.id ? updatedSkill : s));
                setSelectedSkill(null);
            }
        } catch (error) {
            console.error("Failed to save skill:", error);
        }
    };

    const handleEditClick = async (skill: Skill) => {
        try {
            const response = await apiFetch(`/api/skills/${skill.id}`);
            if (response.ok) {
                const fullSkill = await response.json();
                setSelectedSkill(fullSkill);
            }
        } catch (error) {
            console.error("Failed to fetch full skill details:", error);
        }
    };

    const handleApproveSkill = async (skill: Skill) => {
        try {
            const response = await apiFetch(`/api/skills/${skill.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: skill.name,
                    description: skill.description,
                    content: skill.content,
                    is_active: true,
                    is_draft: false
                })
            });
            if (response.ok) {
                setSkills(skills.map(s => s.id === skill.id ? { ...s, is_draft: false, is_active: true } : s));
            }
        } catch (error) {
            console.error("Failed to approve skill:", error);
        }
    };

    const handleRejectSkill = async (skill: Skill) => {
        if (!confirm("Are you sure you want to discard this skill candidate?")) return;
        try {
            const response = await apiFetch(`/api/skills/${skill.id}`, {
                method: "DELETE"
            });
            if (response.ok) {
                setSkills(skills.filter(s => s.id !== skill.id));
                const newSelected = new Set(selectedSkillIds);
                newSelected.delete(skill.id);
                setSelectedSkillIds(newSelected);
            }
        } catch (error) {
            console.error("Failed to reject skill:", error);
        }
    };

    const handleBatchApprove = async () => {
        if (selectedSkillIds.size === 0) return;
        try {
            const response = await apiFetch("/api/skills/batch/approve", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ skill_ids: Array.from(selectedSkillIds) })
            });
            if (response.ok) {
                setSkills(skills.map(s => selectedSkillIds.has(s.id) ? { ...s, is_draft: false, is_active: true } : s));
                setSelectedSkillIds(new Set());
            }
        } catch (error) {
            console.error("Failed to batch approve skills:", error);
        }
    };

    const handleBatchDiscard = async () => {
        if (selectedSkillIds.size === 0) return;
        if (!confirm(`Are you sure you want to discard ${selectedSkillIds.size} selected skill candidates?`)) return;
        try {
            const response = await apiFetch("/api/skills/batch/discard", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ skill_ids: Array.from(selectedSkillIds) })
            });
            if (response.ok) {
                setSkills(skills.filter(s => !selectedSkillIds.has(s.id)));
                setSelectedSkillIds(new Set());
            }
        } catch (error) {
            console.error("Failed to batch discard skills:", error);
        }
    };

    const handleDeleteSkill = async (skill: Skill) => {
        if (!confirm(`Are you sure you want to delete the skill "${skill.name}"? This action cannot be undone.`)) return;
        try {
            const response = await apiFetch(`/api/skills/${skill.id}`, {
                method: "DELETE"
            });
            if (response.ok) {
                setSkills(skills.filter(s => s.id !== skill.id));
            } else {
                const errorData = await response.json();
                alert(`Failed to delete skill: ${errorData.detail || "Unknown error"}`);
            }
        } catch (error) {
            console.error("Failed to delete skill:", error);
            alert("Failed to delete skill due to a network or server error.");
        }
    };

    const toggleSelection = (skillId: string) => {
        const newSelected = new Set(selectedSkillIds);
        if (newSelected.has(skillId)) {
            newSelected.delete(skillId);
        } else {
            newSelected.add(skillId);
        }
        setSelectedSkillIds(newSelected);
    };

    const selectAllDrafts = () => {
        const draftIds = filteredSkills.filter(s => s.is_draft).map(s => s.id);
        setSelectedSkillIds(new Set(draftIds));
    };

    const clearSelection = () => {
        setSelectedSkillIds(new Set());
    };

    const filteredSkills = skills.filter(s =>
        s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.description?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    return (
        <div className="flex-1 overflow-y-auto bg-gray-950 p-8">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-10">
                    <div>
                        <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
                            <Sparkles className="text-cyan-400 w-8 h-8" />
                            Agent Skills
                        </h1>
                        <p className="text-gray-400 mt-2">Manage and train specialized domain knowledge for your agents.</p>
                    </div>

                    <div className="flex items-center gap-4">
                        {selectedSkillIds.size > 0 && (
                            <div className="flex items-center gap-2 bg-gray-900 border border-gray-800 rounded-xl px-4 py-2 animate-in fade-in slide-in-from-right-4">
                                <span className="text-sm font-medium text-gray-400">
                                    {selectedSkillIds.size} selected
                                </span>
                                <div className="w-px h-4 bg-gray-800 mx-2" />
                                <button
                                    onClick={handleBatchApprove}
                                    className="text-xs font-bold uppercase tracking-wider text-cyan-400 hover:text-cyan-300 transition-colors"
                                >
                                    Approve
                                </button>
                                <button
                                    onClick={handleBatchDiscard}
                                    className="text-xs font-bold uppercase tracking-wider text-red-400 hover:text-red-300 transition-colors"
                                >
                                    Discard
                                </button>
                                <button
                                    onClick={clearSelection}
                                    className="p-1 text-gray-500 hover:text-white transition-colors"
                                >
                                    <XCircle className="w-4 h-4" />
                                </button>
                            </div>
                        )}

                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 w-4 h-4" />
                            <input
                                type="text"
                                placeholder="Search skills..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="bg-gray-900 border border-gray-800 rounded-xl py-2 pl-10 pr-4 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-500/50 w-full md:w-64 transition-all"
                            />
                        </div>

                        {filteredSkills.some(s => s.is_draft) && (
                            <button
                                onClick={selectAllDrafts}
                                className="bg-amber-500/10 text-amber-500 border border-amber-500/20 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-wider hover:bg-amber-500/20 transition-all"
                            >
                                Select Drafts
                            </button>
                        )}
                    </div>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-cyan-500"></div>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filteredSkills.map((skill) => (
                            <div
                                key={skill.id}
                                className={`group relative bg-gray-900 border rounded-2xl p-6 transition-all duration-300 hover:scale-[1.02] hover:shadow-2xl hover:shadow-cyan-500/10 ${skill.is_active ? "border-cyan-500/30" : "border-gray-800"
                                    } ${selectedSkillIds.has(skill.id) ? "ring-2 ring-cyan-500 border-cyan-500" : ""}`}
                                onClick={() => skill.is_draft && toggleSelection(skill.id)}
                            >
                                {skill.is_draft && (
                                    <div className="absolute top-4 right-4 z-10">
                                        <div className={`w-5 h-5 rounded border flex items-center justify-center transition-all ${selectedSkillIds.has(skill.id) ? "bg-cyan-500 border-cyan-500" : "bg-gray-800 border-gray-700 opacity-0 group-hover:opacity-100"}`}>
                                            {selectedSkillIds.has(skill.id) && <CheckCircle className="w-3 h-3 text-white" />}
                                        </div>
                                    </div>
                                )}
                                <div className="flex items-start justify-between mb-4">
                                    <div className={`p-3 rounded-xl ${skill.is_active ? "bg-cyan-500/10 text-cyan-400" : "bg-gray-800 text-gray-500"}`}>
                                        <BookOpen w-6 h-6 />
                                    </div>
                                    <button
                                        onClick={() => toggleSkill(skill)}
                                        className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider transition-all ${skill.is_active
                                            ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                                            : "bg-gray-800 text-gray-500 border border-gray-700"
                                            }`}
                                    >
                                        {skill.is_active ? "Active" : "Inactive"}
                                    </button>
                                </div>

                                <h3 className="text-lg font-bold text-white mb-2 group-hover:text-cyan-300 transition-colors">
                                    {skill.name}
                                </h3>
                                <p className="text-sm text-gray-400 line-clamp-2 h-10 mb-6">
                                    {skill.description || "No description provided."}
                                </p>

                                <div className="flex items-center justify-between pt-4 border-t border-gray-800/50">
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                        <Clock w-3 h-3 />
                                        {new Date(skill.created_at).toLocaleDateString()}
                                    </div>

                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={() => handleEditClick(skill)}
                                            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                                        >
                                            <Edit3 w-4 h-4 />
                                        </button>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDeleteSkill(skill);
                                            }}
                                            className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-400/10 rounded-lg transition-colors"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>

                                {skill.is_draft && (
                                    <>
                                        <div className="absolute -top-2 -right-2 bg-amber-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-lg shadow-lg">
                                            DRAFT
                                        </div>
                                        <div className="flex gap-2 mt-4">
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleApproveSkill(skill);
                                                }}
                                                className="flex-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 py-2 rounded-xl text-[10px] font-bold uppercase tracking-wider hover:bg-cyan-500/20 transition-all flex items-center justify-center gap-2"
                                            >
                                                <CheckCircle className="w-3 h-3" /> Approve
                                            </button>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleRejectSkill(skill);
                                                }}
                                                className="flex-1 bg-gray-800 text-gray-500 border border-gray-700 py-2 rounded-xl text-[10px] font-bold uppercase tracking-wider hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/20 transition-all flex items-center justify-center gap-2"
                                            >
                                                <XCircle className="w-3 h-3" /> Discard
                                            </button>
                                        </div>
                                    </>
                                )}
                            </div>
                        ))}

                        {/* Empty State */}
                        {filteredSkills.length === 0 && (
                            <div className="col-span-full py-20 flex flex-col items-center text-gray-500">
                                <div className="bg-gray-900/50 p-6 rounded-3xl mb-4 border border-gray-800">
                                    <Sparkles className="text-gray-700 w-12 h-12" />
                                </div>
                                <p className="text-lg font-medium">No skills found</p>
                                <p className="text-sm mt-1">Try searching for something else or wait for AI to draft new ones.</p>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Editor Overlay */}
            {selectedSkill && (
                <SkillEditor
                    skill={selectedSkill as any}
                    onClose={() => setSelectedSkill(null)}
                    onSave={handleSaveSkill as any}
                />
            )}
        </div>
    );
}
