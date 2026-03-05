"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { getLocalDateString } from "@/lib/dateUtils";
import { useTaskStore } from "@/store/useTaskStore";
import { useIsMobile } from "@/hooks/useIsMobile";
import { Task } from "../types";

export function useTasksLogic() {
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
        overdueTasks,
        fetchTasks,
        fetchOverdueTasks,
        fetchMonthTasks,
        toggleMyDay,
        setActiveFilter
    } = useTaskStore();

    // UI Local State
    const isMobile = useIsMobile();
    const [selectedTask, setSelectedTask] = useState<Task | null>(null);
    const [panelOpen, setPanelOpen] = useState(false);
    const [createModalOpen, setCreateModalOpen] = useState(false);
    const [importModalOpen, setImportModalOpen] = useState(false);
    const [isCompletedCollapsed, setIsCompletedCollapsed] = useState(true);
    const [isDayDetailsOpen, setIsDayDetailsOpen] = useState(false);
    const todayStr = useMemo(() => getLocalDateString(), []);
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

    // Load target date specific data
    useEffect(() => {
        fetchTasks(targetDate);
    }, [targetDate, fetchTasks]);

    // Initial load for global data
    useEffect(() => {
        fetchAllTasks();
        fetchOverdueTasks();
        loadAllProjects();

        // Populate calendarTasks for Planned view
        const start = new Date();
        const end = new Date();
        end.setDate(start.getDate() + 30); // Fetch next 30 days for Planned
        fetchMonthTasks(
            getLocalDateString(start),
            getLocalDateString(end)
        );
    }, [fetchAllTasks, fetchOverdueTasks, fetchMonthTasks]);

    const availableProjects = useMemo(() => {
        const projectsFromTasks = tasks.map(t => t.context);
        const defaults = allProjects.length === 0 ? ["personal"] : [];
        return Array.from(new Set([...allProjects, ...projectsFromTasks, ...defaults])).sort();
    }, [tasks, allProjects]);

    // Split tasks with respect to activeFilter
    const displayTasks = useMemo(() => {
        const todayStr = getLocalDateString();

        if (activeFilter === 'today') {
            return tasks.filter(t => t.due_date === todayStr);
        } else if (activeFilter === 'my-day') {
            return allTasks.filter(t => t.meta_payload?.is_my_day);
        } else if (activeFilter === 'overdue') {
            return overdueTasks.filter(t => t.status !== 'done' && t.status !== 'skipped' && t.status !== 'completed');
        } else if (activeFilter === 'planned') {
            return calendarTasks.filter(t => t.due_date && t.due_date > todayStr);
        } else if (activeFilter === 'completed') {
            return allTasks.filter(t => t.status === 'completed' || t.status === 'done' || t.status === 'skipped');
        } else if (activeFilter === 'project' && activeProject) {
            return allTasks.filter(t => t.context === activeProject);
        } else if (activeFilter === 'inbox') {
            return allTasks;
        }
        return tasks;
    }, [tasks, allTasks, calendarTasks, overdueTasks, activeFilter, activeProject]);

    const groupedTasks = useMemo(() => {
        if (activeFilter !== 'planned' && activeFilter !== 'overdue') return null;

        const groups: { [key: string]: Task[] } = {};
        displayTasks.forEach(t => {
            const d = t.due_date || 'No Date';
            if (!groups[d]) groups[d] = [];
            groups[d].push(t);
        });

        return Object.keys(groups).sort().map(date => ({
            date,
            tasks: groups[date]
        }));
    }, [displayTasks, activeFilter]);

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
    const handleMarkDone = (taskId: string, currentStatus: string, date?: string) => {
        const isCompleting = currentStatus !== 'done' && currentStatus !== 'completed';
        const newStatus = isCompleting ? 'done' : 'todo';
        updateTaskStatus(taskId, newStatus, date || targetDate);

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
        const newDate = getLocalDateString(d);
        setTargetDate(newDate);
        setQaDueDate(newDate);
    };

    const handlePrev = () => {
        if (viewMode === 'calendar') {
            setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1));
        } else if (viewMode === 'timeline') {
            changeDate(-1);
        }
    };

    const handleNext = () => {
        if (viewMode === 'calendar') {
            setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1));
        } else if (viewMode === 'timeline') {
            changeDate(1);
        }
    };

    const handleToday = () => {
        const today = new Date();
        if (viewMode === 'calendar') {
            setCurrentMonth(new Date(today.getFullYear(), today.getMonth(), 1));
        } else {
            const todayStr = getLocalDateString(today);
            setTargetDate(todayStr);
            setQaDueDate(todayStr);
        }
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

    const handleRefresh = () => {
        fetchTasks(targetDate);
        fetchAllTasks();
        setRefreshKey(k => k + 1);
    };

    const handleRowClick = async (task: Task) => {
        try {
            const dateParam = task.due_date ? `?target_date=${task.due_date}` : (targetDate ? `?target_date=${targetDate}` : '');
            const resp = await apiFetch(`/api/lbs/tasks/${task.task_id}${dateParam}`);
            if (resp.ok) {
                const fullTask = await resp.json();
                setSelectedTask({ ...fullTask, due_date: task.due_date || targetDate });
                setPanelOpen(true);
            } else {
                console.error("Failed to fetch task details", await resp.text());
            }
        } catch (err) {
            console.error("Error in handleRowClick:", err);
        }
    };

    return {
        // State
        tasks,
        allTasks,
        loading,
        targetDate,
        viewMode,
        activeFilter,
        setActiveFilter,
        activeProject,
        calendarTasks,
        overdueTasks,
        isMobile,
        selectedTask,
        panelOpen,
        createModalOpen,
        importModalOpen,
        isCompletedCollapsed,
        isDayDetailsOpen,
        todayStr,
        dayDetailsDate,
        currentMonth,
        refreshKey,
        availableProjects,
        displayTasks,
        groupedTasks,
        pendingTasks,
        completedTasksList,
        stats,
        quickAddName,
        quickAddLoading,
        quickAddFocused,
        activeOptions,
        qaContext,
        qaLoadScore,
        qaDueDate,

        // Refs
        quickAddRef,
        qaDateRef,

        // Setters
        setSelectedTask,
        setPanelOpen,
        setCreateModalOpen,
        setImportModalOpen,
        setIsCompletedCollapsed,
        setIsDayDetailsOpen,
        setDayDetailsDate,
        setTargetDate,
        setViewMode,
        setRefreshKey,
        setQuickAddName,
        setQuickAddFocused,
        setActiveOptions,
        setQaContext,
        setQaLoadScore,
        setQaDueDate,
        setCurrentMonth,

        // Handlers
        handleMarkDone,
        handleQuickAdd,
        handlePrev,
        handleNext,
        handleToday,
        handleExportCSV,
        handleRefresh,
        handleRowClick,
        fetchTasks,
        fetchAllTasks,
        fetchMonthTasks,
        toggleMyDay
    };
}
