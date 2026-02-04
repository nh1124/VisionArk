import { create } from 'zustand';
import { Task } from '../app/tasks/types';
import { apiFetch } from '../lib/api';

export type TaskFilter = 'inbox' | 'today' | 'my-day' | 'planned' | 'completed' | 'project' | 'overdue';
export type ViewMode = 'list' | 'calendar' | 'timeline';

interface TaskState {
    tasks: Task[]; // Current view's tasks
    allTasks: Task[]; // Global active tasks for counts
    calendarTasks: Task[]; // Separate storage for month view
    overdueTasks: Task[]; // Tasks from the past that are still TODO
    loading: boolean;
    error: string | null;
    targetDate: string; // YYYY-MM-DD
    viewMode: ViewMode;
    activeFilter: TaskFilter;
    activeProject: string | null;
    selectedTaskId: string | null;

    // Actions
    setTargetDate: (date: string) => void;
    setViewMode: (mode: ViewMode) => void;
    setActiveFilter: (filter: TaskFilter, project?: string | null) => void;
    setSelectedTaskId: (id: string | null) => void;

    fetchTasks: (date: string) => Promise<void>;
    fetchAllTasks: () => Promise<void>;
    fetchMonthTasks: (startDate: string, endDate: string) => Promise<void>;
    fetchOverdueTasks: () => Promise<void>;
    updateTaskStatus: (taskId: string, status: string, date: string) => Promise<void>;
    toggleMyDay: (task: Task) => Promise<void>;
    rescheduleTask: (taskId: string, newDate: string) => Promise<void>;
    updateTask: (taskId: string, data: Partial<Task>) => Promise<void>;
    createException: (taskId: string, targetDate: string, exceptionType: string, overrideData: Partial<Task>) => Promise<void>;
}

export const useTaskStore = create<TaskState>((set, get) => ({
    tasks: [],
    allTasks: [],
    calendarTasks: [],
    overdueTasks: [],
    loading: false,
    error: null,
    targetDate: new Date().toISOString().split('T')[0],
    viewMode: 'list',
    activeFilter: 'inbox',
    activeProject: null,
    selectedTaskId: null,

    setTargetDate: (date) => {
        set({ targetDate: date });
        get().fetchTasks(date);
    },

    setViewMode: (mode) => set({ viewMode: mode }),

    setActiveFilter: (filter, project = null) => {
        if (filter === 'today' || filter === 'my-day') {
            const today = new Date().toISOString().split('T')[0];
            set({ targetDate: today, activeFilter: filter, activeProject: project });
            get().fetchTasks(today);
        } else {
            set({ activeFilter: filter, activeProject: project });
        }
    },

    setSelectedTaskId: (id) => set({ selectedTaskId: id }),

    fetchTasks: async (date) => {
        set({ loading: true, error: null });
        try {
            const resp = await apiFetch(`/api/lbs/tasks?target_date=${date}&active=true`);
            const data = await resp.json();
            set({ tasks: Array.isArray(data) ? data : [], loading: false });
        } catch (err) {
            set({ error: 'Failed to fetch tasks', loading: false });
            console.error(err);
        }
    },

    fetchAllTasks: async () => {
        // Fetch all active tasks to populate counts and global views
        try {
            const resp = await apiFetch(`/api/lbs/tasks?active=true`);
            const data = await resp.json();
            set({ allTasks: Array.isArray(data) ? data : [] });
        } catch (err) {
            console.error('Failed to fetch all tasks:', err);
        }
    },

    fetchMonthTasks: async (startDate: string, endDate: string) => {
        set({ loading: true, error: null });
        try {
            const resp = await apiFetch(`/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`);
            const data = await resp.json();
            // Data is Array<{ date: string, tasks: Task[] }>
            const flattened: Task[] = [];
            const allTasks = get().allTasks;
            if (Array.isArray(data)) {
                data.forEach((day: any) => {
                    day.tasks.forEach((t: any) => {
                        // Try to match with existing task to get full metadata (is_locked, meta_payload)
                        const definition = allTasks.find(at => at.task_id === t.task_id);
                        flattened.push({
                            ...definition, // Spread definition first to get all metadata
                            ...t,          // Overlay schedule-specific status/times
                            base_load_score: t.load ?? definition?.base_load_score, // Ensure overridden load is used for UI slider
                            due_date: day.date // Use the day's date as due_date for schedule tasks
                        });
                    });
                });
            }
            set({ calendarTasks: flattened, loading: false });
        } catch (err) {
            set({ error: 'Failed to fetch month tasks', loading: false });
            console.error(err);
        }
    },

    fetchOverdueTasks: async () => {
        set({ loading: true, error: null });
        try {
            const today = new Date();
            const start = new Date();
            start.setDate(today.getDate() - 7); // Check last 7 days
            const startDate = start.toISOString().split('T')[0];
            const yesterday = new Date();
            yesterday.setDate(today.getDate() - 1);
            const endDate = yesterday.toISOString().split('T')[0];

            const resp = await apiFetch(`/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`);
            const data = await resp.json();

            const overdue: Task[] = [];
            if (Array.isArray(data)) {
                data.forEach((day: any) => {
                    day.tasks?.forEach((t: any) => {
                        if (t.status === 'todo') {
                            overdue.push({ ...t, due_date: day.date });
                        }
                    });
                });
            }
            set({ overdueTasks: overdue, loading: false });
        } catch (err) {
            set({ error: 'Failed to fetch overdue tasks', loading: false });
            console.error(err);
        }
    },

    updateTaskStatus: async (taskId, status, date) => {
        try {
            const resp = await apiFetch(`/api/lbs/tasks/${taskId}/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_date: date, status })
            });
            if (resp.ok) {
                // Update local state for immediate feedback in both lists
                set((state) => ({
                    tasks: state.tasks.map((t) =>
                        t.task_id === taskId ? { ...t, status } : t
                    ),
                    allTasks: state.allTasks.map((t) =>
                        t.task_id === taskId ? { ...t, status } : t
                    ),
                    calendarTasks: state.calendarTasks.map((t) =>
                        t.task_id === taskId && t.due_date === date ? { ...t, status } : t
                    ),
                    overdueTasks: state.overdueTasks.map((t) =>
                        t.task_id === taskId && t.due_date === date ? { ...t, status } : t
                    )
                }));
            }
        } catch (err) {
            console.error('Failed to update task status:', err);
        }
    },

    toggleMyDay: async (task) => {
        const isMyDay = !task.meta_payload?.is_my_day;
        const newMeta = { ...task.meta_payload, is_my_day: isMyDay };

        try {
            // Always include force_override=true for pinning as it's a common operation on protected tasks
            const url = `/api/lbs/tasks/${task.task_id}?force_override=true`;
            const response = await apiFetch(url, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ meta_payload: newMeta })
            });

            if (response.ok) {
                // Update local state for both lists
                set((state) => ({
                    tasks: state.tasks.map((t) =>
                        t.task_id === task.task_id ? { ...t, meta_payload: { ...t.meta_payload, is_my_day: isMyDay } } : t
                    ),
                    allTasks: state.allTasks.map((t) =>
                        t.task_id === task.task_id ? { ...t, meta_payload: { ...t.meta_payload, is_my_day: isMyDay } } : t
                    ),
                    calendarTasks: state.calendarTasks.map((t) =>
                        t.task_id === task.task_id ? { ...t, meta_payload: { ...t.meta_payload, is_my_day: isMyDay } } : t
                    ),
                    overdueTasks: state.overdueTasks.map((t) =>
                        t.task_id === task.task_id ? { ...t, meta_payload: { ...t.meta_payload, is_my_day: isMyDay } } : t
                    )
                }));
            }
        } catch (error) {
            console.error("Failed to toggle My Day:", error);
        }
    },

    rescheduleTask: async (taskId, newDate) => {
        try {
            const resp = await apiFetch(`/api/lbs/tasks/${taskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ due_date: newDate })
            });
            if (resp.ok) {
                set((state) => ({
                    tasks: state.tasks.map((t) =>
                        t.task_id === taskId ? { ...t, due_date: newDate } : t
                    ),
                    calendarTasks: state.calendarTasks.map((t) =>
                        t.task_id === taskId ? { ...t, due_date: newDate } : t
                    )
                }));
                // Invalidate/Refetch if needed, but local update is enough for drag feedback
            }
        } catch (err) {
            console.error('Failed to reschedule task:', err);
        }
    },

    updateTask: async (taskId, data) => {
        try {
            const resp = await apiFetch(`/api/lbs/tasks/${taskId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (resp.ok) {
                set((state) => ({
                    tasks: state.tasks.map((t) =>
                        t.task_id === taskId ? { ...t, ...data } : t
                    ),
                    calendarTasks: state.calendarTasks.map((t) =>
                        t.task_id === taskId ? { ...t, ...data } : t
                    )
                }));
            }
        } catch (err) {
            console.error('Failed to update task:', err);
        }
    },

    createException: async (taskId, targetDate, exceptionType, overrideData) => {
        try {
            const payload = {
                task_id: taskId,
                target_date: targetDate,
                exception_type: exceptionType,
                override_load_value: overrideData.base_load_score,
                start_time: overrideData.start_time,
                end_time: overrideData.end_time,
                notes: overrideData.notes
            };

            const resp = await apiFetch('/api/lbs/exceptions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (resp.ok) {
                // After creating an exception, we should refetch the task for that date to get the "resolved" state
                const resolveResp = await apiFetch(`/api/lbs/tasks/${taskId}/resolved?target_date=${targetDate}`);
                if (resolveResp.ok) {
                    const resolvedTask = await resolveResp.json();
                    set((state) => ({
                        tasks: state.tasks.map((t) =>
                            t.task_id === taskId ? { ...t, ...resolvedTask } : t
                        ),
                        calendarTasks: state.calendarTasks.map((t) =>
                            t.task_id === taskId ? { ...t, ...resolvedTask } : t
                        )
                    }));
                }
            }
        } catch (err) {
            console.error('Failed to create exception:', err);
        }
    }
}));
