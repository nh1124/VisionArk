"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { apiFetch, getFileToken } from "@/lib/api";
import { Download, FileText, Image, ExternalLink, X, Folder, File as FileIcon, RefreshCw, Trash2, Loader2, Eye, Plus, CheckSquare, Square, CheckCircle2, ChevronsUp, ChevronsDown } from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { useNotification } from "@/lib/NotificationContext";
import { useIsMobile } from "@/hooks/useIsMobile";

interface FileInfo {
    id: string;
    filename: string;
    directory: string;
    is_directory: boolean;
    mime_type: string;
    size_bytes: number;
    uploaded_at: string;
}

interface FilesSidebarProps {
    nodeType: "hub" | "spoke" | "project";
    nodeName: string;
    onSyncComplete?: (files: FileInfo[]) => void;
    onOpenFile?: (content: string, filePath: string, format: "markdown" | "code") => void;
    onPreviewImage?: (url: string, name: string) => void;
}

interface TreeNode {
    id?: string;
    name: string;
    path: string;
    type: "file" | "folder";
    children: TreeNode[];
    size?: number;
    modified?: number;
    directory?: string;
    mime_type?: string;
}

interface TreeItemData {
    id: string;
    filename: string;
    directory: string;
    is_directory: boolean;
    mime_type: string;
    size_bytes: number;
    uploaded_at: string;
}

const buildFileTree = (items: TreeItemData[]): TreeNode[] => {
    const root: TreeNode[] = [];
    const map: { [key: string]: TreeNode } = {};

    items.forEach((item) => {
        const parts = item.filename.split(/[/\\]/);
        let currentPath = "";

        parts.forEach((part, index) => {
            const isLast = index === parts.length - 1;
            const parentPath = currentPath;
            currentPath = currentPath ? `${currentPath}/${part}` : part;

            if (!map[currentPath]) {
                const node: TreeNode = {
                    id: isLast || item.is_directory ? item.id : undefined,
                    name: part,
                    path: currentPath,
                    type: isLast && !item.is_directory ? "file" : "folder",
                    children: [],
                    size: isLast ? item.size_bytes : undefined,
                    modified: isLast ? Date.parse(item.uploaded_at) / 1000 : undefined,
                    directory: item.directory,
                    mime_type: isLast ? item.mime_type : undefined
                };

                // If it's a directory record from DB, it will have an ID
                if (item.is_directory && item.filename === currentPath) {
                    node.id = item.id;
                }

                map[currentPath] = node;

                if (parentPath) {
                    map[parentPath].children.push(node);
                } else {
                    root.push(node);
                }
            } else if (isLast) {
                // If we found the actual record for this path (file or folder), update ID
                map[currentPath].id = item.id;
                if (!item.is_directory) {
                    map[currentPath].type = "file";
                    map[currentPath].size = item.size_bytes;
                    map[currentPath].mime_type = item.mime_type;
                }
            }
        });
    });

    const sortTree = (nodes: TreeNode[]) => {
        nodes.sort((a, b) => {
            if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
            return a.name.localeCompare(b.name);
        });
        nodes.forEach((node) => {
            if (node.children.length > 0) sortTree(node.children);
        });
    };

    sortTree(root);
    return root;
};

export default function FilesSidebar({ nodeType, nodeName, onSyncComplete, onOpenFile, onPreviewImage }: FilesSidebarProps) {
    const isMobile = useIsMobile();
    const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [files, setFiles] = useState<FileInfo[]>([]);
    const [activeTab, setActiveTab] = useState<"refs" | "artifacts">("refs");
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [collapsedDirs, setCollapsedDirs] = useState<Record<string, boolean>>({});
    const [isCreatingNewFile, setIsCreatingNewFile] = useState(false);
    const [newFileName, setNewFileName] = useState("");
    const [dragActive, setDragActive] = useState(false);

    const { showConfirm, showToast } = useNotification();

    const toggleSelection = (path: string, node: TreeNode) => {
        setSelectedPaths(prev => {
            const next = new Set(prev);
            const nextIds = new Set(selectedIds);
            const shouldSelect = !next.has(path);

            const toggleRecursive = (n: TreeNode, select: boolean) => {
                if (select) {
                    next.add(n.path);
                    if (n.id) nextIds.add(n.id);
                } else {
                    next.delete(n.path);
                    if (n.id) nextIds.delete(n.id);
                }
                n.children?.forEach(child => toggleRecursive(child, select));
            };

            toggleRecursive(node, shouldSelect);
            setSelectedIds(nextIds);
            return next;
        });
    };

    const isPathSelected = (path: string) => selectedPaths.has(path);

    const clearSelection = () => {
        setSelectedPaths(new Set());
        setSelectedIds(new Set());
    };

    const loadFiles = useCallback(async (silent = false) => {
        try {
            if (!silent) setLoading(true);
            const response = await apiFetch(`/api/files/project/${nodeName}/list`);
            const data = await response.json();
            setFiles(data.files || []);
        } catch (error) {
            console.error("Failed to load files:", error);
        } finally {
            if (!silent) setLoading(false);
        }
    }, [nodeName]);

    const deleteSelected = async () => {
        if (selectedIds.size === 0) return;

        const confirmed = await showConfirm(
            `Delete ${selectedIds.size} selected items?`,
            {
                title: "Batch Delete",
                confirmText: "Delete All",
                variant: "danger"
            }
        );

        if (!confirmed) return;

        // Optimistic update
        const remainingFiles = files.filter(f => !selectedIds.has(f.id));
        setFiles(remainingFiles);
        clearSelection();

        try {
            for (const id of Array.from(selectedIds)) {
                await apiFetch(`/api/files/${id}`, {
                    method: "DELETE"
                });
            }
            showToast(`Deleted ${selectedIds.size} items`, "success");
            await loadFiles(true);
        } catch (error) {
            console.error("Batch delete error:", error);
            showToast("Failed to delete some items", "error");
            await loadFiles(); // Revert/Reload on error
        }
    };

    const handleDeletePath = async (id: string | undefined, name: string, isFolder: boolean = false) => {
        if (!id) {
            showToast("Cannot delete: Item has no ID", "error");
            return;
        }

        const confirmed = await showConfirm(
            `Delete ${isFolder ? "folder" : "file"} ${name}?${isFolder ? " This will delete all contents inside." : ""}`,
            {
                title: isFolder ? "Delete Folder" : "Delete File",
                confirmText: "Delete",
                variant: "danger"
            }
        );

        if (!confirmed) return;

        // Optimistic update
        if (id) {
            setFiles(prev => prev.filter(f => f.id !== id));
        } else if (isFolder) {
            // If it's a folder, remove all files that start with this name in the current directory
            setFiles(prev => prev.filter(f => !f.filename.startsWith(name)));
        }

        try {
            setLoading(true);
            const response = await apiFetch(`/api/files/${id}`, {
                method: "DELETE"
            });

            if (response.ok) {
                showToast(`${name} deleted successfully`, "success");
                await loadFiles(true);
            } else {
                const data = await response.json();
                showToast(data.detail || "Failed to delete", "error");
                await loadFiles(); // Reload to restore
            }
        } catch (error) {
            console.error("Delete error:", error);
            showToast("Failed to delete", "error");
            await loadFiles(); // Reload to restore
        } finally {
            setLoading(false);
        }
    };

    const toggleDir = (path: string) => {
        setCollapsedDirs(prev => ({ ...prev, [path]: !prev[path] }));
    };

    const toggleAllFolders = () => {
        const allFolderPaths: string[] = [];
        const collectFolders = (nodes: TreeNode[]) => {
            nodes.forEach(node => {
                if (node.type === "folder") {
                    allFolderPaths.push(node.path);
                    collectFolders(node.children);
                }
            });
        };
        collectFolders(projectTree);

        const anyExpanded = allFolderPaths.some(path => !collapsedDirs[path]);
        if (anyExpanded) {
            // Collapse all
            const newCollapsed: Record<string, boolean> = {};
            allFolderPaths.forEach(path => { newCollapsed[path] = true; });
            setCollapsedDirs(newCollapsed);
        } else {
            // Expand all
            setCollapsedDirs({});
        }
    };

    const downloadFile = async (fileId: string, filename: string) => {
        try {
            const token = await getFileToken();
            const url = `/api/files/download/${fileId}?token=${token}`;
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error("Download failed:", error);
            showToast("Failed to generate download link", "error");
        }
    };

    const openFileInCanvas = async (fileId: string, name: string) => {
        try {
            const url = `/api/files/content/${fileId}`;
            const response = await apiFetch(url);
            if (!response.ok) throw new Error("Failed to fetch file content");

            const data = await response.json();
            const isCode = /\.(js|ts|py|tsx|jsx|html|css|json|yaml|yml|c|cpp|h|hpp|rs|go|rb|php|sh|bat|ps1|sql|env|gitignore|dockerfile|makefile)$/i.test(name) || name.toLowerCase().includes('dockerfile');

            onOpenFile?.(data.content, data.path, isCode ? "code" : "markdown");
        } catch (error) {
            console.error("Failed to open file:", error);
            showToast("Failed to open file", "error");
        }
    };

    useEffect(() => {
        loadFiles();

        // Background polling every 10 seconds
        const interval = setInterval(() => loadFiles(true), 10000);
        return () => clearInterval(interval);
    }, [loadFiles]);

    const projectTree = useMemo(() => {
        const filtered = files.filter(f => f.directory === activeTab);
        return buildFileTree(filtered);
    }, [files, activeTab]);

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
        const isSelected = isPathSelected(node.path);

        if (node.type === "folder") {
            const hasSomeChildrenSelected = !isSelected && node.children.some(child => isPathSelected(child.path) || (child.type === 'folder' && child.children.some(gc => isPathSelected(gc.path))));

            return (
                <div className="ml-2">
                    <div
                        className={`flex items-center gap-2 ${isMobile ? "p-3" : "p-1.5"} hover:bg-gray-800 rounded cursor-pointer text-sm text-gray-300 group`}
                    >
                        <button
                            onClick={(e) => { e.stopPropagation(); toggleSelection(node.path, node); }}
                            className={`p-1 hover:bg-gray-700 rounded transition-colors ${isSelected ? "text-cyan-400" : hasSomeChildrenSelected ? "text-cyan-600" : "text-gray-600"}`}
                        >
                            {isSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                        </button>
                        <div className="flex items-center gap-2 flex-1 min-w-0" onClick={() => toggleDir(node.path)}>
                            {isCollapsed ? <Folder size={14} className="text-gray-500" /> : <Folder size={14} className="text-yellow-500/70" />}
                            <span className="truncate flex-1">{node.name}</span>
                        </div>
                        <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                            {node.id && (
                                <button
                                    onClick={(e) => { e.stopPropagation(); if (node.id) window.open(`/api/files/download/${node.id}/zip`, '_blank'); }}
                                    className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-white transition-colors"
                                    title="Download ZIP"
                                >
                                    <Download size={12} />
                                </button>
                            )}
                            <button
                                onClick={(e) => { e.stopPropagation(); handleDeletePath(node.id, node.name, true); }}
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
                                <TreeItem key={child.path} node={child} />
                            ))}
                        </div>
                    )}
                </div>
            );
        }

        const isImage = node.mime_type?.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(node.name);

        const handleDownload = (e: React.MouseEvent) => {
            e.stopPropagation();
            if (node.id) downloadFile(node.id, node.name);
        };

        const handleClick = async () => {
            if (isImage && node.id) {
                const token = await getFileToken();
                const url = `/api/files/download/${node.id}?token=${token}`;
                onPreviewImage?.(url, node.name);
            } else if (node.id) {
                openFileInCanvas(node.id, node.name);
            }
        };

        return (
            <div
                className={`flex items-center justify-between ml-4 ${isMobile ? "p-3" : "p-1.5"} hover:bg-gray-800 rounded cursor-pointer text-sm group ${isSelected ? "bg-cyan-500/10 border-l-2 border-cyan-500" : ""}`}
                onClick={handleClick}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <button
                        onClick={(e) => { e.stopPropagation(); toggleSelection(node.path, node); }}
                        className={`p-1 hover:bg-gray-700 rounded transition-colors ${isSelected ? "text-cyan-400" : "text-gray-600"}`}
                    >
                        {isSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                    </button>
                    <FileIcon size={14} className={activeTab === "artifacts" ? "text-cyan-400" : "text-blue-400"} />
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
                        onClick={(e) => { e.stopPropagation(); handleDeletePath(node.id, node.name); }}
                        className="p-1 hover:bg-gray-700 rounded text-gray-400 hover:text-red-400 transition-colors"
                        title="Delete"
                    >
                        <Trash2 size={12} />
                    </button>
                </div>
            </div>
        );
    };

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
                    filename: filename,
                    content: "",
                    directory: activeTab
                })
            });

            if (!response.ok) throw new Error("Failed to create file");

            const result = await response.json();
            // Optimistic update: add the new file to the list
            if (result.file) {
                setFiles(prev => [...prev, result.file]);
            }

            showToast(`File ${filename} created successfully`, "success");
            await loadFiles(true);
        } catch (error) {
            console.error("Create file error:", error);
            showToast("Failed to create new file", "error");
            await loadFiles();
        } finally {
            setLoading(false);
            setIsCreatingNewFile(false);
            setNewFileName("");
        }
    };

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

            const response = await fetch(`/api/files/project/${nodeName}/${activeTab}/upload`, {
                method: "POST",
                headers,
                body: formData,
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Upload failed: ${response.statusText}`);
            }

            const result = await response.json();
            // Add uploaded files to state
            if (result.files) {
                setFiles(prev => [...prev, ...result.files]);
            } else if (result.file) {
                setFiles(prev => [...prev, result.file]);
            }

            await loadFiles(true);
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
            {/* Tabs */}
            <div className={`flex mb-4 border-b border-gray-700 ${isMobile ? "overflow-x-auto no-scrollbar" : ""}`}>
                <button
                    onClick={() => { setActiveTab("refs"); clearSelection(); }}
                    className={`px-4 py-3 text-sm whitespace-nowrap ${activeTab === "refs" ? (nodeType === "hub" ? "text-purple-400 border-b-2 border-purple-400" : "text-cyan-400 border-b-2 border-cyan-400") : "text-gray-400 hover:text-gray-200"}`}
                >
                    📁 References
                </button>
                <button
                    onClick={() => { setActiveTab("artifacts"); clearSelection(); }}
                    className={`px-4 py-3 text-sm whitespace-nowrap ${activeTab === "artifacts" ? (nodeType === "hub" ? "text-purple-400 border-b-2 border-purple-400" : "text-cyan-400 border-b-2 border-cyan-400") : "text-gray-400 hover:text-gray-200"}`}
                >
                    📄 Artifacts
                </button>
            </div>

            {/* Selection Bar */}
            {selectedPaths.size > 0 && (
                <div className="mb-4 p-2 bg-cyan-950/30 border border-cyan-500/30 rounded-lg flex items-center justify-between animate-in fade-in slide-in-from-top-2 duration-200">
                    <div className="flex items-center gap-2">
                        <CheckCircle2 size={16} className="text-cyan-400" />
                        <span className="text-xs font-bold text-cyan-400">{selectedPaths.size} selected</span>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={clearSelection} className="text-[10px] uppercase tracking-wider font-bold text-gray-400 hover:text-white px-2 py-1">Cancel</button>
                        <button onClick={deleteSelected} className="bg-red-500/20 hover:bg-red-500/30 text-red-400 text-[10px] uppercase tracking-wider font-bold px-2 py-1 rounded border border-red-500/30 transition-colors flex items-center gap-1">
                            <Trash2 size={10} /> Delete Selected
                        </button>
                    </div>
                </div>
            )}

            {/* Common UI Elements (Ref-specific mostly) */}
            {activeTab === "refs" ? (
                <>
                    {isCreatingNewFile && (
                        <div className="mb-4 flex items-center gap-2 p-2 bg-gray-800/50 rounded-lg border border-cyan-500/30 animate-in slide-in-from-top-2 duration-200">
                            <input
                                autoFocus
                                type="text"
                                value={newFileName}
                                onChange={(e) => setNewFileName(e.target.value)}
                                onKeyDown={(e) => { if (e.key === "Enter") handleCreateNewFile(); if (e.key === "Escape") setIsCreatingNewFile(false); }}
                                placeholder="filename.md"
                                className="flex-1 bg-transparent border-none outline-none text-sm text-gray-200"
                            />
                            <button onClick={handleCreateNewFile} className="text-cyan-400 hover:text-cyan-300 p-1"><Plus size={16} /></button>
                            <button onClick={() => setIsCreatingNewFile(false)} className="text-gray-500 hover:text-white p-1"><X size={16} /></button>
                        </div>
                    )}

                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-400">Files</span>
                        <div className="flex items-center gap-1">
                            <button
                                onClick={toggleAllFolders}
                                title="Toggle All"
                                className="p-1 text-gray-600 hover:text-white transition-colors"
                            >
                                {Object.keys(collapsedDirs).length > 0 ? <ChevronsDown size={14} /> : <ChevronsUp size={14} />}
                            </button>
                            <button onClick={() => setIsCreatingNewFile(true)} className={`flex items-center gap-1 text-xs px-2 py-1 ${nodeType === "hub" ? "bg-purple-600 hover:bg-purple-500" : "bg-cyan-600 hover:bg-cyan-500"} rounded disabled:opacity-50 transition-colors mr-1`}><Plus size={12} /><span>New</span></button>
                        </div>
                    </div>

                    <div
                        onDrop={handleDrop}
                        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                        onDragLeave={() => setDragActive(false)}
                        className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors mb-4 ${dragActive ? "border-cyan-500 bg-cyan-500/10" : "border-gray-700 hover:border-gray-600"}`}
                    >
                        <input type="file" id={`file-upload-${nodeName}`} className="hidden" onChange={handleFileInput} multiple />
                        <label htmlFor={`file-upload-${nodeName}`} className="cursor-pointer">
                            <div className="text-gray-400 text-sm">
                                {uploading ? <p>⏳ Uploading... {uploadProgress}%</p> : <p>📤 Drop files or click to upload</p>}
                            </div>
                        </label>
                    </div>
                </>
            ) : (
                <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm text-gray-400">Generated Artifacts</span>
                    <button
                        onClick={toggleAllFolders}
                        title="Toggle All"
                        className="p-1 text-gray-600 hover:text-white transition-colors"
                    >
                        {Object.keys(collapsedDirs).length > 0 ? <ChevronsDown size={14} /> : <ChevronsUp size={14} />}
                    </button>
                </div>
            )}

            {error && <div className="mb-4 bg-red-500/10 border border-red-500 rounded p-2 text-red-400 text-xs">❌ {error}</div>}

            <div className="flex-1 overflow-y-auto">
                <div className="space-y-1">
                    {projectTree.map((node) => (
                        <TreeItem key={node.path} node={node} />
                    ))}
                    {projectTree.length === 0 && !loading && (
                        <p className="text-gray-500 text-xs text-center py-4">No {activeTab} found</p>
                    )}
                </div>
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800 text-xs text-gray-500">
                {loading ? "⏳ Loading..." : `${projectTree.length} items shown`}
            </div>
        </div>
    );
}
