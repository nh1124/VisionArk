"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import StarterKit from "@tiptap/starter-kit";
import { BubbleMenu as BubbleMenuExtension } from "@tiptap/extension-bubble-menu";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import { Markdown } from "tiptap-markdown";
import { MermaidExtension } from "./TiptapMermaid";
import Editor from "@monaco-editor/react";
import {
    Type,
    Code,
    Bold,
    Italic,
    List,
    CheckSquare,
    RotateCcw,
    Save,
    Maximize2,
    Command as CmdIcon,
    ChevronDown,
    Wand2,
    X
} from "lucide-react";

interface CanvasProps {
    content: string;
    format: "markdown" | "code";
    filePath?: string;
    onUpdate?: (content: string) => void;
    onSave?: (content: string) => void;
    onClose?: () => void;
    onCommandPalette?: (selection?: string) => void;
}

export default function Canvas({
    content,
    format,
    filePath,
    onUpdate,
    onSave,
    onClose,
    onCommandPalette
}: CanvasProps) {
    const [editorMode, setEditorMode] = useState<"markdown" | "code">(format);
    const [localContent, setLocalContent] = useState(content);
    const [lastSaved, setLastSaved] = useState<Date | null>(null);

    // Refs for synchronization to avoid cursor jumps and feedback loops
    const lastNotifiedRef = React.useRef(content);
    const modeRef = React.useRef(editorMode);

    useEffect(() => {
        modeRef.current = editorMode;
    }, [editorMode]);

    // Detect language for Monaco
    const language = React.useMemo(() => {
        if (!filePath) return "markdown";
        const parts = filePath.split('.');
        if (parts.length <= 1) return "plaintext";
        const ext = parts.pop()?.toLowerCase();

        const map: Record<string, string> = {
            'js': 'javascript', 'jsx': 'javascript',
            'ts': 'typescript', 'tsx': 'typescript',
            'py': 'python',
            'html': 'html', 'css': 'css',
            'json': 'json',
            'yaml': 'yaml', 'yml': 'yaml',
            'c': 'cpp', 'cpp': 'cpp', 'h': 'cpp', 'hpp': 'cpp',
            'rs': 'rust',
            'go': 'go',
            'rb': 'ruby',
            'php': 'php',
            'sh': 'shell', 'bash': 'shell',
            'bat': 'bat', 'ps1': 'powershell',
            'sql': 'sql',
            'md': 'markdown'
        };
        return map[ext!] || "plaintext";
    }, [filePath]);

    // Handle updates from editor
    const handleContentUpdate = useCallback((newContent: string) => {
        const normalized = newContent.replace(/\r\n/g, '\n');
        if (normalized === lastNotifiedRef.current) return;

        setLocalContent(normalized);
        lastNotifiedRef.current = normalized;
        onUpdate?.(normalized);
    }, [onUpdate]);

    // TipTap Setup
    const tiptapEditor = useEditor({
        extensions: [
            MermaidExtension,
            StarterKit.configure({
                codeBlock: false,
            }),
            BubbleMenuExtension,
            TaskList,
            TaskItem.configure({
                nested: true,
            }),
            Markdown.configure({
                html: false,
                tightLists: true,
                breaks: true,
            }),
        ],
        immediatelyRender: false,
        content: content,
        onUpdate: ({ editor }) => {
            // ONLY push changes from Tiptap if it is the active editor
            if (modeRef.current !== "markdown") return;

            const markdown = (editor.storage as any).markdown.getMarkdown();
            handleContentUpdate(markdown);
        },
        editorProps: {
            attributes: {
                class: "prose prose-invert max-w-none focus:outline-none min-h-[500px] px-4 py-6",
            },
        },
    });

    // Auto-save debounce effect
    useEffect(() => {
        if (localContent === content) return; // Don't save if content matches initial prop

        const timer = setTimeout(() => {
            onSave?.(localContent);
            setLastSaved(new Date());
        }, 3000); // 3 second debounce

        return () => clearTimeout(timer);
    }, [localContent, onSave, content]);

    // Sync external changes (prop -> state)
    useEffect(() => {
        const normalizedProp = content ? content.replace(/\r\n/g, '\n') : "";
        // Only sync if the change is NOT an echo of what we just sent
        // and is truly different from our local state
        if (normalizedProp !== lastNotifiedRef.current) {
            setLocalContent(normalizedProp);
            lastNotifiedRef.current = normalizedProp;

            // Sync Tiptap ONLY if we are in markdown mode to avoid background corruption of code
            if (tiptapEditor && editorMode === "markdown") {
                tiptapEditor.commands.setContent(normalizedProp);
            }
        }
    }, [content, tiptapEditor, editorMode]);

    const handleCommandPaletteClick = useCallback(() => {
        let selection = "";
        if (editorMode === "markdown" && tiptapEditor) {
            const { from, to } = tiptapEditor.state.selection;
            if (from !== to) {
                selection = tiptapEditor.state.doc.textBetween(from, to, "\n");
            }
        }
        // Monaco selection handled if needed in future
        onCommandPalette?.(selection);
    }, [editorMode, tiptapEditor, onCommandPalette]);

    useEffect(() => {
        setEditorMode(format);
    }, [format]);

    const toggleMode = () => {
        const next = editorMode === "markdown" ? "code" : "markdown";
        setEditorMode(next);
        // When switching, ensure editors are in sync
        if (next === "markdown" && tiptapEditor) {
            tiptapEditor.commands.setContent(localContent);
        }
    };

    return (
        <div className="flex flex-col h-full bg-gray-950 border-l border-gray-800 text-gray-200">
            {/* Toolbar */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 bg-gray-900/50 backdrop-blur-md sticky top-0 z-10">
                <div className="flex items-center gap-1">
                    <div className="flex bg-gray-800/50 p-1 rounded-lg">
                        <button
                            onClick={() => setEditorMode("markdown")}
                            className={`p-1.5 rounded-md transition-all ${editorMode === "markdown" ? "bg-gray-700 text-cyan-400 shadow-sm" : "text-gray-400 hover:text-white"}`}
                            title="Rich Text"
                        >
                            <Type size={16} />
                        </button>
                        <button
                            onClick={() => setEditorMode("code")}
                            className={`p-1.5 rounded-md transition-all ${editorMode === "code" ? "bg-gray-700 text-cyan-400 shadow-sm" : "text-gray-400 hover:text-white"}`}
                            title="Code"
                        >
                            <Code size={16} />
                        </button>
                    </div>

                    <div className="h-4 w-px bg-gray-800 mx-2" />

                    {editorMode === "markdown" && (
                        <div className="flex items-center gap-0.5">
                            <button
                                onClick={() => tiptapEditor?.chain().focus().toggleBold().run()}
                                className={`p-1.5 rounded-md hover:bg-gray-800 transition-colors ${tiptapEditor?.isActive('bold') ? 'text-cyan-400' : 'text-gray-400'}`}
                            >
                                <Bold size={16} />
                            </button>
                            <button
                                onClick={() => tiptapEditor?.chain().focus().toggleItalic().run()}
                                className={`p-1.5 rounded-md hover:bg-gray-800 transition-colors ${tiptapEditor?.isActive('italic') ? 'text-cyan-400' : 'text-gray-400'}`}
                            >
                                <Italic size={16} />
                            </button>
                            <button
                                onClick={() => tiptapEditor?.chain().focus().toggleBulletList().run()}
                                className={`p-1.5 rounded-md hover:bg-gray-800 transition-colors ${tiptapEditor?.isActive('bulletList') ? 'text-cyan-400' : 'text-gray-400'}`}
                            >
                                <List size={16} />
                            </button>
                            <button
                                onClick={() => tiptapEditor?.chain().focus().toggleTaskList().run()}
                                className={`p-1.5 rounded-md hover:bg-gray-800 transition-colors ${tiptapEditor?.isActive('taskList') ? 'text-cyan-400' : 'text-gray-400'}`}
                            >
                                <CheckSquare size={16} />
                            </button>
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {filePath && (
                        <div className="flex items-center gap-2 mr-2 border-r border-gray-800 pr-3">
                            <span className="text-[10px] font-mono text-gray-500 truncate max-w-[120px]" title={filePath}>
                                {filePath}
                            </span>
                            <button
                                onClick={() => onSave?.(localContent)}
                                className="p-1.5 rounded-md hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
                                title="Save (Ctrl+S)"
                            >
                                <Save size={16} />
                            </button>
                        </div>
                    )}

                    <button
                        onClick={handleCommandPaletteClick}
                        className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all text-xs font-medium"
                    >
                        <Wand2 size={14} />
                        <span>AI Edit</span>
                        <span className="hidden sm:flex items-center bg-cyan-500/20 px-1 rounded ml-1 scale-90">
                            <CmdIcon size={10} className="mr-0.5" /> K
                        </span>
                    </button>

                    {onClose && (
                        <button
                            onClick={onClose}
                            className="p-1.5 rounded-md hover:bg-gray-800 text-gray-500 hover:text-white transition-colors border border-transparent hover:border-gray-700 ml-1"
                            title="Close Canvas"
                        >
                            <X size={18} />
                        </button>
                    )}
                </div>
            </div>

            {/* Editor Content Area */}
            <div className="flex-1 overflow-hidden relative group">
                {editorMode === "markdown" ? (
                    <div className="h-full overflow-y-auto custom-scrollbar bg-gray-950/50">
                        {tiptapEditor && (
                            <BubbleMenu editor={tiptapEditor}>
                                <div className="flex bg-gray-900 border border-gray-700 rounded-lg shadow-xl p-1 overflow-hidden transform animate-in fade-in slide-in-from-bottom-2 duration-200">
                                    <button
                                        onClick={handleCommandPaletteClick}
                                        className="flex items-center gap-1.5 px-2 py-1.5 hover:bg-gray-800 text-cyan-400 text-xs font-semibold rounded-md transition-colors"
                                    >
                                        <Wand2 size={14} />
                                        <span>AI Edit</span>
                                        <span className="flex items-center bg-cyan-900/40 px-1 rounded ml-1 scale-90 border border-cyan-500/20">
                                            <CmdIcon size={10} className="mr-0.5" /> K
                                        </span>
                                    </button>
                                </div>
                            </BubbleMenu>
                        )}
                        <EditorContent editor={tiptapEditor} />
                    </div>
                ) : (
                    <Editor
                        height="100%"
                        language={language}
                        theme="vs-dark"
                        value={localContent}
                        onChange={(value) => handleContentUpdate(value || "")}
                        options={{
                            minimap: { enabled: false },
                            fontSize: 14,
                            lineNumbers: "on",
                            roundedSelection: false,
                            scrollBeyondLastLine: false,
                            readOnly: false,
                            cursorStyle: "line",
                            automaticLayout: true,
                            padding: { top: 20 },
                            wordWrap: "on"
                        }}
                    />
                )}
            </div>

            {/* Sticky bottom indicator */}
            <div className="px-4 py-1.5 border-t border-gray-800 bg-gray-900/30 flex items-center justify-between text-[10px] font-mono text-gray-500">
                <div className="flex gap-4">
                    <span>{editorMode.toUpperCase()}</span>
                    <span>UTF-8</span>
                    {lastSaved && (
                        <span className="text-gray-600">
                            LAST SAVED {lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                    <span>SYNCHRONIZED</span>
                </div>
            </div>

            <style dangerouslySetInnerHTML={{
                __html: `
                .ProseMirror {
                    outline: none;
                }
                .ProseMirror p.is-editor-empty:first-child::before {
                    content: 'Start writing or let AI generate content...';
                    float: left;
                    color: #4b5563;
                    pointer-events: none;
                    height: 0;
                }
                .ProseMirror ul[data-type="taskList"] {
                    list-style: none;
                    padding: 0;
                    margin: 1.5rem 0;
                }
                .ProseMirror ul[data-type="taskList"] li {
                    display: flex;
                    align-items: flex-start;
                    gap: 0.75rem;
                    margin-bottom: 0.5rem;
                }
                .ProseMirror ul[data-type="taskList"] input[type="checkbox"] {
                    margin-top: 0.35rem;
                    cursor: pointer;
                }
                .custom-scrollbar::-webkit-scrollbar {
                    width: 4px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: transparent;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background: #1f2937;
                    border-radius: 10px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: #374151;
                }
            ` }} />
        </div>
    );
}
