"use client";

import { useState, useEffect } from "react";

interface FileUploadProps {
    spokeName: string;
}

export default function FileUpload({ spokeName }: FileUploadProps) {
    const [uploading, setUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState(0);
    const [files, setFiles] = useState<any>({ refs: [], artifacts: [] });
    const [dragActive, setDragActive] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Load files on mount
    useEffect(() => {
        loadFiles();
    }, [spokeName]);

    const loadFiles = async () => {
        try {
            const response = await fetch(`/api/spokes/${spokeName}/files`);
            const data = await response.json();
            setFiles(data);
        } catch (error) {
            console.error("Failed to load files:", error);
        }
    };

    // Handle file upload with progress
    const handleUpload = async (file: File) => {
        setUploading(true);
        setUploadProgress(0);
        setError(null);

        const formData = new FormData();
        formData.append("file", file);

        try {
            const xhr = new XMLHttpRequest();

            // Track upload progress
            xhr.upload.addEventListener("progress", (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    setUploadProgress(percent);
                }
            });

            // Handle completion
            await new Promise((resolve, reject) => {
                xhr.addEventListener("load", () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(xhr.response);
                    } else {
                        const error = JSON.parse(xhr.responseText);
                        reject(new Error(error.detail || "Upload failed"));
                    }
                });
                xhr.addEventListener("error", () => reject(new Error("Network error")));
                xhr.addEventListener("abort", () => reject(new Error("Upload aborted")));

                xhr.open("POST", `/api/spokes/${spokeName}/upload`);
                xhr.send(formData);
            });

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
    const deleteFile = async (directory: string, filename: string) => {
        if (!confirm(`Delete ${filename}?`)) return;

        try {
            const response = await fetch(
                `/api/spokes/${spokeName}/files/${directory}/${filename}`,
                { method: "DELETE" }
            );

            if (response.ok) {
                await loadFiles();
            }
        } catch (error) {
            console.error("Delete error:", error);
        }
    };

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-lg font-semibold mb-3 text-cyan-400">📎 Files</h3>

            {/* Upload Zone */}
            <div
                onDrop={handleDrop}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${dragActive ? "border-cyan-500 bg-cyan-500/10" : "border-gray-700 hover:border-gray-600"
                    }`}
            >
                <input
                    type="file"
                    id={`file-upload-${spokeName}`}
                    className="hidden"
                    onChange={handleFileInput}
                    disabled={uploading}
                />
                <label htmlFor={`file-upload-${spokeName}`} className="cursor-pointer">
                    <div className="text-gray-400">
                        {uploading ? (
                            <>
                                <p>⏳ Uploading... {uploadProgress}%</p>
                                <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                                    <div
                                        className="bg-cyan-500 h-2 rounded-full transition-all"
                                        style={{ width: `${uploadProgress}%` }}
                                    />
                                </div>
                            </>
                        ) : (
                            <>
                                <p>📤 Drop files here or click to upload</p>
                                <p className="text-xs mt-1">PDFs, images, documents (max 100MB)</p>
                            </>
                        )}
                    </div>
                </label>
            </div>

            {/* Error Message */}
            {error && (
                <div className="mt-2 bg-red-500/10 border border-red-500 rounded p-3 text-red-400 text-sm">
                    ❌ {error}
                </div>
            )}

            {/* File Lists */}
            <div className="mt-4 grid grid-cols-2 gap-4">
                {/* Refs */}
                <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">
                        📚 References ({files.refs.length})
                    </h4>
                    <div className="space-y-1">
                        {files.refs.map((file: any) => (
                            <div
                                key={file.name}
                                className="flex items-center justify-between bg-gray-800 p-2 rounded text-sm"
                            >
                                <a
                                    href={`/api/spokes/${spokeName}/files/refs/${file.name}`}
                                    className="text-cyan-400 hover:underline truncate flex-1"
                                    target="_blank"
                                >
                                    {file.name}
                                </a>
                                <button
                                    onClick={() => deleteFile("refs", file.name)}
                                    className="text-red-400 hover:text-red-300 ml-2"
                                >
                                    ×
                                </button>
                            </div>
                        ))}
                        {files.refs.length === 0 && (
                            <p className="text-gray-500 text-xs">No files</p>
                        )}
                    </div>
                </div>

                {/* Artifacts */}
                <div>
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">
                        🎨 Artifacts ({files.artifacts.length})
                    </h4>
                    <div className="space-y-1">
                        {files.artifacts.map((file: any) => (
                            <div
                                key={file.name}
                                className="flex items-center justify-between bg-gray-800 p-2 rounded text-sm"
                            >
                                <a
                                    href={`/api/spokes/${spokeName}/files/artifacts/${file.name}`}
                                    className="text-cyan-400 hover:underline truncate flex-1"
                                    target="_blank"
                                >
                                    {file.name}
                                </a>
                                <button
                                    onClick={() => deleteFile("artifacts", file.name)}
                                    className="text-red-400 hover:text-red-300 ml-2"
                                >
                                    ×
                                </button>
                            </div>
                        ))}
                        {files.artifacts.length === 0 && (
                            <p className="text-gray-500 text-xs">No files</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
