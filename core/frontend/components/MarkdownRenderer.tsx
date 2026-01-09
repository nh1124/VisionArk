"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";
import { useState, useEffect } from "react";
import { getFileToken } from "@/lib/api";

interface MarkdownRendererProps {
    content: string;
    className?: string;
    nodeType?: string;
    nodeName?: string;
}

interface CodeBlockProps {
    children: any;
    className?: string;
    inline?: boolean;
    [key: string]: any;
}

const CodeBlock = ({ children, className, inline, ...props }: CodeBlockProps) => {
    const match = /language-(\w+)/.exec(className || "");
    const [isCopied, setIsCopied] = useState(false);

    const handleCopy = () => {
        const text = String(children).replace(/\n$/, "");
        navigator.clipboard.writeText(text);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    if (!inline && match) {
        return (
            <div className="relative group my-4">
                <div className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2">
                    {isCopied && (
                        <span className="text-[10px] bg-gray-950 text-gray-300 px-1.5 py-0.5 rounded border border-gray-800 shadow-xl whitespace-nowrap transition-all duration-200 opacity-100">
                            Copied!
                        </span>
                    )}
                    <button
                        onClick={handleCopy}
                        className="p-1.5 rounded-md bg-gray-700/50 hover:bg-gray-600/50 text-gray-300 transition-colors border border-gray-600/50 backdrop-blur-sm"
                        title="Copy code"
                    >
                        {isCopied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                    </button>
                </div>
                <div className="text-xs text-gray-500 absolute left-4 top-2 font-mono uppercase tracking-wider">
                    {match[1]}
                </div>
                <SyntaxHighlighter
                    style={atomDark}
                    language={match[1]}
                    PreTag="div"
                    className="rounded-xl !bg-gray-950/80 !mt-0 !pt-10 !pb-4 !px-4 border border-gray-800/50 shadow-inner"
                    {...props}
                >
                    {String(children).replace(/\n$/, "")}
                </SyntaxHighlighter>
            </div>
        );
    }

    if (!inline) {
        return (
            <div className="relative group my-4">
                <div className="absolute right-2 top-2 z-10 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-2">
                    {isCopied && (
                        <span className="text-[10px] bg-gray-950 text-gray-300 px-1.5 py-0.5 rounded border border-gray-800 shadow-xl whitespace-nowrap transition-all duration-200 opacity-100">
                            Copied!
                        </span>
                    )}
                    <button
                        onClick={handleCopy}
                        className="p-1.5 rounded-md bg-gray-700/50 hover:bg-gray-600/50 text-gray-300 transition-colors border border-gray-600/50 backdrop-blur-sm"
                        title="Copy code"
                    >
                        {isCopied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                    </button>
                </div>
                <pre className="p-4 rounded-xl bg-gray-950/80 border border-gray-800/50 font-mono text-sm text-gray-300 overflow-x-auto" {...props}>
                    <code>{children}</code>
                </pre>
            </div>
        );
    }

    return (
        <code className="bg-gray-800 px-1.5 py-0.5 rounded text-pink-400 font-mono text-sm" {...props}>
            {children}
        </code>
    );
};

export default function MarkdownRenderer({
    content,
    className = "",
    nodeType = "hub",
    nodeName = "hub"
}: MarkdownRendererProps) {
    // State for short-lived file token
    const [fileToken, setFileToken] = useState<string | null>(null);

    useEffect(() => {
        getFileToken().then(setFileToken).catch(err => {
            console.error("[MarkdownRenderer] Failed to get file token:", err);
        });
    }, []);

    const tokenQuery = fileToken ? `?token=${fileToken}` : "";

    // Pre-process content to catch bare artifact/ref paths and turn them into images
    // Matches patterns like artifacts/image.png or /artifacts/image.png
    const processedContent = content.replace(
        /(?<![!\]\(\[])\b((?:\/?(?:artifacts|refs|files))\/[^\s\)]+\.(?:png|jpe?g|gif|webp|svg|bmp|tiff))\b/gi,
        (match) => `![${match}](${match})`
    );

    return (
        <div className={`markdown-content prose prose-invert max-w-none ${className}`}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    img({ node, src, alt, ...props }: any) {
                        // Transform local paths to API proxy URLs
                        let processedSrc = src;
                        if (src && !src.startsWith("http")) {
                            // Check if it's an artifact or reference
                            const isArtifact = src.startsWith("artifacts/") || src.includes("/artifacts/");
                            const isReference = src.startsWith("refs/") || src.includes("/refs/");
                            const isFile = src.startsWith("files/") || src.includes("/files/");

                            if (isArtifact || isReference || isFile) {
                                let cleanPath = src.startsWith("/") ? src.substring(1) : src;
                                processedSrc = `/api/files/${nodeType}/${nodeName}/${cleanPath}${tokenQuery}`;
                            } else if (!src.includes("/")) {
                                // Default simple filename to artifacts directory
                                processedSrc = `/api/files/${nodeType}/${nodeName}/artifacts/${src}${tokenQuery}`;
                            }
                        } else if (src && src.startsWith("http") && src.includes("/api/files/")) {
                            // Already processed but might need token
                            if (!src.includes("token=")) {
                                processedSrc = `${src}${src.includes("?") ? "&" : "?"}token=${fileToken || ""}`;
                            }
                        }

                        return (
                            <div className="my-6">
                                <img
                                    src={processedSrc}
                                    alt={alt || "Image"}
                                    className="max-w-full h-auto rounded-xl shadow-lg border border-gray-800/50 hover:shadow-2xl transition-all duration-300"
                                    loading="lazy"
                                    {...props}
                                />
                                {alt && <p className="text-center text-xs text-gray-500 mt-2 italic">{alt}</p>}
                            </div>
                        );
                    },
                    code: CodeBlock,
                    table({ children }) {
                        return (
                            <div className="overflow-x-auto my-6 rounded-xl border border-gray-800/50 bg-gray-900/20 shadow-sm">
                                <table className="min-w-full divide-y divide-gray-800/50">{children}</table>
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
                        return <td className="px-5 py-3 text-sm text-gray-400 border-t border-gray-800/50">{children}</td>;
                    },
                    ul({ children }) {
                        return <ul className="list-disc list-inside space-y-1 my-3 text-gray-300">{children}</ul>;
                    },
                    ol({ children }) {
                        return <ol className="list-decimal list-inside space-y-1 my-3 text-gray-300">{children}</ol>;
                    },
                    a({ href, children }) {
                        // YouTube Link Detection
                        const youtubeRegex = /^(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
                        const match = href?.match(youtubeRegex);

                        if (match) {
                            const videoId = match[1];
                            return (
                                <div className="my-6 aspect-video rounded-xl overflow-hidden shadow-2xl border border-gray-800/50">
                                    <iframe
                                        width="100%"
                                        height="100%"
                                        src={`https://www.youtube.com/embed/${videoId}`}
                                        title="YouTube video player"
                                        frameBorder="0"
                                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                        allowFullScreen
                                        className="w-full h-full"
                                    />
                                </div>
                            );
                        }

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
                {processedContent}
            </ReactMarkdown>
        </div>
    );
}
