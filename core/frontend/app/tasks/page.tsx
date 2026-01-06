"use client";

import { useState, useEffect, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import { getSpokeColor } from "@/lib/colors";
import TaskEditPanel from "../components/TaskEditPanel";
import TaskCreateModal from "../components/TaskCreateModal";
import TaskImportModal from "../components/TaskImportModal";
import {
    Calendar,
    ChevronDown,
    ChevronRight,
    Plus,
    RefreshCw,
    CheckCircle2,
    Circle,
    Hash,
    Archive,
    Download,
    Upload,
    Star
} from "lucide-react";

interface Task {
    task_id: string;
    task_name: string;
    context: string;
    base_load_score: number;
    active: boolean;
    rule_type: string;
    due_date: string | null;
    notes: string | null;
    status?: "todo" | "done" | "skipped";
    mon?: boolean;
    tue?: boolean;
    wed?: boolean;
    thu?: boolean;
    fri?: boolean;
    sat?: boolean;
    sun?: boolean;
    interval_days?: number;
    anchor_date?: string | null;
    month_day?: number;
    nth_in_month?: number;
    weekday_mon1?: number;
    start_date?: string | null;
    end_date?: string | null;
}

export default function UnifiedTasksPage() {
    // State
    const [selectedTask, setSelectedTask] = useState<Task | null>(null);
    const [panelOpen, setPanelOpen] = useState(false);
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [isCompletedCollapsed, setIsCompletedCollapsed] = useState(false);

    // Data state
    const [tasks, setTasks] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);
    const [targetDate, setTargetDate] = useState<string>(new Date().toISOString().split('T')[0]);

    // Quick Add state
    const [quickAddName, setQuickAddName] = useState('');
    const [quickAddLoading, setQuickAddLoading] = useState(false);
    const [quickAddFocused, setQuickAddFocused] = useState(false);
    const [activeOptions, setActiveOptions] = useState(false);

    // Quick Add Options
    const [qaContext, setQaContext] = useState<string>("personal");
    const [qaLoadScore, setQaLoadScore] = useState<number>(3);
    const [qaDueDate, setQaDueDate] = useState<string>(targetDate);

    // Load data
    useEffect(() => {
        loadTasks();
    }, [targetDate]);

    const loadTasks = async () => {
        setLoading(true);
        try {
            const resp = await apiFetch(`/api/lbs/tasks?target_date=${targetDate}&active=true`);
            const data = await resp.json();
            setTasks(Array.isArray(data) ? data : []);

            // Update default context if tasks exist
            if (data.length > 0 && Array.isArray(data)) {
                setQaContext(data[0].context);
            }
        } catch (err) {
            console.error("Failed to load tasks:", err);
        } finally {
            setLoading(false);
        }
    };

    const availableSpokes = useMemo(() => {
        return Array.from(new Set(tasks.map(t => t.context)));
    }, [tasks]);

    // Split tasks
    const pendingTasks = useMemo(() => tasks.filter(t => t.status !== 'done' && t.status !== 'skipped'), [tasks]);
    const completedTasks = useMemo(() => tasks.filter(t => t.status === 'done' || t.status === 'skipped'), [tasks]);

    const stats = useMemo(() => {
        const total = tasks.length;
        const done = completedTasks.length;
        const progress = total > 0 ? Math.round((done / total) * 100) : 0;
        return { total, done, progress };
    }, [tasks, completedTasks]);

    // Handlers
    const handleMarkDone = async (taskId: string, currentStatus: string) => {
        const newStatus = currentStatus === 'done' ? 'todo' : 'done';
        try {
            const resp = await apiFetch(`/api/lbs/tasks/${taskId}/complete`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ target_date: targetDate, status: newStatus })
            });
            if (resp.ok) {
                setTasks(prev => prev.map(t => t.task_id === taskId ? { ...t, status: newStatus } : t));
            }
        } catch (err) {
            console.error("Failed to update status:", err);
        }
    };

    const handleQuickAdd = async () => {
        if (!quickAddName.trim()) return;
        setQuickAddLoading(true);
        try {
            const resp = await apiFetch('/api/lbs/tasks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_name: quickAddName.trim(),
                    context: qaContext,
                    base_load_score: qaLoadScore,
                    rule_type: 'ONCE',
                    due_date: qaDueDate,
                    notes: null
                })
            });
            if (resp.ok) {
                setQuickAddName('');
                loadTasks();
            }
        } catch (err) {
            console.error('Failed to quick-add task:', err);
        } finally {
            setQuickAddLoading(false);
        }
    };

    const changeDate = (days: number) => {
        const d = new Date(targetDate);
        d.setDate(d.getDate() + days);
        const newDate = d.toISOString().split('T')[0];
        setTargetDate(newDate);
        setQaDueDate(newDate);
    };

    const formatDateHeader = (dateStr: string) => {
        const d = new Date(dateStr);
        return d.toLocaleDateString('ja-JP', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    };

    const handleExportCSV = () => {
        const headers = ["task_name", "context", "base_load_score", "rule_type", "active", "notes"];
        const csv = [headers.join(","), ...tasks.map(t => [t.task_name, t.context, t.base_load_score, t.rule_type, t.active, t.notes].join(","))].join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "tasks_export.csv";
        a.click();
    };

    return (
        <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center">
            {/* Background Gradient/Image style (MS To-Do like) */}
            <div className="fixed inset-0 bg-gradient-to-b from-blue-900/20 to-gray-950 -z-10" />

            <div className="w-full max-w-5xl px-8 py-12 flex-1 flex flex-col min-h-0">
                {/* Header */}
                <div className="flex justify-between items-start mb-10">
                    <div>
                        <h1 className="text-4xl font-black mb-1 bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400 tracking-tight">
                            今日の結果
                        </h1>
                        <div className="flex items-center gap-3 text-gray-400 font-bold">
                            <span>{formatDateHeader(targetDate)}</span>
                            <div className="flex items-center gap-1 bg-gray-900/50 border border-gray-800 rounded-lg p-0.5">
                                <button onClick={() => changeDate(-1)} className="p-1 hover:bg-gray-800 rounded-md transition-colors">
                                    <ChevronDown className="rotate-90 w-4 h-4" />
                                </button>
                                <button onClick={() => changeDate(1)} className="p-1 hover:bg-gray-800 rounded-md transition-colors">
                                    <ChevronDown className="-rotate-90 w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => setImportModalOpen(true)} className="p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Import">
                            <Upload className="w-5 h-5" />
                        </button>
                        <button onClick={handleExportCSV} className="p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Export">
                            <Download className="w-5 h-5" />
                        </button>
                        <button onClick={loadTasks} className="p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Refresh">
                            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>

                {/* Main Task List */}
                <div className="flex-1 space-y-4 pb-32 overflow-y-auto no-scrollbar">
                    {loading && tasks.length === 0 ? (
                        <div className="text-center py-20 text-gray-600 font-bold animate-pulse uppercase tracking-widest text-sm">
                            Synchronizing Tasks...
                        </div>
                    ) : tasks.length === 0 ? (
                        <div className="bg-gray-900/30 border border-gray-800/50 border-dashed rounded-[2rem] py-32 text-center flex flex-col items-center justify-center group transition-all hover:bg-gray-900/40">
                            <div className="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                                <Plus className="w-10 h-10 text-gray-600" />
                            </div>
                            <h2 className="text-xl font-bold text-gray-500 mb-2">何をする予定ですか？</h2>
                            <p className="text-gray-600 text-sm font-medium">下の入力フォームから新しいタスクを追加しましょう。</p>
                        </div>
                    ) : (
                        <>
                            {/* Pending Tasks */}
                            <div className="space-y-2">
                                {pendingTasks.map(task => (
                                    <TaskRow
                                        key={task.task_id}
                                        task={task}
                                        onToggle={() => handleMarkDone(task.task_id, task.status || 'todo')}
                                        onClick={async () => {
                                            const resp = await apiFetch(`/api/lbs/tasks/${task.task_id}`);
                                            const fullTask = await resp.json();
                                            setSelectedTask(fullTask);
                                            setPanelOpen(true);
                                        }}
                                    />
                                ))}
                            </div>

                            {/* Completed Section */}
                            {completedTasks.length > 0 && (
                                <div className="mt-8">
                                    <button
                                        onClick={() => setIsCompletedCollapsed(!isCompletedCollapsed)}
                                        className="flex items-center gap-2 px-4 py-2 bg-gray-900/50 hover:bg-gray-900/80 rounded-xl text-gray-500 hover:text-gray-300 transition-all group mb-2"
                                    >
                                        {isCompletedCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                        <span className="text-sm font-bold uppercase tracking-wider">完了済み {completedTasks.length}</span>
                                    </button>

                                    {!isCompletedCollapsed && (
                                        <div className="space-y-2 animate-in fade-in slide-in-from-top-2 duration-300">
                                            {completedTasks.map(task => (
                                                <TaskRow
                                                    key={task.task_id}
                                                    task={task}
                                                    onToggle={() => handleMarkDone(task.task_id, task.status || 'todo')}
                                                    onClick={async () => {
                                                        const resp = await apiFetch(`/api/lbs/tasks/${task.task_id}`);
                                                        const fullTask = await resp.json();
                                                        setSelectedTask(fullTask);
                                                        setPanelOpen(true);
                                                    }}
                                                />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Bottom Quick Add (Chatbox Style) */}
                <div className="fixed bottom-0 left-0 right-0 p-8 pt-4 flex justify-center bg-gradient-to-t from-gray-950 via-gray-950/80 to-transparent pointer-events-none">
                    <div className="w-full max-w-5xl pointer-events-auto">
                        <div className={`bg-gray-900/95 backdrop-blur-xl border transition-all duration-300 ${quickAddFocused ? 'border-blue-500 shadow-2xl shadow-blue-500/10' : 'border-gray-800'} rounded-3xl overflow-hidden`}>
                            <div className="p-1 flex flex-col">
                                <div className="flex items-center gap-4 px-4 py-3">
                                    <div className="w-6 h-6 flex items-center justify-center">
                                        <Plus className={`w-6 h-6 ${quickAddFocused ? 'text-blue-500' : 'text-gray-600'} transition-colors`} />
                                    </div>
                                    <input
                                        type="text"
                                        placeholder="タスクの追加"
                                        value={quickAddName}
                                        onChange={(e) => setQuickAddName(e.target.value)}
                                        onFocus={() => { setQuickAddFocused(true); setActiveOptions(true); }}
                                        onBlur={() => {
                                            // Delay blur to allow clicking options
                                            setTimeout(() => { if (!quickAddName) { setQuickAddFocused(false); setActiveOptions(false); } }, 200);
                                        }}
                                        onKeyDown={(e) => e.key === 'Enter' && handleQuickAdd()}
                                        disabled={quickAddLoading}
                                        className="flex-1 bg-transparent border-none focus:ring-0 text-lg font-bold placeholder:text-gray-600 placeholder:font-bold py-2"
                                    />
                                    {quickAddName && (
                                        <button
                                            onClick={handleQuickAdd}
                                            disabled={quickAddLoading}
                                            className="p-2 bg-blue-600 hover:bg-blue-500 rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center"
                                        >
                                            <div className="w-5 h-5 flex items-center justify-center">
                                                {quickAddLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ChevronDown className="-rotate-90 w-5 h-5" />}
                                            </div>
                                        </button>
                                    )}
                                </div>

                                {/* Quick Add Options Bar */}
                                {(activeOptions || quickAddName) && (
                                    <div className="flex items-center gap-2 px-4 pb-3 animate-in slide-in-from-top-2">
                                        {/* Spoke/Context Selector */}
                                        <div className="relative group">
                                            <select
                                                value={qaContext}
                                                onChange={(e) => setQaContext(e.target.value)}
                                                className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                            >
                                                {availableSpokes.map(s => <option key={s} value={s}>{s}</option>)}
                                                <option value="personal">personal</option>
                                                <option value="research">research</option>
                                                <option value="NTT">NTT</option>
                                            </select>
                                            <button className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-xs font-black uppercase tracking-wider text-gray-400 group-hover:text-blue-400 transition-all">
                                                <Archive className="w-3.5 h-3.5" />
                                                {qaContext}
                                            </button>
                                        </div>

                                        {/* Workload Selector */}
                                        <div className="relative group">
                                            <select
                                                value={qaLoadScore}
                                                onChange={(e) => setQaLoadScore(parseFloat(e.target.value))}
                                                className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                            >
                                                {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n} pt</option>)}
                                            </select>
                                            <button className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-xs font-black uppercase tracking-wider text-gray-400 group-hover:text-green-400 transition-all">
                                                <Hash className="w-3.5 h-3.5" />
                                                {qaLoadScore} pt
                                            </button>
                                        </div>

                                        {/* Due Date Selector */}
                                        <div className="relative group">
                                            <input
                                                type="date"
                                                value={qaDueDate}
                                                onChange={(e) => setQaDueDate(e.target.value)}
                                                className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                            />
                                            <button className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-xs font-black uppercase tracking-wider text-gray-400 group-hover:text-amber-400 transition-all">
                                                <Calendar className="w-3.5 h-3.5" />
                                                {qaDueDate === targetDate ? "今日" : qaDueDate}
                                            </button>
                                        </div>

                                        <div className="ml-auto">
                                            <button
                                                onClick={() => setCreateModalOpen(true)}
                                                className="p-1.5 text-gray-600 hover:text-gray-400 transition-colors"
                                            >
                                                <Plus className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Modals & Panels */}
            <TaskEditPanel
                task={selectedTask}
                isOpen={panelOpen}
                onClose={() => setPanelOpen(false)}
                onSave={() => loadTasks()}
                onDelete={() => loadTasks()}
            />
            <TaskCreateModal
                isOpen={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                onTaskCreated={() => loadTasks()}
                availableSpokes={availableSpokes}
            />
            <TaskImportModal
                isOpen={importModalOpen}
                onClose={() => setImportModalOpen(false)}
                onImportComplete={() => loadTasks()}
                existingSpokes={availableSpokes}
            />
        </div>
    );
}

// Sub-component for a task row
function TaskRow({ task, onToggle, onClick }: { task: Task, onToggle: () => void, onClick: () => void }) {
    const isCompleted = task.status === 'done' || task.status === 'skipped';

    return (
        <div
            onClick={onClick}
            className={`flex items-center gap-4 p-4 bg-gray-900/60 hover:bg-gray-900 border ${isCompleted ? 'border-gray-800/40 opacity-70' : 'border-gray-800/80 shadow-sm'} rounded-2xl group transition-all cursor-pointer`}
        >
            <button
                onClick={(e) => { e.stopPropagation(); onToggle(); }}
                className={`w-6 h-6 flex items-center justify-center transition-transform active:scale-90 ${isCompleted ? 'text-blue-500' : 'text-gray-600 hover:text-gray-400'}`}
            >
                {isCompleted ? <CheckCircle2 className="w-6 h-6" /> : <Circle className="w-6 h-6" />}
            </button>
            <div className="flex-1 min-w-0">
                <h3 className={`text-base font-bold truncate tracking-tight transition-colors group-hover:text-blue-400 ${isCompleted ? 'line-through text-gray-500' : 'text-white'}`}>
                    {task.task_name}
                </h3>
                <div className="flex items-center gap-2 mt-0.5">
                    <span
                        className="text-[10px] font-black uppercase tracking-[0.15em] px-1.5 py-0.5 rounded-md bg-white/5 border border-white/5"
                        style={{ color: getSpokeColor(task.context) }}
                    >
                        {task.context}
                    </span>
                    {task.due_date && (
                        <span className="text-[10px] font-bold text-gray-600 flex items-center gap-1">
                            <Calendar className="w-3 h-3" />
                            {task.due_date}
                        </span>
                    )}
                </div>
            </div>
            <div className="flex items-center justify-center px-3 py-1 bg-gray-800/40 border border-gray-700/30 rounded-lg group-hover:border-blue-500/30 transition-colors">
                <span className="text-xs font-black text-gray-500 group-hover:text-blue-400">{task.base_load_score}</span>
            </div>
            <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                <Star className="w-4 h-4 text-gray-700 hover:text-amber-500" />
            </div>
        </div>
    );
}
