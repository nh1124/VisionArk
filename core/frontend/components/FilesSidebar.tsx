"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";

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
    nodeType: "hub" | "spoke";
    nodeName: string;
    onSyncComplete?: (files: FileInfo[]) => void;
}

export default function FilesSidebar({ nodeType, nodeName, onSyncComplete }: FilesSidebarProps) {
    const [files, setFiles] = useState<FileInfo[]>([]);
    const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
    const [activeTab, setActiveTab] = useState<"refs" | "artifacts">("refs");
    const [loading, setLoading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [error, setError] = useState<string | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const [selectedArtifact, setSelectedArtifact] = useState<{ name: string, content: string } | null>(null);

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

    // Sync files to Gemini
    const syncFiles = useCallback(async () => {
        setSyncing(true);
        setError(null);
        try {
            const response = await apiFetch(`/api/files/${nodeType}/${nodeName}/sync-gemini`, {
                method: "POST"
            });
            const data = await response.json();
            console.log(`[FilesSidebar] Synced ${data.synced_count} files to Gemini`);
            await loadFiles();
            if (onSyncComplete) {
                onSyncComplete(files);
            }
        } catch (error: any) {
            console.error("Failed to sync files:", error);
            setError("Failed to sync files to Gemini");
        } finally {
            setSyncing(false);
        }
    }, [nodeType, nodeName, loadFiles, files, onSyncComplete]);

    // Cleanup Gemini files
    const cleanupFiles = useCallback(async () => {
        try {
            await apiFetch(`/api/files/${nodeType}/${nodeName}/cleanup-gemini`, {
                method: "POST"
            });
            console.log(`[FilesSidebar] Cleaned up Gemini files for ${nodeType}/${nodeName}`);
        } catch (error) {
            console.error("Failed to cleanup Gemini files:", error);
        }
    }, [nodeType, nodeName]);

    // Load artifacts (AI-created files)
    const loadArtifacts = useCallback(async () => {
        try {
            const url = nodeType === "hub"
                ? `/api/agents/hub/artifacts`
                : `/api/agents/${nodeType}/${nodeName}/artifacts`;
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
            const url = nodeType === "hub"
                ? `/api/agents/hub/artifacts/${path}`
                : `/api/agents/${nodeType}/${nodeName}/artifacts/${path}`;
            const response = await apiFetch(url);
            const data = await response.json();
            setSelectedArtifact({ name, content: data.content || "Unable to read file" });
        } catch (error) {
            console.error("Failed to view artifact:", error);
            setSelectedArtifact({ name, content: "Error loading file" });
        }
    };

    // Load files and sync on mount
    useEffect(() => {
        loadFiles().then(() => {
            syncFiles();
        });
        loadArtifacts();

        // Cleanup on unmount
        return () => {
            cleanupFiles();
        };
    }, [nodeType, nodeName]);

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
            // Sync new file to Gemini
            await syncFiles();
            setUploadProgress(100);
            setTimeout(() => setUploadProgress(0), 1000);
        } catch (error: any) {
            console.error("Upload error:", error);
            setError(error.message || "Upload failed");
        } finally {
            setUploading(false);
        }
    };

    // Handle file drop
    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setDragActive(false);
        const droppedFiles = Array.from(e.dataTransfer.files);
        if (droppedFiles.length > 0) {
            handleUpload(droppedFiles[0]);
        }
    };

    // Handle file input change
    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            handleUpload(e.target.files[0]);
        }
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
                    {/* Sync button */}
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-sm text-gray-400">Reference Files</span>
                        <button
                            onClick={syncFiles}
                            disabled={syncing}
                            className={`text-xs px-2 py-1 ${nodeType === "hub" ? "bg-purple-600 hover:bg-purple-500" : "bg-cyan-600 hover:bg-cyan-500"} rounded disabled:opacity-50`}
                        >
                            {syncing ? "⏳" : "🔄 Sync"}
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
                                <div key={file.id} className="flex items-center justify-between bg-gray-800 p-2 rounded text-sm group">
                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                        <span className={file.has_gemini_ref ? "text-green-400" : "text-gray-400"}>
                                            {file.has_gemini_ref ? "✅" : "⏳"}
                                        </span>
                                        <span className="truncate text-gray-200" title={file.filename}>{file.filename}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-gray-500 text-xs">{formatSize(file.size_bytes)}</span>
                                        <button onClick={() => deleteFile(file.id, file.filename)} className="text-red-400 hover:text-red-300 opacity-0 group-hover:opacity-100 transition-opacity">×</button>
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
                            {syncing ? "⏳ Syncing to Gemini..." :
                                files.filter(f => f.has_gemini_ref).length === files.length && files.length > 0
                                    ? "✅ All files synced"
                                    : `${files.filter(f => f.has_gemini_ref).length}/${files.length} synced`}
                        </p>
                    </div>
                </>
            )}

            {/* Artifacts Tab Content */}
            {activeTab === "artifacts" && (
                <div className="flex-1 overflow-y-auto">
                    <p className="text-xs text-gray-400 mb-3">Files created by AI</p>
                    <div className="space-y-2">
                        {artifacts.map((artifact) => (
                            <div
                                key={artifact.path}
                                onClick={() => viewArtifact(artifact.path, artifact.name)}
                                className="flex items-center justify-between bg-gray-800 p-2 rounded text-sm hover:bg-gray-700 cursor-pointer"
                            >
                                <div className="flex items-center gap-2 flex-1 min-w-0">
                                    <span className={nodeType === "hub" ? "text-purple-400" : "text-cyan-400"}>📄</span>
                                    <span className="truncate text-gray-200" title={artifact.path}>{artifact.name}</span>
                                </div>
                                <span className="text-gray-500 text-xs">{formatSize(artifact.size)}</span>
                            </div>
                        ))}
                        {artifacts.length === 0 && (
                            <p className="text-gray-500 text-xs text-center py-4">No artifacts yet. Ask AI to create files!</p>
                        )}
                    </div>
                </div>
            )}

            {/* Artifact Viewer Modal */}
            {selectedArtifact && (
                <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={() => setSelectedArtifact(null)}>
                    <div className="bg-gray-900 border border-gray-700 rounded-lg max-w-2xl max-h-[80vh] w-full m-4 flex flex-col" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between p-4 border-b border-gray-700">
                            <h3 className="font-semibold text-cyan-400">{selectedArtifact.name}</h3>
                            <button onClick={() => setSelectedArtifact(null)} className="text-gray-400 hover:text-gray-200">✕</button>
                        </div>
                        <div className="flex-1 overflow-auto p-4">
                            <pre className="text-sm text-gray-200 whitespace-pre-wrap font-mono">{selectedArtifact.content}</pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

