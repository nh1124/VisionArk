"use client";

import { useState, useRef, DragEvent } from "react";

interface ChatInputProps {
    value: string;
    onChange: (value: string) => void;
    onSend: (message: string, files: File[]) => void;
    placeholder: string;
    disabled?: boolean;
    allowFileAttach?: boolean;
    // Model selection props
    selectedModel?: string;
    onModelChange?: (model: string) => void;
    showModelSelector?: boolean;
    onClone?: () => void;
}

const MODEL_OPTIONS = [
    { group: "Gemini 3 (Preview)", models: ["gemini-3-pro-preview", "gemini-3-flash-preview"] },
    { group: "Gemini 2.5", models: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-preview", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite-preview"] },
    { group: "Gemini 2.0", models: ["gemini-2.0-flash", "gemini-2.0-flash-lite"] },
];

const getModelDisplayName = (model: string) => {
    const parts = model.split("-");
    if (parts.length >= 3) {
        return parts.slice(1).join(" ").replace(/\b\w/g, c => c.toUpperCase());
    }
    return model;
};

export default function ChatInput({
    value,
    onChange,
    onSend,
    placeholder,
    disabled = false,
    allowFileAttach = true,
    selectedModel = "gemini-2.5-flash-lite",
    onModelChange,
    showModelSelector = false,
    onClone
}: ChatInputProps) {
    const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const [showModelMenu, setShowModelMenu] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const modelMenuRef = useRef<HTMLDivElement>(null);
    const toolsMenuRef = useRef<HTMLDivElement>(null);
    const [showToolsMenu, setShowToolsMenu] = useState(false);

    // Auto-resize logic
    const adjustTextareaHeight = () => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            const newHeight = Math.min(textarea.scrollHeight, isExpanded ? 600 : 200);
            textarea.style.height = `${newHeight}px`;
        }
    };

    const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        onChange(e.target.value);
        setTimeout(adjustTextareaHeight, 0);
    };

    const handleFileSelect = (files: FileList | null) => {
        if (!files) return;
        const newFiles = Array.from(files);
        setAttachedFiles((prev) => [...prev, ...newFiles]);
    };

    const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(false);
    };

    const handleDrop = (e: DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(false);
        handleFileSelect(e.dataTransfer.files);
    };

    const removeFile = (index: number) => {
        setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
    };

    const handleSend = () => {
        if (!value.trim() && attachedFiles.length === 0) return;
        onSend(value, attachedFiles);
        setAttachedFiles([]);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const formatFileSize = (bytes: number): string => {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    };

    const handleModelSelect = (model: string) => {
        onModelChange?.(model);
        setShowModelMenu(false);
    };

    return (
        <div className="sticky bottom-0 bg-gray-950 border-t border-gray-800 p-4">
            {/* File Attachments Preview */}
            {attachedFiles.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-2">
                    {attachedFiles.map((file, index) => (
                        <div
                            key={index}
                            className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2 border border-gray-700"
                        >
                            <div className="flex items-center gap-2 flex-1">
                                <div className="w-8 h-8 rounded bg-purple-500/20 flex items-center justify-center text-purple-400">
                                    {file.type.startsWith("image/") ? "🖼️" :
                                        file.type === "application/pdf" ? "📄" :
                                            file.type.startsWith("video/") ? "🎥" :
                                                file.type.startsWith("audio/") ? "🎵" : "📎"}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium text-gray-200 truncate">
                                        {file.name}
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        {formatFileSize(file.size)}
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => removeFile(index)}
                                className="text-gray-400 hover:text-red-400 transition-colors p-1"
                                title="Remove file"
                            >
                                ✕
                            </button>
                        </div>
                    ))}
                </div>
            )}

            {/* Gemini-style Input Container */}
            <div
                className={`relative rounded-3xl border transition-all duration-500 ease-in-out flex flex-col shadow-2xl ${isDragging
                    ? "border-purple-500 bg-purple-500/10"
                    : "border-gray-700 bg-gray-900/80 backdrop-blur-sm"
                    } ${isExpanded ? "flex-1 min-h-[400px]" : "h-auto"}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <div className="relative flex-1 flex flex-col min-h-0 overflow-hidden">
                    <textarea
                        ref={textareaRef}
                        value={value}
                        onChange={handleTextChange}
                        onKeyDown={handleKeyDown}
                        placeholder={isDragging ? "Drop files here..." : placeholder}
                        className={`w-full bg-transparent border-none focus:outline-none resize-none py-4 px-6 text-gray-100 placeholder-gray-600 transition-all duration-500 ease-in-out ${isExpanded ? "flex-1 text-lg mb-4" : ""}`}
                        disabled={disabled}
                        style={{
                            minHeight: isExpanded ? "300px" : "48px",
                            maxHeight: isExpanded ? "none" : "200px",
                            overflowY: "auto"
                        }}
                    />

                    {/* Expansion Toggle Button */}
                    <button
                        onClick={() => {
                            setIsExpanded(!isExpanded);
                            setTimeout(adjustTextareaHeight, 0);
                        }}
                        className="absolute top-2 right-4 p-2 text-gray-500 hover:text-white hover:bg-gray-800 rounded-xl transition-all group scale-90 hover:scale-100"
                        title={isExpanded ? "Normal View" : "Focus Mode"}
                    >
                        {isExpanded ? (
                            <svg className="w-5 h-5 transition-transform group-hover:scale-95" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
                            </svg>
                        ) : (
                            <svg className="w-5 h-5 transition-transform group-hover:scale-110" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
                            </svg>
                        )}
                    </button>
                </div>

                {/* Bottom Row: Controls */}
                <div className="flex items-center justify-between gap-1 px-4 py-2 border-t border-gray-800/50">
                    {/* Left Side Buttons */}
                    <div className="flex items-center gap-1">
                        {/* File Attach Button (+) */}
                        {allowFileAttach && (
                            <button
                                onClick={() => fileInputRef.current?.click()}
                                className="p-2.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-full transition-all"
                                title="Attach files"
                                disabled={disabled}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                </svg>
                            </button>
                        )}

                        {/* Tools Button */}
                        <div className="relative" ref={toolsMenuRef}>
                            <button
                                onClick={() => setShowToolsMenu(!showToolsMenu)}
                                className="p-2.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-full transition-all flex items-center gap-2 px-3 sm:px-4 group"
                                title="Tools"
                                disabled={disabled}
                            >
                                <svg className="w-5 h-5 text-gray-500 group-hover:text-purple-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                <span className="text-sm font-medium hidden sm:inline whitespace-nowrap">ツール</span>
                            </button>

                            {/* Tools Dropdown */}
                            {showToolsMenu && (
                                <div className="absolute bottom-full left-0 mb-4 bg-gray-900 border border-gray-700/50 rounded-2xl shadow-2xl py-2 min-w-[200px] z-50 overflow-hidden backdrop-blur-xl">
                                    <button
                                        onClick={() => {
                                            onClone?.();
                                            setShowToolsMenu(false);
                                        }}
                                        className="w-full text-left px-4 py-2.5 text-sm text-gray-300 hover:bg-white/5 transition-all flex items-center gap-3"
                                    >
                                        <span className="text-purple-400">📋</span> Clone Spoke (Branch)
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Hidden File Input */}
                    <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        className="hidden"
                        onChange={(e) => handleFileSelect(e.target.files)}
                        accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt,.md"
                    />

                    {/* Right Side Buttons */}
                    <div className="flex items-center gap-1">
                        {/* Model Selector */}
                        {showModelSelector && (
                            <div className="relative" ref={modelMenuRef}>
                                <button
                                    onClick={() => setShowModelMenu(!showModelMenu)}
                                    className="px-3 sm:px-4 py-2 text-gray-300 hover:text-white hover:bg-gray-800 rounded-full transition-all text-xs sm:text-sm flex items-center gap-2 border border-gray-700/50 whitespace-nowrap"
                                    title="Select model"
                                >
                                    <span className="font-medium text-[10px] uppercase tracking-wider text-gray-500 hidden xs:inline">Model:</span>
                                    <span>{selectedModel.includes("pro") ? "Pro" : selectedModel.includes("flash-lite") ? "Lite" : "Flash"}</span>
                                    <svg className="w-4 h-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                    </svg>
                                </button>

                                {/* Model Dropdown */}
                                {showModelMenu && (
                                    <div className="absolute bottom-full right-0 mb-4 bg-gray-900 border border-gray-700/50 rounded-2xl shadow-2xl py-3 min-w-[240px] z-50 overflow-hidden backdrop-blur-xl">
                                        {MODEL_OPTIONS.map((group) => (
                                            <div key={group.group}>
                                                <div className="px-4 py-2 text-[10px] text-gray-500 font-bold uppercase tracking-widest">{group.group}</div>
                                                {group.models.map((model) => (
                                                    <button
                                                        key={model}
                                                        onClick={() => handleModelSelect(model)}
                                                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-white/5 transition-all flex items-center justify-between ${selectedModel === model ? "text-purple-400 bg-purple-500/5" : "text-gray-300"
                                                            }`}
                                                    >
                                                        <span>{getModelDisplayName(model)}</span>
                                                        {selectedModel === model && <div className="w-1.5 h-1.5 rounded-full bg-purple-400 shadow-[0_0_8px_rgba(168,85,247,0.5)]"></div>}
                                                    </button>
                                                ))}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Voice Button */}
                        <button
                            className="p-2.5 text-gray-500 hover:text-gray-300 hover:bg-gray-800 rounded-full transition-all"
                            title="Voice input"
                            disabled
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                            </svg>
                        </button>

                        {/* Send Button */}
                        <button
                            onClick={handleSend}
                            disabled={disabled || (!value.trim() && attachedFiles.length === 0)}
                            className="p-2.5 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-800 disabled:text-gray-600 rounded-full shadow-lg transition-all ml-1"
                            title="Send message"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>

            {/* Drag Overlay */}
            {isDragging && (
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center bg-purple-500/10 rounded-3xl">
                    <div className="text-purple-400 text-lg font-semibold">
                        Drop files to attach
                    </div>
                </div>
            )}
        </div>
    );
}
