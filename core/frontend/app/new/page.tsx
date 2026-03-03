"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { Send, Loader2, Paperclip, X, FileText } from "lucide-react";
import { useModel, getModelDisplayName } from "@/lib/ModelContext";

export default function NewProjectPage() {
    const [prompt, setPrompt] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [files, setFiles] = useState<File[]>([]);
    const [showModelMenu, setShowModelMenu] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const modelMenuRef = useRef<HTMLDivElement>(null);
    const router = useRouter();
    const { selectedModel, setSelectedModel, modelGroups } = useModel();

    const suggestionChips = [
        "Research project planning",
        "Python automation",
        "Data analysis",
        "Feature design",
        "Documentation",
        "Code review",
    ];

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) {
            setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
        }
    };

    const removeFile = (index: number) => {
        setFiles((prev) => prev.filter((_, i) => i !== index));
    };

    const handleSubmit = async (inputPrompt?: string) => {
        const finalPrompt = inputPrompt || prompt;
        if (!finalPrompt.trim()) return;

        setLoading(true);
        setError("");

        try {
            const formData = new FormData();
            formData.append("prompt", finalPrompt);
            files.forEach((file) => {
                formData.append("files", file);
            });

            const response = await apiFetch("/api/agents/project/create-from-prompt", {
                method: "POST",
                headers: {
                    // Content-Type is set automatically by browser with boundary for FormData
                    "X-Preferred-Model": selectedModel
                },
                body: formData,
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

    const [isDragging, setIsDragging] = useState(false);

    // Close dropdowns when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (modelMenuRef.current && !modelMenuRef.current.contains(event.target as Node)) {
                setShowModelMenu(false);
            }
        };

        document.addEventListener("mousedown", handleClickOutside);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
        };
    }, []);

    const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files) {
            setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
        }
    };

    const handleModelSelect = (model: string) => {
        setSelectedModel(model);
        setShowModelMenu(false);
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-full px-4 text-white">
            <div className="w-full max-w-2xl space-y-6">
                {/* Greeting - Smaller Title */}
                <h1 className="text-2xl md:text-3xl font-bold text-center bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
                    New Project
                </h1>

                {/* File List */}
                {files.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                        {files.map((file, index) => (
                            <div key={index} className="flex items-center gap-2 bg-gray-800/60 border border-gray-700/60 rounded-lg px-3 py-2 animate-in fade-in zoom-in-95 duration-200">
                                <div className="w-8 h-8 rounded bg-cyan-500/20 flex items-center justify-center text-cyan-400">
                                    {file.type.startsWith("image/") ? "🖼️" :
                                        file.type === "application/pdf" ? "📄" : "📎"}
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-xs font-medium text-gray-200 max-w-[150px] truncate" title={file.name}>{file.name}</span>
                                    <span className="text-[10px] text-gray-500">{(file.size / 1024).toFixed(1)} KB</span>
                                </div>
                                <button
                                    onClick={() => removeFile(index)}
                                    className="p-1 hover:bg-red-500/20 hover:text-red-400 rounded transition-colors text-gray-500 ml-1"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            </div>
                        ))}
                    </div>
                )}

                {/* Input Area - Chat Style */}
                <div
                    className={`relative group border rounded-3xl transition-all shadow-xl
                        ${isDragging
                            ? "border-cyan-500 bg-cyan-500/10"
                            : "bg-gray-900/80 border-gray-700 focus-within:border-gray-600"
                        }`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                >
                    <textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={isDragging ? "Drop files here..." : "What would you like to work on?"}
                        disabled={loading}
                        rows={3}
                        className="w-full bg-transparent text-gray-100 placeholder-gray-500 resize-none focus:outline-none text-lg p-6 pb-2"
                    />

                    {/* Bottom Controls Row */}
                    <div className="flex items-center justify-between px-4 py-2">
                        {/* Left Side: Attachments */}
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => fileInputRef.current?.click()}
                                className="p-3 text-gray-400 hover:text-white hover:bg-gray-800 rounded-full transition-all min-w-[44px] min-h-[44px] flex items-center justify-center"
                                title="Attach Files"
                            >
                                <Paperclip className="w-5 h-5" />
                            </button>
                            <input
                                type="file"
                                ref={fileInputRef}
                                onChange={handleFileSelect}
                                multiple
                                className="hidden"
                            />
                        </div>

                        {/* Right Side: Model & Send */}
                        <div className="flex items-center gap-1">
                            {/* Model Selector */}
                            <div className="relative" ref={modelMenuRef}>
                                <button
                                    onClick={() => setShowModelMenu(!showModelMenu)}
                                    className="px-3 sm:px-4 py-2 text-gray-300 hover:text-white hover:bg-gray-800 rounded-full transition-all text-xs sm:text-sm flex items-center gap-1.5 sm:gap-2 border border-gray-700/50 whitespace-nowrap min-h-[44px] flex-shrink-0"
                                    title="Select model"
                                >
                                    <span className="font-medium text-[10px] uppercase tracking-wider text-gray-500 hidden xs:inline">Model:</span>
                                    <span className="max-w-[100px] sm:max-w-none truncate font-semibold">{selectedModel.includes("pro") ? "Gemini Pro" : selectedModel.includes("flash-lite") ? "Flash Lite" : "Gemini Flash"}</span>
                                    <svg className="w-4 h-4 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                </button>

                                {/* Model Dropdown */}
                                {showModelMenu && (
                                    <div className="absolute bottom-full right-0 mb-4 bg-gray-900 border border-gray-700/50 rounded-2xl shadow-2xl py-3 min-w-[240px] z-50 overflow-hidden backdrop-blur-xl">
                                        {modelGroups.map((group) => (
                                            <div key={group.group}>
                                                <div className="px-4 py-2 text-[10px] text-gray-500 font-bold uppercase tracking-widest">{group.group}</div>
                                                {group.models.map((model) => (
                                                    <button
                                                        key={model.id}
                                                        onClick={() => handleModelSelect(model.id)}
                                                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-white/5 transition-all flex items-center justify-between ${selectedModel === model.id ? "text-purple-400 bg-purple-500/5" : "text-gray-300"
                                                            }`}
                                                    >
                                                        <span>{getModelDisplayName(model.id, modelGroups)}</span>
                                                        {selectedModel === model.id && <div className="w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.5)]"></div>}
                                                    </button>
                                                ))}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            <button
                                onClick={() => handleSubmit()}
                                disabled={loading || !prompt.trim()}
                                className="p-3 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-800 disabled:text-gray-600 rounded-full shadow-lg transition-all ml-1 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
                                title="Start Project"
                            >
                                {loading ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <Send className="w-5 h-5 ml-0.5" />
                                )}
                            </button>
                        </div>
                    </div>
                </div>

                {error && (
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
                        {error}
                    </div>
                )}

                {/* Suggestion Chips */}
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
