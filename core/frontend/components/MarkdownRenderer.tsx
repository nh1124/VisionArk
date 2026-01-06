"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";
import { useState } from "react";

interface MarkdownRendererProps {
    content: string;
    className?: string;
}

export default function MarkdownRenderer({ content, className = "" }: MarkdownRendererProps) {
    return (
        <div className={`markdown-content prose prose-invert max-w-none ${className}`}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    code({ node, inline, className, children, ...props }: any) {
                        const match = /language-(\w+)/.exec(className || "");
                        const [isCopied, setIsCopied] = useState(false);

                        const handleCopy = () => {
                            navigator.clipboard.writeText(String(children));
                            setIsCopied(true);
                            setTimeout(() => setIsCopied(false), 2000);
                        };

                        if (!inline && match) {
                            return (
                                <div className="relative group my-4">
                                    <div className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={handleCopy}
                                            className="p-1.5 rounded-md bg-gray-700/50 hover:bg-gray-600/50 text-gray-300 transition-colors border border-gray-600/50"
                                            title="Copy code"
                                        >
                                            {isCopied ? <Check size={14} /> : <Copy size={14} />}
                                        </button>
                                    </div>
                                    <div className="text-xs text-gray-400 absolute left-4 top-2 font-mono">
                                        {match[1]}
                                    </div>
                                    <SyntaxHighlighter
                                        style={atomDark}
                                        language={match[1]}
                                        PreTag="div"
                                        className="rounded-xl !bg-gray-900/50 !mt-0 !pt-8"
                                        {...props}
                                    >
                                        {String(children).replace(/\n$/, "")}
                                    </SyntaxHighlighter>
                                </div>
                            );
                        }

                        return (
                            <code className="bg-gray-800 px-1.5 py-0.5 rounded text-pink-400 font-mono text-sm" {...props}>
                                {children}
                            </code>
                        );
                    },
                    table({ children }) {
                        return (
                            <div className="overflow-x-auto my-4 rounded-lg border border-gray-700">
                                <table className="min-w-full divide-y divide-gray-700">{children}</table>
                            </div>
                        );
                    },
                    thead({ children }) {
                        return <thead className="bg-gray-800/50">{children}</thead>;
                    },
                    th({ children }) {
                        return (
                            <th className="px-4 py-2 text-left text-xs font-semibold text-gray-300 uppercase tracking-wider">
                                {children}
                            </th>
                        );
                    },
                    td({ children }) {
                        return <td className="px-4 py-2 text-sm text-gray-400 border-t border-gray-700">{children}</td>;
                    },
                    ul({ children }) {
                        return <ul className="list-disc list-inside space-y-1 my-3 text-gray-300">{children}</ul>;
                    },
                    ol({ children }) {
                        return <ol className="list-decimal list-inside space-y-1 my-3 text-gray-300">{children}</ol>;
                    },
                    a({ href, children }) {
                        return (
                            <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-cyan-400 hover:text-cyan-300 transition-colors underline underline-offset-4"
                            >
                                {children}
                            </a>
                        );
                    },
                    h1({ children }) { return <h1 className="text-2xl font-bold mt-6 mb-4 text-white">{children}</h1> },
                    h2({ children }) { return <h2 className="text-xl font-bold mt-5 mb-3 text-white border-b border-gray-800 pb-1">{children}</h2> },
                    h3({ children }) { return <h3 className="text-lg font-bold mt-4 mb-2 text-white">{children}</h3> },
                    blockquote({ children }) {
                        return (
                            <blockquote className="border-l-4 border-purple-500 pl-4 py-1 my-4 italic text-gray-400 bg-purple-500/5 rounded-r-lg">
                                {children}
                            </blockquote>
                        );
                    }
                }}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
}
