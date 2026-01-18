"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { apiFetch, getFileToken } from "@/lib/api";
import { Download, FileText, Image, ExternalLink, X, Folder, File, RefreshCw, Trash2, Loader2, Eye } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";

interface FileInfo {
    id: string;
    filename: string;
    mime_type: string;
    size_bytes: number;
    uploaded_at: string;
    has_gemini_ref: boolean;
}

interface ArtifactInfo {
    name: string;
    path: string;
    size: number;
    modified: number;
}

interface FilesSidebarProps {
    nodeType: "hub" | "spoke" | "project";
    nodeName: string;
    onSyncComplete?: (files: FileInfo[]) => void;
}

interface TreeNode {
    name: string;
    path: string;
    type: "file" | "folder";
    children: TreeNode[];
    size?: number;
    modified?: number;
}

const buildFileTree = (artifacts: ArtifactInfo[]): TreeNode[] => {
    const root: TreeNode[] = [];

    artifacts.forEach((artifact) => {
        const parts = artifact.path.split(/[/\\]/);
        let currentLevel = root;
        let currentPath = "";

        parts.forEach((part, index) => {
            currentPath = currentPath ? `${currentPath}/${part}` : part;
            const isLast = index === parts.length - 1;

            let existingNode = currentLevel.find((node) => node.name === part);

            if (!existingNode) {
                existingNode = {
                    name: part,
                    path: currentPath,
                    type: isLast ? "file" : "folder",
                    children: [],
                    size: isLast ? artifact.size : undefined,
                    modified: isLast ? artifact.modified : undefined,
                };
                currentLevel.push(existingNode);
            }

            currentLevel = existingNode.children;
        });
    });

    // Sort: folders first, then files alphabetically
    const sortTree = (nodes: TreeNode[]) => {
        nodes.sort((a, b) => {
            if (a.type !== b.type) {
                return a.type === "folder" ? -1 : 1;
            }
            return a.name.localeCompare(b.name);
        });
        nodes.forEach((node) => {
            if (node.children.length > 0) {
                sortTree(node.children);
            }
        });
    };

    sortTree(root);
    return root;
};

export default function FilesSidebar({ nodeType, nodeName, onSyncComplete }: FilesSidebarProps) {
    const [files, setFiles] = useState<FileInfo[]>([]);
    const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
    const [activeTab, setActiveTab] = useState<"refs" | "artifacts">("refs");
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const [selectedArtifact, setSelectedArtifact] = useState<{
        name: string,
        content?: string,
        path: string,
        type: 'text' | 'image' | 'binary',
        mimeType?: string
    } | null>(null);
    const [collapsedDirs, setCollapsedDirs] = useState<Record<string, boolean>>({});

    const toggleDir = (path: string) => {
        setCollapsedDirs(prev => ({ ...prev, [path]: !prev[path] }));
    };

    const downloadFile = async (url: string, filename: string) => {
        try {
            const token = await getFileToken();
            const downloadUrl = `${url}${url.includes('?') ? '&' : '?'}token=${token}`;

            // Create a temporary link and click it to trigger download
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error("Download failed:", error);
            setError("Failed to generate download link");
        }
    };

    const openArtifact = async (path: string) => {
        try {
            const token = await getFileToken();
            const url = nodeType === 'hub'
                ? `/api/agents/hub/artifacts/${path}?token=${token}`
                : `/api/agents/project/${nodeName}/artifacts/${path}?token=${token}`;
            window.open(url, '_blank');
        } catch (error) {
            console.error("Failed to open artifact:", error);
        }
    };

    const artifactTree = useMemo(() => buildFileTree(artifacts), [artifacts]);

    // Internal component for authenticated image preview
    const ImagePreview = ({ url, name }: { url: string; name: string }) => {
        const [imgToken, setImgToken] = useState<string | null>(null);

        useEffect(() => {
            getFileToken().then(setImgToken).catch(() => { });
        }, []);

        if (!imgToken) {
            return (
                <div className="flex items-center justify-center p-20 text-gray-500 italic">
                    <Loader2 size={24} className="animate-spin mr-2" />
                    Loading preview...
                </div>
            );
        }

        return (
            <div className="flex items-center justify-center p-8 min-h-[400px]">
                <img
                    src={`${url}?token=${imgToken}`}
                    alt={name}
                    className="max-w-full h-auto rounded-lg shadow-2xl border border-gray-800"
                />
            </div>
        );
    };

    // Recursive component to render tree nodes
    const TreeItem = ({ node }: { node: TreeNode }) => {
        const isCollapsed = collapsedDirs[node.path];

        if (node.type === "folder") {
            return (
                <div className="ml-2">
                    <div
                        onClick={() => toggleDir(node.path)}
                        className="flex items-center gap-2 p-1.5 hover:bg-gray-800 rounded cursor-pointer text-sm text-gray-300 group"
                    >
                        {isCollapsed ? <Folder size={14} className="text-gray-500" /> : <Folder size={14} className="text-yellow-500/70" />}
                        <span className="truncate flex-1">{node.name}</span>
                    </div>
                    {!isCollapsed && (
                        <div className="ml-2 border-l border-gray-700/50">
                            {node.children.map((child) => (
                                <TreeItem key={child.path} node={child} />
                            ))}
                        </div>
                    )}
                </div>
            );
        }

        return (
            <div
                className="flex items-center justify-between ml-4 p-1.5 hover:bg-gray-800 rounded cursor-pointer text-sm group"
                onClick={() => viewArtifact(node.path, node.name)}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <File size={14} className={nodeType === "hub" ? "text-purple-400" : "text-cyan-400"} />
                    <span className="truncate text-gray-200" title={node.path}>{node.name}</span>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {node.size !== undefined && (
                        <span className="text-gray-500 text-[10px] mr-1 whitespace-nowrap">
                            {formatSize(node.size)}
                        </span>
                    )}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            openArtifact(node.path);
                        }}
                        className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-white transition-colors"
                        title="Download"
                    >
                        <Download size={12} />
                    </button>
                </div>
            </div>
        );
    };

    // Load files list
    const loadFiles = useCallback(async () => {
        try {
            const response = await apiFetch(`/api/files/${nodeType}/${nodeName}`);
            const data = await response.json();
            setFiles(data.files || []);
        } catch (error) {
            console.error("Failed to load files:", error);
        }
    }, [nodeType, nodeName]);




    // Load artifacts (AI-created files)
    const loadArtifacts = useCallback(async () => {
        try {
            const url = nodeType === "hub"
                ? `/api/agents/hub/artifacts`
                : `/api/agents/project/${nodeName}/artifacts`;
            const response = await apiFetch(url);
            const data = await response.json();
            setArtifacts(data.artifacts || []);
        } catch (error) {
            console.error("Failed to load artifacts:", error);
        }
    }, [nodeType, nodeName]);

    // View artifact content
    const viewArtifact = async (path: string, name: string) => {
        try {
            const isImage = /\.(png|jpe?g|gif|webp|svg)$/i.test(name);
            const url = nodeType === "hub"
                ? `/api/agents/hub/artifacts/${path}`
                : `/api/agents/project/${nodeName}/artifacts/${path}`;

            if (isImage) {
                setSelectedArtifact({ name, path, type: 'image' });
                return;
            }

            const response = await apiFetch(url);
            const contentType = response.headers.get('Content-Type') || '';

            if (contentType.includes('application/json')) {
                const data = await response.json();
                setSelectedArtifact({
                    name,
                    path,
                    content: data.content || "Unable to read file",
                    type: 'text'
                });
            } else if (contentType.includes('text/')) {
                const content = await response.text();
                setSelectedArtifact({ name, path, content, type: 'text' });
            } else {
                // For other types, just show download option
                setSelectedArtifact({ name, path, type: 'binary', mimeType: contentType });
            }
        } catch (error) {
            console.error("Failed to view artifact:", error);
            setSelectedArtifact({ name, path, content: "Error loading file", type: 'text' });
        }
    };

    // Load files on mount
    useEffect(() => {
        loadFiles();
        loadArtifacts();
    }, [nodeType, nodeName, loadFiles, loadArtifacts]);

    // Handle file upload
    const handleUpload = async (file: File) => {
        setUploading(true);
        setUploadProgress(0);
        setError(null);

        const formData = new FormData();
        formData.append("file", file);

        try {
            // Use fetch with proper authorization - use atmos_access_token key
            const token = localStorage.getItem("atmos_access_token");
            const headers: HeadersInit = {};
            if (token) {
                headers["Authorization"] = `Bearer ${token}`;
            } else {
                console.warn("[FilesSidebar] No auth token found in localStorage");
            }

            // Progress simulation since fetch doesn't support progress
            const progressInterval = setInterval(() => {
                setUploadProgress((prev) => Math.min(prev + 10, 90));
            }, 200);

            const response = await fetch(`/api/files/${nodeType}/${nodeName}/upload`, {
                method: "POST",
                headers,
                body: formData,
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Upload failed: ${response.statusText}`);
            }

            await loadFiles();
            setUploadProgress(100);
            setTimeout(() => setUploadProgress(0), 1000);
        } catch (error: any) {
            console.error("Upload error:", error);
            setError(error.message || "Upload failed");
        } finally {
            setUploading(false);
        }
    };

    // Handle multiple file uploads sequentially
    const handleMultipleUpload = async (files: File[]) => {
        if (files.length === 0) return;

        setUploading(true);
        setError(null);

        const totalFiles = files.length;
        let uploadedCount = 0;

        for (const file of files) {
            setUploadProgress(Math.round((uploadedCount / totalFiles) * 100));
            try {
                await handleUpload(file);
                uploadedCount++;
            } catch (error) {
                console.error(`Failed to upload ${file.name}:`, error);
            }
        }

        setUploadProgress(100);
        setTimeout(() => setUploadProgress(0), 1000);
        setUploading(false);
    };

    // Handle file drop
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setDragActive(false);
        const droppedFiles = Array.from(e.dataTransfer.files);
        if (droppedFiles.length > 0) {
            handleMultipleUpload(droppedFiles);
        }
    };

    // Handle file input change
    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            handleMultipleUpload(Array.from(e.target.files));
        }
        // Reset input so the same files can be selected again
        e.target.value = '';
    };

    // Delete file
    const deleteFile = async (fileId: string, filename: string) => {
        if (!confirm(`Delete ${filename}?`)) return;

        try {
            const response = await apiFetch(`/api/files/${fileId}`, {
                method: "DELETE"
            });

            if (response.ok) {
                await loadFiles();
            }
        } catch (error) {
            console.error("Delete error:", error);
        }
    };

    // Format file size
    const formatSize = (bytes: number) => {
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    };

    return (
        <div className="h-full flex flex-col">
            {/* Tabs for both Hub and Spoke */}
            <div className="flex mb-4 border-b border-gray-700">
                <button
                    onClick={() => setActiveTab("refs")}
                    className={`px-3 py-2 text-sm ${activeTab === "refs" ? (nodeType === "hub" ? "text-purple-400 border-b-2 border-purple-400" : "text-cyan-400 border-b-2 border-cyan-400") : "text-gray-400 hover:text-gray-200"}`}
                >
                    📁 References
                </button>
                <button
                    onClick={() => { setActiveTab("artifacts"); loadArtifacts(); }}
                    className={`px-3 py-2 text-sm ${activeTab === "artifacts" ? (nodeType === "hub" ? "text-purple-400 border-b-2 border-purple-400" : "text-cyan-400 border-b-2 border-cyan-400") : "text-gray-400 hover:text-gray-200"}`}
                >
                    📄 Artifacts ({artifacts.length})
                </button>
            </div>

            {/* References Tab Content */}
            {activeTab === "refs" && (
                <>
                    {/* Refresh button */}
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-400">Reference Files</span>
                        <button
                            onClick={loadFiles}
                            disabled={loading}
                            className={`flex items-center gap-1 text-xs px-2 py-1 ${nodeType === "hub" ? "bg-purple-600 hover:bg-purple-500" : "bg-cyan-600 hover:bg-cyan-500"} rounded disabled:opacity-50 transition-colors`}
                        >
                            {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                            <span>Refresh</span>
                        </button>
                    </div>

                    {/* Upload Zone */}
                    <div
                        onDrop={handleDrop}
                        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                        onDragLeave={() => setDragActive(false)}
                        className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors mb-4 ${dragActive ? "border-cyan-500 bg-cyan-500/10" : "border-gray-700 hover:border-gray-600"}`}
                    >
                        <input
                            type="file"
                            id={`file-upload-${nodeType}-${nodeName}`}
                            className="hidden"
                            onChange={handleFileInput}
                            disabled={uploading}
                            multiple
                        />
                        <label htmlFor={`file-upload-${nodeType}-${nodeName}`} className="cursor-pointer">
                            <div className="text-gray-400 text-sm">
                                {uploading ? (
                                    <>
                                        <p>⏳ Uploading... {uploadProgress}%</p>
                                        <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                                            <div className="bg-cyan-500 h-2 rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <p>📤 Drop files or click to upload</p>
                                        <p className="text-xs mt-1 text-gray-500">PDFs, images, docs (max 100MB)</p>
                                    </>
                                )}
                            </div>
                        </label>
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="mb-4 bg-red-500/10 border border-red-500 rounded p-2 text-red-400 text-xs">
                            ❌ {error}
                        </div>
                    )}

                    {/* Files List */}
                    <div className="flex-1 overflow-y-auto">
                        <div className="space-y-2">
                            {files.map((file) => (
                                <div key={file.id} className="flex items-center justify-between bg-gray-800/50 border border-gray-700/50 p-2.5 rounded-lg text-sm group hover:bg-gray-800 transition-colors">
                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                        <div className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.4)]" />
                                        <span className="truncate text-gray-200 font-medium" title={file.filename}>{file.filename}</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <span className="text-gray-500 text-[10px] mr-1">{formatSize(file.size_bytes)}</span>
                                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                            <button
                                                onClick={() => downloadFile(`/api/files/download/${file.id}`, file.filename)}
                                                className="p-1.5 hover:bg-gray-700 rounded text-gray-400 hover:text-cyan-400 transition-colors"
                                                title="Download"
                                            >
                                                <Download size={14} />
                                            </button>
                                            <button
                                                onClick={() => deleteFile(file.id, file.filename)}
                                                className="p-1.5 hover:bg-gray-700 rounded text-gray-400 hover:text-red-400 transition-colors"
                                                title="Delete"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                            {files.length === 0 && !loading && (
                                <p className="text-gray-500 text-xs text-center py-4">No files uploaded yet</p>
                            )}
                        </div>
                    </div>

                    {/* Sync Status */}
                    <div className="mt-4 pt-4 border-t border-gray-800">
                        <p className="text-xs text-gray-500">
                            {loading ? "⏳ Loading files..." :
                                files.length > 0
                                    ? `${files.length} files loaded`
                                    : "No files loaded"}
                        </p>
                    </div>
                </>
            )}

            {/* Artifacts Tab Content */}
            {activeTab === "artifacts" && (
                <div className="flex-1 overflow-y-auto">
                    <p className="text-xs text-gray-400 mb-3">Files created by AI (Hierarchical view)</p>
                    <div className="py-2">
                        {artifactTree.map((node) => (
                            <TreeItem key={node.path} node={node} />
                        ))}
                        {artifacts.length === 0 && (
                            <p className="text-gray-500 text-xs text-center py-4">No artifacts yet. Ask AI to create files!</p>
                        )}
                    </div>
                </div>
            )}

            {/* Artifact Viewer Modal */}
            {selectedArtifact && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setSelectedArtifact(null)}>
                    <div className="bg-gray-900 border border-gray-700 rounded-2xl max-w-4xl max-h-[90vh] w-full shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200" onClick={(e) => e.stopPropagation()}>
                        {/* Modal Header */}
                        <div className="flex items-center justify-between p-4 border-b border-gray-800 bg-gray-900/50">
                            <div className="flex items-center gap-3">
                                {selectedArtifact.type === 'image' ? <Image size={18} className="text-cyan-400" /> : <FileText size={18} className="text-cyan-400" />}
                                <h3 className="font-bold text-gray-100 truncate max-w-md">{selectedArtifact.name}</h3>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => downloadFile(`/api/files/${nodeType}/${nodeName}/artifacts/${selectedArtifact.path}`, selectedArtifact.name)}
                                    className="flex items-center gap-2 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm font-medium transition-colors"
                                >
                                    <Download size={16} />
                                    Download
                                </button>
                                <button
                                    onClick={loadFiles}
                                    className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-all"
                                    title="Refresh file list"
                                    disabled={loading}
                                >
                                    <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                                </button>
                                <button
                                    onClick={() => setSelectedArtifact(null)}
                                    className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        </div>

                        {/* Modal Content */}
                        <div className="flex-1 overflow-auto p-0 bg-gray-950/20">
                            {selectedArtifact.type === 'image' ? (
                                <ImagePreview
                                    url={`/api/files/${nodeType}/${nodeName}/artifacts/${selectedArtifact.path}`}
                                    name={selectedArtifact.name}
                                />
                            ) : selectedArtifact.type === 'text' ? (
                                <div className="p-6">
                                    {selectedArtifact.name.endsWith('.md') ? (
                                        <MarkdownRenderer content={selectedArtifact.content || ''} />
                                    ) : (
                                        <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap leading-relaxed">
                                            {selectedArtifact.content}
                                        </pre>
                                    )}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center p-20 gap-4">
                                    <FileText size={64} className="text-gray-700" />
                                    <p className="text-gray-400 italic">This file type ({selectedArtifact.mimeType || 'binary'}) cannot be previewed.</p>
                                    <button
                                        onClick={() => downloadFile(`/api/files/${nodeType}/${nodeName}/artifacts/${selectedArtifact.path}`, selectedArtifact.name)}
                                        className="text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                                    >
                                        Download to view
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
