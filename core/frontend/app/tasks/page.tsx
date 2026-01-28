"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { useTaskStore } from "@/store/useTaskStore";
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
    Star,
    Hash,
    Archive,
    Download,
    Upload,
    List,
    CalendarDays,
    X
} from "lucide-react";
import { Task } from "./types";
import HeatMapCalendar from "@/components/HeatMapCalendar";
import GridCalendar from "@/components/GridCalendar";
import TimelineCalendar from "@/components/TimelineCalendar";

export default function UnifiedTasksPage() {
    const {
        tasks,
        allTasks,
        loading,
        targetDate,
        setTargetDate,
        viewMode,
        setViewMode,
        activeFilter,
        activeProject,
        fetchAllTasks,
        updateTaskStatus,
        calendarTasks,
        fetchTasks
    } = useTaskStore();

    // UI Local State
    const isMobile = useIsMobile();
    const [selectedTask, setSelectedTask] = useState<Task | null>(null);
    const [panelOpen, setPanelOpen] = useState(false);
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [isCompletedCollapsed, setIsCompletedCollapsed] = useState(true);
    const [isDayDetailsOpen, setIsDayDetailsOpen] = useState(false);
    const todayStr = new Date().toISOString().split('T')[0];
    const [dayDetailsDate, setDayDetailsDate] = useState(todayStr);

    // Refresh and context
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [refreshKey, setRefreshKey] = useState(0);
    const [allProjects, setAllProjects] = useState<string[]>([]);

    // Quick Add state
    const [quickAddName, setQuickAddName] = useState('');
    const [quickAddLoading, setQuickAddLoading] = useState(false);
    const [quickAddFocused, setQuickAddFocused] = useState(false);
    const [activeOptions, setActiveOptions] = useState(false);
    const quickAddRef = useRef<HTMLDivElement>(null);
    const qaDateRef = useRef<HTMLInputElement>(null);

    // Quick Add Options
    const [qaContext, setQaContext] = useState<string>("personal");
    const [qaLoadScore, setQaLoadScore] = useState<number>(3);
    const [qaDueDate, setQaDueDate] = useState<string>(targetDate);

    // Load data
    useEffect(() => {
        fetchTasks(targetDate);
        fetchAllTasks();
        loadAllProjects();
    }, [targetDate, fetchTasks, fetchAllTasks, activeFilter]); // fetchAllTasks is stable

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

    const availableProjects = useMemo(() => {
        const projectsFromTasks = tasks.map(t => t.context);
        const defaults = allProjects.length === 0 ? ["personal"] : [];
        return Array.from(new Set([...allProjects, ...projectsFromTasks, ...defaults])).sort();
    }, [tasks, allProjects]);

    // Split tasks with respect to activeFilter
    const displayTasks = useMemo(() => {
        const today = new Date();
        const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

        if (activeFilter === 'today') {
            return tasks.filter(t => t.due_date === todayStr);
        } else if (activeFilter === 'my-day') {
            return tasks.filter(t => t.meta_payload?.is_my_day);
        } else if (activeFilter === 'planned') {
            // "Planned" should show all future tasks from the global list
            return allTasks.filter(t => t.due_date && t.due_date >= todayStr);
        } else if (activeFilter === 'completed') {
            return allTasks.filter(t => t.status === 'completed' || t.status === 'done' || t.status === 'skipped');
        } else if (activeFilter === 'project' && activeProject) {
            return allTasks.filter(t => t.context === activeProject);
        } else if (activeFilter === 'inbox') {
            return allTasks;
        }
        return tasks;
    }, [tasks, allTasks, activeFilter, activeProject]);

    const pendingTasks = useMemo(() => {
        return displayTasks.filter(t => t.status !== 'done' && t.status !== 'skipped' && t.status !== 'completed');
    }, [displayTasks]);

    const completedTasksList = useMemo(() => {
        return displayTasks.filter(t => t.status === 'done' || t.status === 'skipped' || t.status === "completed");
    }, [displayTasks]);

    const stats = useMemo(() => {
        const total = displayTasks.length;
        const done = completedTasksList.length;
        const progress = total > 0 ? Math.round((done / total) * 100) : 0;
        return { total, done, progress };
    }, [displayTasks, completedTasksList]);

    // Handlers
    const handleMarkDone = (taskId: string, currentStatus: string) => {
        const isCompleting = currentStatus !== 'done' && currentStatus !== 'completed';
        const newStatus = isCompleting ? 'done' : 'todo';
        updateTaskStatus(taskId, newStatus, targetDate);

        if (isCompleting) {
            setIsCompletedCollapsed(false);
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
                fetchTasks(targetDate);
            }
        } catch (err) {
            console.error('Failed to quick-add task:', err);
        } finally {
            setQuickAddLoading(false);
        }
    };

    const changeDate = (days: number) => {
        const shift = viewMode === 'timeline' ? days * 7 : days;
        const d = new Date(targetDate);
        d.setDate(d.getDate() + shift);
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
            {/* Background Style */}
            <div className={`fixed inset-0 ${viewMode === 'list' ? 'bg-gradient-to-b from-blue-900/20 to-gray-950' : 'bg-gray-950'} -z-10`} />

            <div className="w-full px-4 sm:px-10 py-8 sm:py-12 flex-1 flex flex-col min-h-0 overflow-hidden transition-all duration-500">
                {/* Header */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 sm:gap-0 mb-6 sm:mb-10">
                    <div className="w-full sm:w-auto flex items-center gap-3">
                        {/* Date Header and Controls */}
                        <div className="flex flex-col items-start gap-2">
                            <h1 className={`${isMobile ? 'text-base' : 'text-lg'} font-medium text-white whitespace-nowrap min-w-[200px] sm:min-w-[300px]`}>
                                {viewMode === 'calendar'
                                    ? currentMonth.toLocaleString('en-US', { month: 'long', year: 'numeric' })
                                    : formatDateHeader(targetDate)
                                }
                            </h1>
                        </div>
                    </div>

                    {/* Action Buttons (Grouped on the right) */}
                    <div className="w-full sm:w-auto flex items-center justify-end gap-2">
                        {/* View Switcher */}
                        <div className="flex items-center gap-0.5 bg-gray-900/80 border border-gray-800 rounded-xl p-1 shadow-lg">
                            <button
                                onClick={() => setViewMode("list")}
                                className={`p-1.5 sm:p-2 rounded-lg transition-all ${viewMode === "list" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                                title="List View"
                            >
                                <List className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setViewMode("calendar")}
                                className={`p-1.5 sm:p-2 rounded-lg transition-all ${viewMode === "calendar" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                                title="Monthly Calendar"
                            >
                                <CalendarDays className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => setViewMode("timeline")}
                                className={`p-1.5 sm:p-2 rounded-lg transition-all ${viewMode === "timeline" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}
                                title="Timeline"
                            >
                                <Calendar className="w-4 h-4" />
                            </button>
                        </div>

                        <div className="flex items-center gap-2">
                            <button onClick={() => setImportModalOpen(true)} className="p-2 sm:p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg" title="Import">
                                <Upload className="w-4 h-4 sm:w-5 h-5" />
                            </button>
                            <button onClick={handleExportCSV} className="p-2 sm:p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg" title="Export">
                                <Download className="w-4 h-4 sm:w-5 h-5" />
                            </button>
                            <button onClick={() => { fetchTasks(targetDate); fetchAllTasks(); setRefreshKey(k => k + 1); }} className="p-2 sm:p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg" title="Refresh">
                                <RefreshCw className={`w-4 h-4 sm:w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Main Content Area - Unified Scrollable List */}
                <div className={`flex-1 overflow-hidden relative ${viewMode === "list" ? 'max-w-5xl mx-auto w-full' : 'w-full'}`}>
                    <div className="absolute inset-0 overflow-y-auto custom-scrollbar px-1 pb-40">
                        {viewMode === "list" ? (
                            // List View
                            <div className="space-y-6">
                                {loading && displayTasks.length === 0 ? (
                                    <div className="text-center py-20 text-gray-600 font-bold animate-pulse uppercase tracking-widest text-sm">
                                        Synchronizing Tasks...
                                    </div>
                                ) : displayTasks.length === 0 ? (
                                    <div className="bg-gray-900/30 border border-gray-800/50 border-dashed rounded-[2rem] py-32 text-center flex flex-col items-center justify-center group transition-all hover:bg-gray-900/40">
                                        <div className="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                                            <Plus className="w-10 h-10 text-gray-600" />
                                        </div>
                                        <h2 className="text-xl font-bold text-gray-500 mb-2">
                                            {activeFilter === 'today' ? "What are you planning to do Today?" :
                                                activeFilter === 'planned' ? "No future tasks planned." :
                                                    activeFilter === 'inbox' ? "Your inbox is empty." :
                                                        "Nothing found here."}
                                        </h2>
                                        <p className="text-gray-600 text-sm font-medium">Add a new task from the input below.</p>
                                    </div>
                                ) : (
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

                                        {/* Integrated Quick Add Row (Google/MS ToDo style) */}
                                        <div className={`mt-2 bg-gray-900/40 border border-gray-800/50 rounded-xl transition-all duration-300 ${quickAddFocused ? 'bg-gray-900/60 ring-1 ring-blue-500/50 shadow-lg shadow-blue-500/5' : 'hover:bg-gray-900/60'}`} ref={quickAddRef}>
                                            <div className="flex flex-col">
                                                <div className="flex items-center gap-3 px-4 py-3">
                                                    <Plus className={`w-5 h-5 ${quickAddFocused ? 'text-blue-500' : 'text-gray-500'}`} />
                                                    <input
                                                        type="text"
                                                        placeholder="Add a task"
                                                        value={quickAddName}
                                                        onChange={(e) => setQuickAddName(e.target.value)}
                                                        onFocus={() => { setQuickAddFocused(true); setActiveOptions(true); }}
                                                        onKeyDown={(e) => e.key === 'Enter' && handleQuickAdd()}
                                                        disabled={quickAddLoading}
                                                        className="flex-1 bg-transparent border-none focus:ring-0 font-semibold placeholder:text-gray-600 outline-none text-sm"
                                                    />
                                                    {quickAddName && (
                                                        <button
                                                            onClick={handleQuickAdd}
                                                            disabled={quickAddLoading}
                                                            className="p-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg transition-all shadow-lg active:scale-95"
                                                        >
                                                            {quickAddLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ChevronDown className="-rotate-90 w-3.5 h-3.5" />}
                                                        </button>
                                                    )}
                                                </div>

                                                {/* Expanded Options */}
                                                {(activeOptions || quickAddName) && quickAddFocused && (
                                                    <div className="px-4 pb-3 pt-1 flex items-center gap-2 animate-in slide-in-from-top-1 duration-200 border-t border-gray-800/30 mt-1">
                                                        <div className="relative group">
                                                            <select
                                                                value={qaContext}
                                                                onChange={(e) => setQaContext(e.target.value)}
                                                                className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                                            >
                                                                {availableProjects.map(s => <option key={s} value={s}>{s}</option>)}
                                                            </select>
                                                            <button className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-blue-400 transition-all">
                                                                <Archive className="w-3 h-3" />
                                                                {qaContext}
                                                            </button>
                                                        </div>

                                                        <div className="relative group">
                                                            <select
                                                                value={qaLoadScore}
                                                                onChange={(e) => setQaLoadScore(parseFloat(e.target.value))}
                                                                className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                                            >
                                                                {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n}</option>)}
                                                            </select>
                                                            <button className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-green-400 transition-all">
                                                                <Hash className="w-3 h-3" />
                                                                {qaLoadScore}
                                                            </button>
                                                        </div>

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
                                                                className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-amber-400 transition-all"
                                                            >
                                                                <Calendar className="w-3 h-3" />
                                                                {qaDueDate === targetDate ? "Today" : qaDueDate}
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Completed Section Inline */}
                                        {completedTasksList.length > 0 && (
                                            <div className="mt-6">
                                                <button
                                                    onClick={() => setIsCompletedCollapsed(!isCompletedCollapsed)}
                                                    className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/50 hover:bg-gray-900/80 rounded-lg text-gray-500 hover:text-gray-300 transition-all group mb-2"
                                                >
                                                    {isCompletedCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                                    <span className="text-xs font-bold uppercase tracking-wider">Completed {completedTasksList.length}</span>
                                                </button>

                                                {!isCompletedCollapsed && (
                                                    <div className="space-y-1 animate-in fade-in slide-in-from-top-2 duration-300">
                                                        {completedTasksList.map(task => (
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
                                    </div>
                                )}
                            </div>
                        ) : viewMode === "calendar" ? (
                            <div className="flex gap-6 h-full min-h-0">
                                <div className="flex-1 min-w-0">
                                    <GridCalendar
                                        month={currentMonth}
                                        onDayClick={(date) => {
                                            setTargetDate(date);
                                            setDayDetailsDate(date);
                                            setIsDayDetailsOpen(true);
                                        }}
                                        includeCompleted={true}
                                    />
                                </div>

                                {/* Calendar Day Details Panel */}
                                {isDayDetailsOpen && (
                                    <div className="w-[350px] bg-gray-900/60 border border-gray-800 rounded-2xl flex flex-col min-h-0 animate-in slide-in-from-right-4 duration-300 shadow-2xl backdrop-blur-xl">
                                        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
                                            <div>
                                                <h3 className="text-sm font-black uppercase tracking-widest text-blue-400">Day Details</h3>
                                                <p className="text-xs text-gray-500 font-bold">{formatDateHeader(dayDetailsDate)}</p>
                                            </div>
                                            <button
                                                onClick={() => setIsDayDetailsOpen(false)}
                                                className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-500 hover:text-white transition-all"
                                            >
                                                <X className="w-4 h-4" />
                                            </button>
                                        </div>

                                        <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
                                            {calendarTasks.filter(t => t.due_date === dayDetailsDate).length === 0 ? (
                                                <div className="h-full flex flex-col items-center justify-center text-center p-8">
                                                    <div className="w-12 h-12 bg-gray-800/50 rounded-full flex items-center justify-center mb-4">
                                                        <Plus className="w-6 h-6 text-gray-600" />
                                                    </div>
                                                    <p className="text-xs font-bold text-gray-600 uppercase tracking-widest">No tasks for this day</p>
                                                </div>
                                            ) : (
                                                calendarTasks.filter(t => t.due_date === dayDetailsDate).map(task => (
                                                    <div
                                                        key={task.task_id}
                                                        onClick={async () => {
                                                            const resp = await apiFetch(`/api/lbs/tasks/${task.task_id}`);
                                                            const fullTask = await resp.json();
                                                            setSelectedTask(fullTask);
                                                            setPanelOpen(true);
                                                        }}
                                                        className="group bg-gray-950/40 border border-gray-800/50 rounded-xl p-3 hover:bg-gray-900 hover:border-blue-500/30 transition-all cursor-pointer"
                                                    >
                                                        <div className="flex items-center gap-3 mb-1">
                                                            <div className={task.status === 'done' || task.status === 'completed' ? 'text-blue-500' : 'text-gray-600'}>
                                                                {task.status === 'done' || task.status === 'completed' ? <CheckCircle2 className="w-4 h-4" /> : <Circle className="w-4 h-4" />}
                                                            </div>
                                                            <span className={`text-sm font-bold truncate ${task.status === 'done' || task.status === 'completed' ? 'line-through text-gray-600' : 'text-gray-200 group-hover:text-blue-400'}`}>
                                                                {task.task_name}
                                                            </span>
                                                        </div>
                                                        <div className="flex items-center gap-2 pl-7">
                                                            <span className="text-[10px] font-black uppercase tracking-tighter text-gray-600" style={{ color: getSpokeColor(task.context) }}>
                                                                {task.context}
                                                            </span>
                                                            <span className="text-[10px] font-bold text-gray-700 bg-gray-900 rounded px-1.5 py-0.5">
                                                                Impact: {task.base_load_score}
                                                            </span>
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>

                                        <div className="p-3 border-t border-gray-800">
                                            <button
                                                onClick={() => {
                                                    setQaDueDate(dayDetailsDate);
                                                    setCreateModalOpen(true);
                                                }}
                                                className="w-full py-2.5 bg-blue-600/10 hover:bg-blue-600 text-blue-400 hover:text-white border border-blue-600/20 rounded-xl text-xs font-black uppercase tracking-widest transition-all shadow-lg shadow-blue-500/5 active:scale-95"
                                            >
                                                Add Task
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <TimelineCalendar
                                targetDate={targetDate}
                                onTaskClick={(task) => {
                                    setSelectedTask(task);
                                    setPanelOpen(true);
                                }}
                                refreshKey={refreshKey}
                            />
                        )}
                    </div>
                </div>
            </div>

            {/* Modals & Panels */}
            <TaskEditPanel
                task={selectedTask}
                isOpen={panelOpen}
                onClose={() => setPanelOpen(false)}
                onSave={() => fetchTasks(targetDate)}
                onDelete={() => fetchTasks(targetDate)}
            />
            <TaskCreateModal
                isOpen={createModalOpen}
                onClose={() => setCreateModalOpen(false)}
                onTaskCreated={() => fetchTasks(targetDate)}
                availableProjects={availableProjects}
            />
            <TaskImportModal
                isOpen={importModalOpen}
                onClose={() => setImportModalOpen(false)}
                onImportComplete={() => fetchTasks(targetDate)}
                existingProjects={availableProjects}
            />
        </div>
    );
}

// Sub-component for a task row
function TaskRow({ task, onToggle, onClick, isMobile }: { task: Task, onToggle: () => void, onClick: () => void, isMobile: boolean }) {
    const isCompleted = task.status === 'done' || task.status === 'skipped' || task.status === 'completed';
    const { toggleMyDay } = useTaskStore();
    const isMyDay = task.meta_payload?.is_my_day;

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

            <button
                onClick={(e) => { e.stopPropagation(); toggleMyDay(task); }}
                className={`w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 flex items-center justify-center transition-transform active:scale-90 ${isMyDay ? 'text-amber-400' : 'text-gray-700 hover:text-gray-500'}`}
            >
                <Star size={isMobile ? 14 : 16} fill={isMyDay ? "currentColor" : "none"} />
            </button>
        </div>
    );
}
