"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { apiFetch, getFileToken } from "@/lib/api";
import { Download, FileText, Image, ExternalLink, X, Folder, File as FileIcon, RefreshCw, Trash2, Loader2, Eye, Plus } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useNotification } from "@/lib/NotificationContext";

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
    onOpenFile?: (content: string, filePath: string, format: "markdown" | "code") => void;
    onPreviewImage?: (url: string, name: string) => void;
}

interface TreeNode {
    name: string;
    path: string;
    type: "file" | "folder";
    children: TreeNode[];
    size?: number;
    modified?: number;
}

interface TreeItemData {
    id?: string;
    name: string;
    path: string;
    size?: number;
    modified?: string | number;
    mime_type?: string;
    source?: 'disk' | 'database';
}

const buildFileTree = (items: TreeItemData[]): TreeNode[] => {
    const root: TreeNode[] = [];

    items.forEach((item) => {
        const parts = item.path.split(/[/\\]/);
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
                    size: isLast ? item.size : undefined,
                    modified: isLast ? (typeof item.modified === 'string' ? Date.parse(item.modified) / 1000 : item.modified) : undefined,
                };
                // Store additional data for files
                if (isLast) {
                    (existingNode as any).id = item.id;
                    (existingNode as any).mime_type = item.mime_type;
                }
                currentLevel.push(existingNode);
            } else if (isLast && existingNode.type === "folder") {
                // Handle edge case where a file and folder have same name (rare)
                // We'll just treat it as a file for now or leave as is
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

export default function FilesSidebar({ nodeType, nodeName, onSyncComplete, onOpenFile, onPreviewImage }: FilesSidebarProps) {
    const [files, setFiles] = useState<FileInfo[]>([]);
    const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
    const [activeTab, setActiveTab] = useState<"refs" | "artifacts">("refs");
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [collapsedDirs, setCollapsedDirs] = useState<Record<string, boolean>>({});
    const [isCreatingNewFile, setIsCreatingNewFile] = useState(false);
    const [newFileName, setNewFileName] = useState("");
    const [dragActive, setDragActive] = useState(false);

    const toggleDir = (path: string) => {
        setCollapsedDirs(prev => ({ ...prev, [path]: !prev[path] }));
    };

    const { showConfirm, showToast } = useNotification();

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



    const refTree = useMemo(() => buildFileTree(files.map(f => ({
        id: f.id,
        name: f.filename.split(/[/\\]/).pop() || f.filename,
        path: f.filename,
        size: f.size_bytes,
        modified: f.uploaded_at,
        mime_type: f.mime_type
    }))), [files]);

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
    const TreeItem = ({ node, isArtifact = false }: { node: TreeNode, isArtifact?: boolean }) => {
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
                        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                                onClick={(e) => { e.stopPropagation(); downloadFile(`/api/files/project/${nodeName}/${isArtifact ? 'artifacts' : 'refs'}/${node.path}/zip`, `${node.name}.zip`); }}
                                className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-white transition-colors"
                                title="Download Folder (ZIP)"
                            >
                                <Download size={12} />
                            </button>
                            <button
                                onClick={(e) => { e.stopPropagation(); handleDeletePath(node.path, node.name, isArtifact ? "artifacts" : "refs", true); }}
                                className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-red-400 transition-colors"
                                title="Delete Folder"
                            >
                                <Trash2 size={12} />
                            </button>
                        </div>
                    </div>
                    {!isCollapsed && (
                        <div className="ml-2 border-l border-gray-700/50">
                            {node.children.map((child) => (
                                <TreeItem key={child.path} node={child} isArtifact={isArtifact} />
                            ))}
                        </div>
                    )}
                </div>
            );
        }

        const fileId = (node as any).id;
        const isImage = (node as any).mime_type?.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(node.name);

        const handleDownload = (e: React.MouseEvent) => {
            e.stopPropagation();
            if (isArtifact) {
                downloadFile(`/api/files/project/${nodeName}/artifacts/${node.path}`, node.name);
            } else {
                if (fileId?.startsWith('disk:')) {
                    const relativePath = fileId.replace('disk:refs/', '');
                    downloadFile(`/api/files/project/${nodeName}/refs/${relativePath}`, node.name);
                } else {
                    downloadFile(`/api/files/download/${fileId}`, node.name);
                }
            }
        };

        const handleClick = async () => {
            if (isImage) {
                const token = await getFileToken();
                const url = `/api/files/project/${nodeName}/${isArtifact ? 'artifacts' : 'refs'}/${node.path}?token=${token}`;
                onPreviewImage?.(url, node.name);
            } else {
                openFileInCanvas(node.path, node.name, isArtifact ? "artifacts" : "refs");
            }
        };

        return (
            <div
                className="flex items-center justify-between ml-4 p-1.5 hover:bg-gray-800 rounded cursor-pointer text-sm group"
                onClick={handleClick}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <FileIcon size={14} className={isArtifact ? (nodeType === "hub" ? "text-purple-400" : "text-cyan-400") : "text-blue-400"} />
                    <span className="truncate text-gray-200" title={node.path}>{node.name}</span>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    {node.size !== undefined && (
                        <span className="text-gray-500 text-[10px] mr-1 whitespace-nowrap">
                            {formatSize(node.size)}
                        </span>
                    )}
                    <button
                        onClick={handleDownload}
                        className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-white transition-colors"
                        title="Download"
                    >
                        <Download size={12} />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); handleDeletePath(node.path, node.name, isArtifact ? "artifacts" : "refs"); }}
                        className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-red-400 transition-colors"
                        title="Delete"
                    >
                        <Trash2 size={12} />
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

    // Create a new empty file
    const handleCreateNewFile = async () => {
        const filename = newFileName.trim();
        if (!filename) return;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/files/project/${nodeName}/save`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    path: filename,
                    content: "",
                    directory: "refs"
                })
            });

            if (!response.ok) throw new Error("Failed to create file");

            showToast(`File ${filename} created successfully`, "success");
            await loadFiles();

            // Open it automatically in canvas
            openFileInCanvas(filename, filename.split('/').pop() || filename, "refs");
        } catch (error) {
            console.error("Create file error:", error);
            showToast("Failed to create new file", "error");
        } finally {
            setLoading(false);
            setIsCreatingNewFile(false);
            setNewFileName("");
        }
    };




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

    // Open file content in canvas
    const openFileInCanvas = async (path: string, name: string, directory: "refs" | "artifacts" | "files") => {
        try {
            const url = `/api/files/project/${nodeName}/${directory}/${path}`;

            const response = await apiFetch(url);
            if (!response.ok) throw new Error("Failed to fetch file");

            const contentType = response.headers.get('Content-Type') || '';

            if (contentType.includes('application/json')) {
                const data = await response.json();
                onOpenFile?.(data.content || JSON.stringify(data, null, 2), `${directory}/${path}`, "markdown");
            } else if (contentType.includes('text/')) {
                const content = await response.text();
                const isCode = /\.(js|ts|py|tsx|jsx|html|css|json|yaml|yml|c|cpp|h|hpp|rs|go|rb|php|sh|bat|ps1|sql|env|gitignore|dockerfile|makefile)$/i.test(name) || name.toLowerCase().includes('dockerfile');
                onOpenFile?.(content, `${directory}/${path}`, isCode ? "code" : "markdown");
            } else {
                console.log("Unsupported file type for canvas opening:", contentType);
            }
        } catch (error) {
            console.error("Failed to open file:", error);
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

    // Delete file or directory by path
    const handleDeletePath = async (path: string, name: string, directory: "refs" | "artifacts", isFolder: boolean = false) => {
        const confirmed = await showConfirm(
            `Delete ${isFolder ? "folder" : "file"} ${name}?${isFolder ? " This will delete all contents inside." : ""}`,
            {
                title: isFolder ? "Delete Folder" : "Delete File",
                confirmText: "Delete",
                variant: "danger"
            }
        );

        if (!confirmed) return;

        try {
            setLoading(true);
            const response = await apiFetch(`/api/files/project/${nodeName}/${directory}/${encodeURIComponent(path)}`, {
                method: "DELETE"
            });

            if (response.ok) {
                showToast(`${name} deleted successfully`, "success");
                await loadFiles();
                await loadArtifacts();
            } else {
                const data = await response.json();
                showToast(data.detail || "Failed to delete", "error");
            }
        } catch (error) {
            console.error("Delete error:", error);
            showToast("Failed to delete", "error");
        } finally {
            setLoading(false);
        }
    };

    // Delete file by ID (legacy ref - keeping for compatibility if needed, but updated UI to use path)
    const deleteFile = async (fileId: string, filename: string) => {
        const confirmed = await showConfirm(`Delete ${filename}?`, {
            title: "Delete File",
            confirmText: "Delete",
            variant: "danger"
        });

        if (!confirmed) return;

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
                    {/* New File Input */}
                    {isCreatingNewFile && (
                        <div className="mb-4 flex items-center gap-2 p-2 bg-gray-800/50 rounded-lg border border-cyan-500/30 animate-in slide-in-from-top-2 duration-200">
                            <input
                                autoFocus
                                type="text"
                                value={newFileName}
                                onChange={(e) => setNewFileName(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter") handleCreateNewFile();
                                    if (e.key === "Escape") setIsCreatingNewFile(false);
                                }}
                                placeholder="filename.md"
                                className="flex-1 bg-transparent border-none outline-none text-sm text-gray-200"
                            />
                            <button
                                onClick={handleCreateNewFile}
                                className="text-cyan-400 hover:text-cyan-300 p-1"
                            >
                                <Plus size={16} />
                            </button>
                            <button
                                onClick={() => setIsCreatingNewFile(false)}
                                className="text-gray-500 hover:text-white p-1"
                            >
                                <X size={16} />
                            </button>
                        </div>
                    )}

                    {/* Refresh button */}
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-400">Reference Files</span>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={() => setIsCreatingNewFile(true)}
                                disabled={loading || isCreatingNewFile}
                                className={`flex items-center gap-1 text-xs px-2 py-1 ${nodeType === "hub" ? "bg-purple-600 hover:bg-purple-500" : "bg-cyan-600 hover:bg-cyan-500"} rounded disabled:opacity-50 transition-colors mr-1`}
                                title="Create New File"
                            >
                                <Plus size={12} />
                                <span>New</span>
                            </button>
                            <button
                                onClick={loadFiles}
                                disabled={loading}
                                className={`flex items-center gap-1 text-xs px-2 py-1 ${nodeType === "hub" ? "bg-purple-600 hover:bg-purple-500" : "bg-cyan-600 hover:bg-cyan-500"} rounded disabled:opacity-50 transition-colors`}
                            >
                                {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                                <span>Refresh</span>
                            </button>
                        </div>
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

                    {/* Files List - Hierarchical Tree */}
                    <div className="flex-1 overflow-y-auto">
                        <div className="space-y-1">
                            {refTree.map((node) => (
                                <TreeItem key={node.path} node={node} isArtifact={false} />
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
                            <TreeItem key={node.path} node={node} isArtifact={true} />
                        ))}
                        {artifacts.length === 0 && (
                            <p className="text-gray-500 text-xs text-center py-4">No artifacts yet. Ask AI to create files!</p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
