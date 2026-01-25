"use client";

import { ReactNodeViewRenderer, NodeViewWrapper, NodeViewContent } from "@tiptap/react";
import CodeBlock from "@tiptap/extension-code-block";
import Mermaid from "./Mermaid";
import React, { useState } from "react";
import { Pencil, Eye } from "lucide-react";

const MermaidComponent = ({ node, updateAttributes, extension }: any) => {
    const [isEditing, setIsEditing] = useState(false);
    const language = node.attrs.language;
    const isMermaid = language?.toLowerCase() === "mermaid";
    const chart = node.content.content?.[0]?.text || "";

    if (!isMermaid) {
        return (
            <NodeViewWrapper className="code-block relative">
                <pre>
                    <NodeViewContent as="code" />
                </pre>
            </NodeViewWrapper>
        );
    }

    return (
        <NodeViewWrapper className="mermaid-block relative group my-6">
            <div className="absolute right-2 top-2 z-20 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                <button
                    onClick={() => setIsEditing(!isEditing)}
                    className="p-1.5 rounded-md bg-gray-800/90 hover:bg-gray-700 text-gray-400 hover:text-cyan-400 transition-all border border-gray-700 shadow-xl backdrop-blur-sm"
                    title={isEditing ? "View Diagram" : "Edit Code"}
                >
                    {isEditing ? <Eye size={14} /> : <Pencil size={14} />}
                </button>
            </div>

            {isEditing ? (
                <div className="bg-gray-950/90 rounded-xl border border-gray-800 p-4 font-mono text-sm shadow-2xl">
                    <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-2 px-1 flex justify-between items-center">
                        <span>Mermaid Source</span>
                        <span className="text-cyan-500/50">Editing</span>
                    </div>
                    <pre className="outline-none">
                        <NodeViewContent as="code" className="block min-h-[1em] language-mermaid" />
                    </pre>
                </div>
            ) : (
                <div className="bg-transparent cursor-pointer" onClick={() => setIsEditing(true)}>
                    <Mermaid chart={chart} />
                    {chart.trim() === "" && (
                        <div className="p-12 border-2 border-dashed border-gray-800 rounded-2xl text-center text-gray-600 hover:border-gray-700 transition-colors">
                            <Pencil size={24} className="mx-auto mb-2 opacity-20" />
                            <p>Empty Mermaid Chart</p>
                            <p className="text-xs mt-1">Click to edit and create a visualization</p>
                        </div>
                    )}
                </div>
            )}
        </NodeViewWrapper>
    );
};

export const MermaidExtension = CodeBlock.extend({
    addNodeView() {
        return ReactNodeViewRenderer(MermaidComponent);
    },
});
