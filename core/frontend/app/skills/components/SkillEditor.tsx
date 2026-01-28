"use client";

import React, { useState } from "react";
import { X, Save, Trash2, Eye } from "lucide-react";

interface Skill {
    id: string;
    name: string;
    description: string;
    content: string;
    is_active: boolean;
    is_draft?: boolean;
    created_at?: string;
}

interface SkillEditorProps {
    skill: Skill;
    onClose: () => void;
    onSave: (updatedSkill: Skill) => Promise<void>;
}

export default function SkillEditor({ skill, onClose, onSave }: SkillEditorProps) {
    const [editedSkill, setEditedSkill] = useState<Skill>({ ...skill });
    const [isSaving, setIsSaving] = useState(false);

    const handleSave = async () => {
        setIsSaving(true);
        await onSave(editedSkill);
        setIsSaving(false);
    };

    return (
        <div className="fixed inset-y-0 right-0 w-full max-w-2xl bg-gray-900 border-l border-gray-800 shadow-2xl z-50 flex flex-col transform transition-transform duration-300">
            {/* Header */}
            <div className="p-6 border-b border-gray-800 flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-bold text-white">Edit Skill</h2>
                    <p className="text-xs text-gray-500 mt-1">ID: {skill.id}</p>
                </div>
                <button onClick={onClose} className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg">
                    <X w-5 h-5 />
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
                <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Skill Name</label>
                    <input
                        type="text"
                        value={editedSkill.name}
                        onChange={(e) => setEditedSkill({ ...editedSkill, name: e.target.value })}
                        className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-cyan-500/50 outline-none transition-all"
                    />
                </div>

                <div>
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Description</label>
                    <textarea
                        value={editedSkill.description}
                        onChange={(e) => setEditedSkill({ ...editedSkill, description: e.target.value })}
                        rows={3}
                        className="w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-cyan-500/50 outline-none transition-all resize-none"
                    />
                </div>

                <div className="flex-1 flex flex-col min-h-[300px]">
                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2 flex items-center justify-between">
                        <span>Instruction Content (Markdown)</span>
                        <span className="text-[10px] text-cyan-500 font-normal">Supports SKILL.md format</span>
                    </label>
                    <textarea
                        value={editedSkill.content}
                        onChange={(e) => setEditedSkill({ ...editedSkill, content: e.target.value })}
                        className="flex-1 w-full bg-gray-950 border border-gray-800 rounded-xl px-4 py-3 text-white font-mono text-sm focus:ring-2 focus:ring-cyan-500/50 outline-none transition-all resize-none"
                    />
                </div>
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-gray-800 flex items-center justify-between bg-gray-900/50">
                <button className="flex items-center gap-2 text-red-400 hover:text-red-300 text-sm font-medium transition-colors">
                    <Trash2 w-4 h-4 />
                    Delete Skill
                </button>

                <div className="flex items-center gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={isSaving}
                        className={`flex items-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white px-6 py-2 rounded-xl font-bold transition-all shadow-lg shadow-cyan-600/20 disabled:opacity-50`}
                    >
                        {isSaving ? (
                            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                        ) : (
                            <Save w-4 h-4 />
                        )}
                        Save Changes
                    </button>
                </div>
            </div>
        </div>
    );
}
