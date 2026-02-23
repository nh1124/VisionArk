"use client";

import { useState, useRef, DragEvent, useEffect, memo } from "react";
import { createPortal } from "react-dom";
import { useNotification } from "@/lib/NotificationContext";
import { useIsMobile } from "@/hooks/useIsMobile";

interface ChatInputProps {
    value?: string;
    initialValue?: string;
    onChange?: (value: string) => void;
    onCommandModeChange?: (isCommandMode: boolean, value: string) => void;  // Only fires when command mode changes
    onSend: (message: string, files: File[]) => void;
    onKeyDown?: (e: React.KeyboardEvent) => void;
    placeholder: string;
    disabled?: boolean;
    allowFileAttach?: boolean;
    selectedModel?: string;
    onModelChange?: (model: string) => void;
    showModelSelector?: boolean;
    onClone?: () => void;
    onScheduleMessage?: () => void;
    loading?: boolean;
    onStop?: () => void;
    compact?: boolean;
}

import { MODEL_OPTIONS, getModelDisplayName } from "@/lib/ModelContext";

function ChatInputComponent({
    value,
    initialValue = "",
    onChange,
    onCommandModeChange,
    onSend,
    placeholder,
    disabled = false,
    allowFileAttach = true,
    selectedModel = "gemini-3-pro-preview",
    onModelChange,
    showModelSelector = false,
    onClone,
    onScheduleMessage,
    loading = false,
    onStop,
    onKeyDown,
    compact = false
}: ChatInputProps) {
    // Internal state for the input value - prevents parent re-renders on each keystroke
    const [internalValue, setInternalValue] = useState(initialValue);
    const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const [showModelMenu, setShowModelMenu] = useState(false);
    const [isExpanded, setIsExpanded] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const modelMenuRef = useRef<HTMLDivElement>(null);
    const toolsMenuRef = useRef<HTMLDivElement>(null);
    const [showToolsMenu, setShowToolsMenu] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
    const audioChunksRef = useRef<Blob[]>([]);

    const { showToast } = useNotification();
    const isMobile = useIsMobile();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    // Restore focus when expanded
    useEffect(() => {
        if (isExpanded && textareaRef.current) {
            requestAnimationFrame(() => {
                textareaRef.current?.focus();
                adjustTextareaHeight(true);
            });
        }
    }, [isExpanded]);

    // Update internal value when external value prop changes
    useEffect(() => {
        if (value !== undefined) {
            setInternalValue(value);
            // Also trigger resize
            setTimeout(adjustTextareaHeight, 0);
        }
    }, [value]);

    // Auto-resize logic
    const adjustTextareaHeight = (overrideExpanded?: boolean) => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            const effectiveExpanded = overrideExpanded !== undefined ? overrideExpanded : isExpanded;
            const minHeight = isMobile ? 40 : (effectiveExpanded ? 200 : 40);
            const maxHeight = effectiveExpanded ? 800 : (isMobile ? 150 : 300); // 300px is the limit for normal mode
            const newHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);
            textarea.style.height = `${newHeight}px`;
        }
    };

    const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const newValue = e.target.value;
        const prevIsCommand = internalValue.trim().startsWith('/');
        const newIsCommand = newValue.trim().startsWith('/');

        setInternalValue(newValue);
        onChange?.(newValue);

        // Always notify parent if it's a command (for autocomplete filtering) 
        // OR if the command mode just changed (to open/close dropdown)
        if (newIsCommand || prevIsCommand !== newIsCommand) {
            onCommandModeChange?.(newIsCommand, newValue);
        }

        // Only trigger resize if NOT expanded (normal input mode)
        if (!isExpanded) {
            requestAnimationFrame(() => adjustTextareaHeight());
        }
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
        if (!internalValue.trim() && attachedFiles.length === 0) return;
        onSend(internalValue, attachedFiles);
        setInternalValue("");  // Clear internal state after send
        setAttachedFiles([]);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (onKeyDown) {
            onKeyDown(e);
            if (e.defaultPrevented) return;
        }

        if (e.key === "Escape" && isExpanded) {
            e.preventDefault();
            setIsExpanded(false);
            setTimeout(adjustTextareaHeight, 0);
            return;
        }

        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    // Handle paste event for clipboard images
    const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
        const items = e.clipboardData?.items;
        if (!items) return;

        const imageFiles: File[] = [];

        for (let i = 0; i < items.length; i++) {
            const item = items[i];

            // Check if the item is an image
            if (item.type.startsWith('image/')) {
                const file = item.getAsFile();
                if (file) {
                    // Create a new file with a meaningful name
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                    const extension = item.type.split('/')[1] || 'png';
                    const namedFile = new File([file], `pasted-image-${timestamp}.${extension}`, {
                        type: file.type
                    });
                    imageFiles.push(namedFile);
                }
            }
        }

        if (imageFiles.length > 0) {
            setAttachedFiles((prev) => [...prev, ...imageFiles]);
            // Don't prevent default if no images - allow normal text paste
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

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mimeType = MediaRecorder.isTypeSupported("audio/webm")
                ? "audio/webm"
                : MediaRecorder.isTypeSupported("audio/mp4")
                    ? "audio/mp4"
                    : "audio/aac";

            const recorder = new MediaRecorder(stream, { mimeType });
            audioChunksRef.current = [];

            recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunksRef.current.push(event.data);
                }
            };

            recorder.onstop = () => {
                const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
                const extension = mimeType.split("/")[1].split(";")[0];
                const file = new File([audioBlob], `voice-recording-${new Date().getTime()}.${extension}`, {
                    type: mimeType
                });

                // Automatically send the voice message along with any text or other attachments
                onSend(internalValue, [...attachedFiles, file]);
                setInternalValue("");
                setAttachedFiles([]);

                // Stop all tracks in the stream to release the microphone
                stream.getTracks().forEach(track => track.stop());
            };

            recorder.start();
            setMediaRecorder(recorder);
            setIsRecording(true);
        } catch (error) {
            console.error("Error accessing microphone:", error);
            showToast("Could not access microphone. Please check permissions.", "error");
        }
    };

    const stopRecording = () => {
        if (mediaRecorder && mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
            setMediaRecorder(null);
            setIsRecording(false);
        }
    };

    const toggleRecording = () => {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    };

    // --- Render Helpers ---

    const filesPreview = attachedFiles.length > 0 && (
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
    );

    const backdrop = isExpanded && (
        <div
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[990]"
            onClick={() => {
                setIsExpanded(false);
                requestAnimationFrame(() => adjustTextareaHeight(false));
            }}
        />
    );

    const inputContainer = (
        <div
            className={`flex flex-col shadow-2xl transition-[inset,transform,background-color,border-color,border-radius] duration-500 ease-in-out
                ${isExpanded
                    ? "fixed inset-4 md:inset-x-20 md:inset-y-10 z-[1000] bg-gray-900 border border-gray-700 rounded-3xl overflow-hidden"
                    : `relative ${compact ? "rounded-2xl" : "rounded-3xl"} border ${isDragging ? "border-purple-500 bg-purple-500/10" : "border-gray-700 bg-gray-900/80 backdrop-blur-sm"}`
                }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
        >
            {/* Backdrop for proper focus mode isolation if needed, though 'fixed inset-4' covers most. 
                If we wanted true full screen overlay we might use a Portal, but this works for "pop out". 
                Actually, let's make it a modal overlay if expanded. */}

            <div className="relative flex-1 flex flex-col min-h-0 overflow-hidden">
                <textarea
                    ref={textareaRef}
                    value={internalValue}
                    onChange={handleTextChange}
                    onKeyDown={handleKeyDown}
                    onPaste={handlePaste}
                    placeholder={isDragging ? "Drop files here..." : placeholder}
                    className={`w-full bg-transparent border-none focus:outline-none resize-none px-4 text-gray-100 placeholder-gray-600 
                        ${isExpanded ? "flex-1 text-lg p-6" : (compact || isMobile) ? "py-2.5 text-[16px]" : "py-2.5"}`}
                    disabled={disabled}
                    style={{
                        minHeight: (compact || isMobile) ? "40px" : (isExpanded ? "100%" : "40px"),
                        maxHeight: isExpanded ? "none" : (compact || isMobile) ? "150px" : "300px", // Increased max-height for normal mode
                        overflowY: "auto"
                    }}
                />

                {/* Expansion Toggle Button */}
                <button
                    onClick={() => {
                        const willExpand = !isExpanded;
                        setIsExpanded(willExpand);
                        // Adjust height immediately with the target state
                        requestAnimationFrame(() => adjustTextareaHeight(willExpand));
                    }}
                    className={`absolute top-2 right-4 p-2 text-gray-500 hover:text-white hover:bg-gray-800 rounded-xl transition-all group scale-90 hover:scale-100 ${isExpanded ? "bg-gray-800/50" : ""}`}
                    title={isExpanded ? "Exit Focus Mode" : "Enter Focus Mode"}
                >
                    {isExpanded ? (
                        <svg className="w-5 h-5 transition-transform group-hover:scale-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    ) : (
                        <svg className="w-5 h-5 transition-transform group-hover:scale-110" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5" />
                        </svg>
                    )}
                </button>

                {/* Character/Word Count in Expanded Mode */}
                {isExpanded && (
                    <div className="absolute bottom-4 right-6 text-xs text-gray-500 font-mono pointer-events-none">
                        {internalValue.length} chars | {internalValue.split(/\s+/).filter(w => w.length > 0).length} words
                    </div>
                )}
            </div>

            {/* Bottom Row: Controls */}
            <div className={`flex items-center justify-between gap-1 border-t border-gray-800/50 ${compact ? "px-2 py-1" : (isMobile ? "px-2 py-1" : "px-4 py-2")} ${showModelMenu || showToolsMenu ? "" : "overflow-x-auto no-scrollbar"
                }`}>
                {/* Left Side Buttons */}
                <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0">
                    {/* File Attach Button (+) */}
                    {allowFileAttach && !compact && (
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            className="p-3 text-gray-400 hover:text-white hover:bg-gray-800 rounded-full transition-all min-w-[44px] min-h-[44px] flex items-center justify-center"
                            title="Attach files"
                            disabled={disabled}
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                        </button>
                    )}

                    {/* Tools Button */}
                    {!compact && (
                        <div className="relative" ref={toolsMenuRef}>
                            <button
                                onClick={() => setShowToolsMenu(!showToolsMenu)}
                                className="p-3 text-gray-400 hover:text-white hover:bg-gray-800 rounded-full transition-all flex items-center gap-2 px-3 sm:px-4 group min-h-[44px]"
                                title="Tools"
                                disabled={disabled}
                            >
                                <svg className="w-5 h-5 text-gray-500 group-hover:text-purple-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                </svg>
                                <span className="text-sm font-medium hidden xs:inline whitespace-nowrap">Tools</span>
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
                                    <button
                                        onClick={() => {
                                            onScheduleMessage?.();
                                            setShowToolsMenu(false);
                                        }}
                                        className="w-full text-left px-4 py-2.5 text-sm text-gray-300 hover:bg-white/5 transition-all flex items-center gap-3"
                                    >
                                        <span className="text-blue-400">📅</span> Schedule Message
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
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
                    {showModelSelector && !compact && (
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
                        onClick={toggleRecording}
                        className={`p-3 rounded-full transition-all min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0 ${isRecording
                            ? "text-red-500 bg-red-500/10 animate-pulse border border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.4)]"
                            : "text-gray-500 hover:text-gray-300 hover:bg-gray-800"
                            }`}
                        title={isRecording ? "Stop recording" : "Voice input"}
                        disabled={disabled}
                        type="button"
                    >
                        <svg className="w-5 h-5" fill={isRecording ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                    </button>

                    {/* Stop/Send Button */}
                    {loading && onStop ? (
                        <button
                            onClick={onStop}
                            className="p-3 bg-white/10 hover:bg-white/20 rounded-full transition-all ml-1 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0 group"
                            title="Stop Agent"
                        >
                            <div className="w-4 h-4 bg-red-500 rounded-sm group-hover:bg-red-400 transition-colors" />
                        </button>
                    ) : (
                        <button
                            onClick={handleSend}
                            disabled={disabled || (!internalValue.trim() && attachedFiles.length === 0)}
                            className="p-3 bg-purple-600 hover:bg-purple-500 disabled:bg-gray-800 disabled:text-gray-600 rounded-full shadow-lg transition-all ml-1 min-w-[44px] min-h-[44px] flex items-center justify-center flex-shrink-0"
                            title="Send message"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                            </svg>
                        </button>
                    )}
                </div>
            </div>
        </div>
    );

    const dragOverlay = isDragging && (
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center bg-purple-500/10 rounded-3xl">
            <div className="text-purple-400 text-lg font-semibold">
                Drop files to attach
            </div>
        </div>
    );

    if (isExpanded && mounted) {
        return (
            <>
                <div className={`sticky bottom-0 bg-transparent ${compact ? "p-0" : (isMobile ? "p-2" : "p-4")}`}>
                    {filesPreview}
                    {/* Placeholder for layout stability */}
                    <div className="invisible pointer-events-none" style={{ height: (compact || isMobile) ? "40px" : "40px" }} />
                </div>
                {createPortal(
                    <div className="fixed inset-0 z-[9999]" onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
                        {backdrop}
                        {inputContainer}
                        {dragOverlay}
                    </div>,
                    document.body
                )}
            </>
        );
    }

    return (
        <div className={`sticky bottom-0 bg-transparent ${compact ? "p-0" : (isMobile ? "p-2" : "p-4")}`}>
            {filesPreview}
            {backdrop}
            {inputContainer}
            {dragOverlay}
        </div>
    );
}

// Memoize the component to prevent unnecessary re-renders from parent
const ChatInput = memo(ChatInputComponent);
export default ChatInput;
