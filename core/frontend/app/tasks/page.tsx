"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { useIsMobile } from "@/hooks/useIsMobile";
import { getSpokeColor } from "@/lib/colors";
import TaskEditPanel from "../components/TaskEditPanel";
import TaskCreateModal from "../components/TaskCreateModal";
import TaskImportModal from "../components/TaskImportModal";
import {
    Calendar,
    ChevronDown,
    ChevronRight,
    ChevronLeft,
    Plus,
    RefreshCw,
    CheckCircle2,
    Circle,
    Hash,
    Archive,
    Download,
    Upload,
    Star,
    List,
    CalendarDays
} from "lucide-react";
import HeatMapCalendar from "@/components/HeatMapCalendar";

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
    const isMobile = useIsMobile();
    const [selectedTask, setSelectedTask] = useState<Task | null>(null);
    const [panelOpen, setPanelOpen] = useState(false);
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [isCompletedCollapsed, setIsCompletedCollapsed] = useState(false);

    // View mode state
    const [viewMode, setViewMode] = useState<"list" | "calendar">("list");
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [refreshKey, setRefreshKey] = useState(0);

    // Data state
    const [tasks, setTasks] = useState<Task[]>([]);
    const [loading, setLoading] = useState(true);
    const [targetDate, setTargetDate] = useState<string>(new Date().toISOString().split('T')[0]);

    // Quick Add state
    const [quickAddName, setQuickAddName] = useState('');
    const [quickAddLoading, setQuickAddLoading] = useState(false);
    const [quickAddFocused, setQuickAddFocused] = useState(false);
    const [activeOptions, setActiveOptions] = useState(false);
    const quickAddRef = useRef<HTMLDivElement>(null);
    const qaDateRef = useRef<HTMLInputElement>(null);

    // Projects list
    const [allProjects, setAllProjects] = useState<string[]>([]);

    // Quick Add Options
    const [qaContext, setQaContext] = useState<string>("personal");
    const [qaLoadScore, setQaLoadScore] = useState<number>(3);
    const [qaDueDate, setQaDueDate] = useState<string>(targetDate);

    // Load data
    useEffect(() => {
        loadTasks();
        loadAllProjects();
    }, [targetDate]);

    // Handle clicks outside quick add to hide options
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (quickAddRef.current && !quickAddRef.current.contains(event.target as Node)) {
                setActiveOptions(false);
                setQuickAddFocused(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const loadAllProjects = async () => {
        try {
            const response = await apiFetch("/api/agents/project/list");
            const data = await response.json();
            if (data && data.projects && Array.isArray(data.projects)) {
                setAllProjects(data.projects.map((s: any) => s.name));
            }
        } catch (err) {
            console.error("Failed to load projects:", err);
        }
    };

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

    const availableProjects = useMemo(() => {
        const projectsFromTasks = tasks.map(t => t.context);
        // Only include "personal" if no projects are found, otherwise rely on actual project list
        const defaults = allProjects.length === 0 ? ["personal"] : [];
        return Array.from(new Set([...allProjects, ...projectsFromTasks, ...defaults])).sort();
    }, [tasks, allProjects]);

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
        return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
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

            <div className="w-full max-w-5xl px-4 sm:px-8 py-8 sm:py-12 flex-1 flex flex-col min-h-0">
                {/* Header */}
                {/* Header */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 sm:gap-0 mb-6 sm:mb-10">
                    <div className={`${isMobile ? 'hidden' : 'block'}`}>
                        <h1 className="text-3xl font-bold mb-1 text-white tracking-tight">
                            Daily Results
                        </h1>
                    </div>

                    <div className="w-full sm:w-auto flex flex-col sm:flex-row items-center gap-3">
                        {/* Date Controls */}
                        <div className="w-full sm:w-auto flex items-center justify-between sm:justify-start gap-3 bg-gray-900/40 sm:bg-transparent p-2 sm:p-0 rounded-xl sm:rounded-none border border-gray-800/50 sm:border-none">
                            <div className="flex items-center gap-3 text-gray-400 font-bold">
                                <span className={isMobile ? 'text-sm' : 'text-base'}>{formatDateHeader(targetDate)}</span>
                                <div className="flex items-center gap-1 bg-gray-900/50 border border-gray-800 rounded-lg p-0.5">
                                    <button onClick={() => changeDate(-1)} className="p-1 hover:bg-gray-800 rounded-md transition-colors">
                                        <ChevronLeft className="w-4 h-4" />
                                    </button>
                                    <button onClick={() => changeDate(1)} className="p-1 hover:bg-gray-800 rounded-md transition-colors">
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="w-full sm:w-auto flex items-center justify-center sm:justify-start gap-2">
                            {/* View Switcher */}
                            <div className="flex items-center gap-0.5 bg-gray-900/80 border border-gray-800 rounded-xl p-1">
                                <button
                                    onClick={() => setViewMode("list")}
                                    className={`p-1.5 sm:p-2 rounded-lg transition-all ${viewMode === "list" ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                                    title="List View"
                                >
                                    <List className="w-4 h-4" />
                                </button>
                                <button
                                    onClick={() => setViewMode("calendar")}
                                    className={`p-1.5 sm:p-2 rounded-lg transition-all ${viewMode === "calendar" ? 'bg-blue-600 text-white' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                                    title="Calendar View"
                                >
                                    <CalendarDays className="w-4 h-4" />
                                </button>
                            </div>

                            <div className="flex items-center gap-2">
                                <button onClick={() => setImportModalOpen(true)} className="p-2 sm:p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Import">
                                    <Upload className="w-4 h-4 sm:w-5 h-5" />
                                </button>
                                <button onClick={handleExportCSV} className="p-2 sm:p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Export">
                                    <Download className="w-4 h-4 sm:w-5 h-5" />
                                </button>
                                <button onClick={() => { loadTasks(); setRefreshKey(k => k + 1); }} className="p-2 sm:p-3 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white" title="Refresh">
                                    <RefreshCw className={`w-4 h-4 sm:w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Main Content Area */}
                <div className={`flex-1 space-y-4 overflow-y-auto no-scrollbar ${viewMode === "list" ? 'pb-32' : 'pb-8'}`}>
                    {viewMode === "list" ? (
                        // List View
                        <>
                            {loading && tasks.length === 0 ? (
                                <div className="text-center py-20 text-gray-600 font-bold animate-pulse uppercase tracking-widest text-sm">
                                    Synchronizing Tasks...
                                </div>
                            ) : tasks.length === 0 ? (
                                <div className="bg-gray-900/30 border border-gray-800/50 border-dashed rounded-[2rem] py-32 text-center flex flex-col items-center justify-center group transition-all hover:bg-gray-900/40">
                                    <div className="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                                        <Plus className="w-10 h-10 text-gray-600" />
                                    </div>
                                    <h2 className="text-xl font-bold text-gray-500 mb-2">What are you planning to do?</h2>
                                    <p className="text-gray-600 text-sm font-medium">Add a new task from the input below.</p>
                                </div>
                            ) : (
                                <>
                                    {/* Pending Tasks */}
                                    <div className="space-y-1">
                                        {pendingTasks.map(task => (
                                            <TaskRow
                                                key={task.task_id}
                                                task={task}
                                                isMobile={!!isMobile}
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
                                        <div className="mt-6">
                                            <button
                                                onClick={() => setIsCompletedCollapsed(!isCompletedCollapsed)}
                                                className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/50 hover:bg-gray-900/80 rounded-lg text-gray-500 hover:text-gray-300 transition-all group mb-2"
                                            >
                                                {isCompletedCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                                <span className="text-xs font-bold uppercase tracking-wider">Completed {completedTasks.length}</span>
                                            </button>

                                            {!isCompletedCollapsed && (
                                                <div className="space-y-1 animate-in fade-in slide-in-from-top-2 duration-300">
                                                    {completedTasks.map(task => (
                                                        <TaskRow
                                                            key={task.task_id}
                                                            task={task}
                                                            isMobile={!!isMobile}
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
                        </>
                    ) : (
                        // Calendar View
                        <div className="space-y-6">
                            {/* Month Navigation */}
                            <div className="flex items-center justify-between">
                                <h2 className="text-lg font-bold text-gray-300 tracking-tight">
                                    {currentMonth.toLocaleString('en-US', { month: 'long', year: 'numeric' })}
                                </h2>
                                <div className="flex items-center gap-1 bg-gray-900/50 border border-gray-800 rounded-xl p-1">
                                    <button
                                        onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))}
                                        className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-500 hover:text-white"
                                    >
                                        <ChevronLeft className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => setCurrentMonth(new Date())}
                                        className="px-3 py-1 text-xs font-bold text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
                                    >
                                        Today
                                    </button>
                                    <button
                                        onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))}
                                        className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-500 hover:text-white"
                                    >
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>

                            {/* Calendar Component */}
                            <HeatMapCalendar
                                month={currentMonth}
                                onDayClick={(date) => {
                                    setTargetDate(date);
                                    setQaDueDate(date);
                                    setViewMode("list");
                                }}
                                refreshKey={refreshKey}
                                includeCompleted={true}
                            />
                        </div>
                    )}
                </div>

                {/* Bottom Quick Add (Floating Chatbox Style) - Only show in list view */}
                {viewMode === "list" && (
                    <div className="absolute bottom-6 left-4 right-4 sm:left-8 sm:right-8 flex justify-center pointer-events-none">
                        <div className="w-full max-w-5xl pointer-events-auto relative" ref={quickAddRef}>
                            {/* Quick Add Options Bar - Floating Above */}
                            {(activeOptions || quickAddName) && (
                                <div className="absolute bottom-full left-0 mb-3 flex items-center gap-2 px-4 py-2 bg-gray-900/90 backdrop-blur-xl border border-gray-800 rounded-2xl animate-in slide-in-from-bottom-2 duration-300 shadow-2xl z-20">
                                    {/* Project/Context Selector */}
                                    <div className="relative group">
                                        <select
                                            value={qaContext}
                                            onChange={(e) => setQaContext(e.target.value)}
                                            className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                        >
                                            {availableProjects.map(s => <option key={s} value={s}>{s}</option>)}
                                        </select>
                                        <button className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-[10px] font-black uppercase tracking-wider text-gray-400 group-hover:text-blue-400 transition-all">
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
                                            {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n}</option>)}
                                        </select>
                                        <button className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-[10px] font-black uppercase tracking-wider text-gray-400 group-hover:text-green-400 transition-all">
                                            <Hash className="w-3.5 h-3.5" />
                                            Impact: {qaLoadScore}
                                        </button>
                                    </div>

                                    {/* Due Date Selector */}
                                    <div className="relative group">
                                        <input
                                            ref={qaDateRef}
                                            type="date"
                                            value={qaDueDate}
                                            onChange={(e) => setQaDueDate(e.target.value)}
                                            className="absolute inset-0 opacity-0 pointer-events-none"
                                        />
                                        <button
                                            onClick={() => qaDateRef.current?.showPicker()}
                                            className="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 border border-gray-700/50 rounded-xl text-[10px] font-black uppercase tracking-wider text-gray-400 group-hover:text-amber-400 transition-all"
                                        >
                                            <Calendar className="w-3.5 h-3.5" />
                                            {qaDueDate === targetDate ? "Today" : qaDueDate}
                                        </button>
                                    </div>

                                    <div className="ml-4 border-l border-gray-800 pl-2">
                                        <button
                                            onClick={() => setCreateModalOpen(true)}
                                            className="p-1.5 text-gray-600 hover:text-gray-400 transition-colors"
                                            title="Full Editor"
                                        >
                                            <Plus className="w-4 h-4" />
                                        </button>
                                    </div>
                                </div>
                            )}

                            <div className={`bg-gray-900/95 backdrop-blur-xl border border-gray-800 rounded-2xl sm:rounded-3xl overflow-hidden transition-all duration-300 ${quickAddFocused ? 'bg-gray-900/98 shadow-xl shadow-black/40' : ''}`}>
                                <div className="p-0.5 sm:p-1 flex flex-col">
                                    <div className={`flex items-center gap-2 sm:gap-4 px-3 sm:px-4 ${isMobile ? 'py-1.5' : 'py-3'}`}>
                                        <div className="w-5 h-5 sm:w-6 sm:h-6 flex items-center justify-center">
                                            <Plus className={`${isMobile ? 'w-5 h-5' : 'w-6 h-6'} ${quickAddFocused ? 'text-blue-500' : 'text-gray-600'} transition-colors`} />
                                        </div>
                                        <input
                                            type="text"
                                            placeholder="Add a task"
                                            value={quickAddName}
                                            onChange={(e) => setQuickAddName(e.target.value)}
                                            onFocus={() => { setQuickAddFocused(true); setActiveOptions(true); }}
                                            onKeyDown={(e) => e.key === 'Enter' && handleQuickAdd()}
                                            disabled={quickAddLoading}
                                            className={`flex-1 bg-transparent border-none focus:ring-0 font-bold placeholder:text-gray-600 placeholder:font-bold outline-none ${isMobile ? 'text-sm py-1' : 'text-lg py-2'}`}
                                        />
                                        {quickAddName && (
                                            <button
                                                onClick={handleQuickAdd}
                                                disabled={quickAddLoading}
                                                className={`${isMobile ? 'p-1.5' : 'p-2'} bg-blue-600 hover:bg-blue-500 rounded-lg sm:rounded-xl transition-all shadow-lg active:scale-95 flex items-center justify-center`}
                                            >
                                                <div className="w-4 h-4 sm:w-5 sm:h-5 flex items-center justify-center">
                                                    {quickAddLoading ? <RefreshCw className="w-3.5 h-3.5 sm:w-4 sm:h-4 animate-spin" /> : <ChevronDown className="-rotate-90 w-4 h-4 sm:w-5 sm:h-5" />}
                                                </div>
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}
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
                availableProjects={availableProjects}
            />
            <TaskImportModal
                isOpen={importModalOpen}
                onClose={() => setImportModalOpen(false)}
                onImportComplete={() => loadTasks()}
                existingProjects={availableProjects}
            />
        </div>
    );
}

// Sub-component for a task row
function TaskRow({ task, onToggle, onClick, isMobile }: { task: Task, onToggle: () => void, onClick: () => void, isMobile: boolean }) {
    const isCompleted = task.status === 'done' || task.status === 'skipped';

    return (
        <div
            onClick={onClick}
            className={`flex items-center gap-2 sm:gap-3 px-2 sm:px-3 py-2 sm:py-2.5 bg-gray-900/40 hover:bg-gray-900/80 border-b border-gray-800/10 sm:border ${isCompleted ? 'opacity-60' : ''} sm:rounded-xl group transition-all cursor-pointer`}
        >
            <button
                onClick={(e) => { e.stopPropagation(); onToggle(); }}
                className={`w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 flex items-center justify-center transition-transform active:scale-90 ${isCompleted ? 'text-blue-500' : 'text-gray-600 hover:text-gray-400'}`}
            >
                {isCompleted ? <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5" /> : <Circle className="w-4 h-4 sm:w-5 sm:h-5" />}
            </button>
            <h3 className={`flex-1 min-w-0 font-semibold truncate transition-colors group-hover:text-blue-400 ${isCompleted ? 'line-through text-gray-500' : 'text-white'} ${isMobile ? 'text-[13px]' : 'text-sm'}`}>
                {task.task_name}
            </h3>
            <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 ml-auto">
                <span
                    className="text-[8px] sm:text-[9px] font-black uppercase tracking-wider px-1.2 sm:px-1.5 py-0.5 rounded bg-white/5"
                    style={{ color: getSpokeColor(task.context) }}
                >
                    {task.context}
                </span>
                {task.due_date && (
                    <span className="text-[8px] sm:text-[9px] font-semibold text-gray-600 flex items-center gap-1">
                        <Calendar className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                        <span className="whitespace-nowrap">{isMobile ? task.due_date.split('-').slice(1).join('/') : task.due_date}</span>
                    </span>
                )}
                <span className="text-[8px] sm:text-[9px] font-bold text-gray-600 px-1 sm:px-1.5 py-0.5 bg-gray-800/40 rounded min-w-[1.2rem] text-center">
                    {task.base_load_score}
                </span>
            </div>
            {!isMobile && <Star className="w-4 h-4 flex-shrink-0 text-gray-700 hover:text-amber-500 opacity-0 group-hover:opacity-100 transition-opacity" />}
        </div>
    );
}
