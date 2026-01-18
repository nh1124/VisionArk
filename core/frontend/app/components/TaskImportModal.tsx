"use client";

import { useState, useRef } from "react";
import { apiFetch } from "@/lib/api";

interface ParsedTask {
    task_name: string;
    context: string;
    base_load_score: number;
    rule_type: string;
    due_date: string | null;
    nth_in_month: number | null;
    weekday_mon1: number | null;
    notes: string | null;
    isNewProject?: boolean;
}

interface TaskImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImportComplete: () => void;
    existingProjects: string[];
}

export default function TaskImportModal({
    isOpen,
    onClose,
    onImportComplete,
    existingProjects
}: TaskImportModalProps) {
    const [parsedTasks, setParsedTasks] = useState<ParsedTask[]>([]);
    const [autoCreateProjects, setAutoCreateProjects] = useState(true);
    const [loading, setLoading] = useState(false);
    const [status, setStatus] = useState<{ type: "success" | "error" | "info"; message: string } | null>(null);
    const [fileName, setFileName] = useState<string>("");
    const fileInputRef = useRef<HTMLInputElement>(null);

    if (!isOpen) return null;

    const newProjects = parsedTasks
        .map(t => t.context)
        .filter((project, idx, arr) =>
            project &&
            !existingProjects.includes(project) &&
            arr.indexOf(project) === idx
        );

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setFileName(file.name);
        setStatus(null);

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const text = event.target?.result as string;
                const lines = text.split(/\r?\n/).filter(line => line.trim());

                if (lines.length < 2) {
                    setStatus({ type: "error", message: "CSV file must have a header row and at least one data row" });
                    return;
                }

                const headers = parseCSVLine(lines[0]);
                const tasks: ParsedTask[] = [];

                for (let i = 1; i < lines.length; i++) {
                    const values = parseCSVLine(lines[i]);
                    const task: ParsedTask = {
                        task_name: getField(headers, values, "task_name") || `Task ${i}`,
                        context: getField(headers, values, "context") || "general",
                        base_load_score: parseFloat(getField(headers, values, "base_load_score") || "5") || 5,
                        rule_type: getField(headers, values, "rule_type") || "ONCE",
                        due_date: getField(headers, values, "due_date") || null,
                        nth_in_month: parseInt(getField(headers, values, "nth_in_month")) || null,
                        weekday_mon1: parseInt(getField(headers, values, "weekday_mon1")) || null,
                        notes: getField(headers, values, "notes") || null,
                        isNewProject: !existingProjects.includes(getField(headers, values, "context") || "general")
                    };
                    tasks.push(task);
                }

                setParsedTasks(tasks);
                setStatus({ type: "info", message: `Parsed ${tasks.length} tasks from CSV` });
            } catch (error) {
                setStatus({ type: "error", message: "Failed to parse CSV file" });
                console.error(error);
            }
        };
        reader.readAsText(file);
    };

    const parseCSVLine = (line: string): string[] => {
        const result: string[] = [];
        let current = "";
        let inQuotes = false;

        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            if (char === '"') {
                if (inQuotes && line[i + 1] === '"') {
                    current += '"';
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === "," && !inQuotes) {
                result.push(current.trim());
                current = "";
            } else {
                current += char;
            }
        }
        result.push(current.trim());
        return result;
    };

    const getField = (headers: string[], values: string[], fieldName: string): string => {
        const idx = headers.findIndex(h => h.toLowerCase() === fieldName.toLowerCase());
        return idx >= 0 ? values[idx] || "" : "";
    };

    const handleImport = async () => {
        if (parsedTasks.length === 0) {
            setStatus({ type: "error", message: "No tasks to import" });
            return;
        }

        // Get the actual file from the file input
        const file = fileInputRef.current?.files?.[0];
        if (!file) {
            setStatus({ type: "error", message: "No file selected" });
            return;
        }

        setLoading(true);
        setStatus({ type: "info", message: "Importing tasks..." });

        try {
            // Create new projects if needed
            if (autoCreateProjects && newProjects.length > 0) {
                setStatus({ type: "info", message: `Creating ${newProjects.length} new project(s)...` });

                for (const projectName of newProjects) {
                    try {
                        await apiFetch("/api/agents/project/create", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ project_name: projectName })
                        });
                    } catch (err) {
                        console.error(`Failed to create project ${projectName}:`, err);
                    }
                }
            }

            // Upload CSV file directly to server for parsing
            setStatus({ type: "info", message: "Uploading CSV file..." });

            const formData = new FormData();
            formData.append("file", file);

            const response = await apiFetch("/api/lbs/tasks/upload-csv", {
                method: "POST",
                body: formData
            });

            if (response.ok) {
                const result = await response.json();
                setStatus({ type: "success", message: result.message || "Successfully imported tasks!" });
                setTimeout(() => {
                    onImportComplete();
                    onClose();
                    setParsedTasks([]);
                    setFileName("");
                    setStatus(null);
                }, 1500);
            } else {
                const errorData = await response.json().catch(() => ({}));
                setStatus({ type: "error", message: errorData.detail || "Import failed" });
            }
        } catch (error) {
            setStatus({ type: "error", message: "Import failed" });
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleClose = () => {
        setParsedTasks([]);
        setFileName("");
        setStatus(null);
        onClose();
    };

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center"
                onClick={handleClose}
            >
                {/* Modal */}
                <div
                    className="bg-gray-900 rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Header */}
                    <div className="sticky top-0 bg-gray-900 border-b border-gray-800 p-6 flex items-center justify-between z-10">
                        <h2 className="text-2xl font-bold">Import Tasks from CSV</h2>
                        <button
                            onClick={handleClose}
                            className="text-gray-400 hover:text-white text-2xl"
                        >
                            ×
                        </button>
                    </div>

                    <div className="p-6 space-y-6">
                        {/* Status Message */}
                        {status && (
                            <div className={`p-4 rounded-lg flex items-center gap-3 ${status.type === 'success' ? 'bg-green-500/10 text-green-500 border border-green-500/20' :
                                status.type === 'error' ? 'bg-red-500/10 text-red-500 border border-red-500/20' :
                                    'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                }`}>
                                <span className="text-xl">
                                    {status.type === 'success' ? '✓' : status.type === 'error' ? '⚠️' : 'ℹ️'}
                                </span>
                                <span className="font-medium">{status.message}</span>
                            </div>
                        )}

                        {/* File Upload */}
                        <div>
                            <label className="block text-sm font-medium text-gray-400 mb-2">
                                Select CSV File
                            </label>
                            <div
                                className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center hover:border-purple-500 transition-colors cursor-pointer"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".csv"
                                    onChange={handleFileChange}
                                    className="hidden"
                                />
                                {fileName ? (
                                    <div className="text-purple-400">
                                        <span className="text-2xl">📄</span>
                                        <p className="mt-2 font-medium">{fileName}</p>
                                        <p className="text-sm text-gray-500">Click to change file</p>
                                    </div>
                                ) : (
                                    <div className="text-gray-400">
                                        <span className="text-4xl">📤</span>
                                        <p className="mt-2">Click to select a CSV file</p>
                                        <p className="text-sm text-gray-500">Required columns: task_name, context, base_load_score, rule_type</p>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Preview Table */}
                        {parsedTasks.length > 0 && (
                            <>
                                <div>
                                    <h3 className="text-lg font-medium mb-3">Preview ({parsedTasks.length} tasks)</h3>
                                    <div className="overflow-x-auto border border-gray-800 rounded-lg">
                                        <table className="w-full text-sm">
                                            <thead className="bg-gray-800">
                                                <tr>
                                                    <th className="px-4 py-2 text-left">Task Name</th>
                                                    <th className="px-4 py-2 text-left">Project</th>
                                                    <th className="px-4 py-2 text-left">Impact</th>
                                                    <th className="px-4 py-2 text-left">Type</th>
                                                    <th className="px-4 py-2 text-left">Details</th>
                                                    <th className="px-4 py-2 text-left">Due Date</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {parsedTasks.slice(0, 10).map((task, idx) => (
                                                    <tr key={idx} className="border-t border-gray-800">
                                                        <td className="px-4 py-2">{task.task_name}</td>
                                                        <td className="px-4 py-2">
                                                            {task.isNewProject ? (
                                                                <span className="text-yellow-400 flex items-center gap-1">
                                                                    <span>🆕</span> {task.context}
                                                                </span>
                                                            ) : (
                                                                task.context
                                                            )}
                                                        </td>
                                                        <td className="px-4 py-2">{task.base_load_score}</td>
                                                        <td className="px-4 py-2">{task.rule_type}</td>
                                                        <td className="px-4 py-2">
                                                            {task.rule_type === "MONTHLY_NTH_WEEKDAY" ? (
                                                                <span className="text-xs text-gray-400">
                                                                    Nth: {task.nth_in_month}, Day: {task.weekday_mon1}
                                                                </span>
                                                            ) : "-"}
                                                        </td>
                                                        <td className="px-4 py-2">{task.due_date || "-"}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                        {parsedTasks.length > 10 && (
                                            <div className="px-4 py-2 text-gray-500 text-center bg-gray-800/50">
                                                ... and {parsedTasks.length - 10} more tasks
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* New Projects Warning */}
                                {newProjects.length > 0 && (
                                    <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4">
                                        <div className="flex items-start gap-3">
                                            <span className="text-xl">⚠️</span>
                                            <div className="flex-1">
                                                <p className="font-medium text-yellow-400">
                                                    {newProjects.length} new project(s) will be created:
                                                </p>
                                                <p className="text-sm text-gray-300 mt-1">
                                                    {newProjects.join(", ")}
                                                </p>
                                                <label className="flex items-center gap-2 mt-3 cursor-pointer">
                                                    <input
                                                        type="checkbox"
                                                        checked={autoCreateProjects}
                                                        onChange={(e) => setAutoCreateProjects(e.target.checked)}
                                                        className="w-4 h-4 accent-purple-500"
                                                    />
                                                    <span className="text-sm">Automatically create missing projects</span>
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </>
                        )}

                        {/* Actions */}
                        <div className="flex gap-3 pt-4 border-t border-gray-800">
                            <button
                                type="button"
                                onClick={handleClose}
                                className="flex-1 px-6 py-3 bg-gray-800 hover:bg-gray-700 rounded-lg font-medium transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleImport}
                                disabled={loading || parsedTasks.length === 0}
                                className="flex-1 px-6 py-3 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-700 rounded-lg font-medium transition-colors"
                            >
                                {loading ? "Importing..." : `Import ${parsedTasks.length} Tasks`}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
