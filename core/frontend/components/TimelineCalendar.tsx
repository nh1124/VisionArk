"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { apiFetch } from "@/lib/api";
import { ChevronLeft, ChevronRight, Clock, MoreVertical, Lock, AlertCircle } from "lucide-react";
import { getSpokeColor } from "@/lib/colors";
import { useTaskStore } from "../store/useTaskStore";

interface TimelineTask {
    task_id: string;
    task_name: string;
    context: string;
    load: number;
    status: string;
    start_time: string | null;
    end_time: string | null;
    has_exception: boolean;
    is_locked: boolean;
}

interface DaySchedule {
    date: string;
    total_load: number;
    tasks: TimelineTask[];
}

interface TimelineCalendarProps {
    targetDate: string;
    refreshKey?: number;
    onTaskClick?: (task: any) => void;
}

const HOURS = Array.from({ length: 17 }, (_, i) => i + 7); // 07:00 to 23:00
const HOUR_HEIGHT = 80; // pixels per hour

export default function TimelineCalendar({ targetDate, refreshKey = 0, onTaskClick }: TimelineCalendarProps) {
    const { activeProject } = useTaskStore();
    const [schedule, setSchedule] = useState<DaySchedule[]>([]);
    const [loading, setLoading] = useState(true);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    // Calculate week range
    const weekDays = useMemo(() => {
        const d = new Date(targetDate);
        const day = d.getDay(); // 0 (Sun) to 6 (Sat)
        const diff = d.getDate() - day; // Adjust to Sunday
        const sun = new Date(d.setDate(diff));

        return Array.from({ length: 7 }, (_, i) => {
            const next = new Date(sun);
            next.setDate(sun.getDate() + i);
            return next.toISOString().split('T')[0];
        });
    }, [targetDate]);

    useEffect(() => {
        loadWeekSchedule();
    }, [weekDays, refreshKey]);

    const loadWeekSchedule = async () => {
        setLoading(true);
        try {
            const startDate = weekDays[0];
            const endDate = weekDays[6];
            const resp = await apiFetch(`/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`);
            const data = await resp.json();
            setSchedule(Array.isArray(data) ? data : []);
        } catch (err) {
            console.error("Failed to load week schedule:", err);
        } finally {
            setLoading(false);
        }
    };

    const getTimePosition = (timeStr: string | null) => {
        if (!timeStr) return 0;
        const [h, m] = timeStr.split(':').map(Number);
        const totalMinutes = h * 60 + m;
        const startMinutes = 7 * 60; // 07:00
        return ((totalMinutes - startMinutes) / 60) * HOUR_HEIGHT;
    };

    const getTaskDurationHeight = (start: string | null, end: string | null) => {
        if (!start || !end) return HOUR_HEIGHT; // default 1 hour if missing
        const [h1, m1] = start.split(':').map(Number);
        const [h2, m2] = end.split(':').map(Number);
        const durationMinutes = (h2 * 60 + m2) - (h1 * 60 + m1);
        return (durationMinutes / 60) * HOUR_HEIGHT;
    };

    const formatDayHeader = (dateStr: string) => {
        const d = new Date(dateStr);
        const today = new Date().toISOString().split('T')[0];
        const isToday = dateStr === today;

        return (
            <div className={`flex flex-col items-center py-3 border-b border-gray-800 ${isToday ? 'bg-blue-600/10' : ''}`}>
                <span className={`text-[10px] font-black uppercase tracking-widest ${isToday ? 'text-blue-400' : 'text-gray-500'}`}>
                    {d.toLocaleDateString('en-US', { weekday: 'short' })}
                </span>
                <span className={`text-xl font-bold mt-0.5 ${isToday ? 'text-white' : 'text-gray-300'}`}>
                    {d.getDate()}
                </span>
                {isToday && <div className="w-1 h-1 bg-blue-500 rounded-full mt-1 animate-pulse" />}
            </div>
        );
    };

    if (loading && schedule.length === 0) {
        return <div className="h-[600px] flex items-center justify-center bg-gray-900/20 rounded-3xl border border-gray-800 animate-pulse">
            <span className="text-gray-600 font-bold uppercase tracking-widest">Loading Timeline...</span>
        </div>;
    }

    return (
        <div className="flex flex-col h-[calc(100vh-140px)] min-h-[600px] bg-gray-900/10 rounded-none border border-gray-800 overflow-hidden backdrop-blur-sm">
            {/* Week Header */}
            <div className="grid grid-cols-[60px_1fr] flex-shrink-0">
                <div className="border-r border-b border-gray-800 flex items-center justify-center bg-gray-900/40">
                    <Clock className="w-4 h-4 text-gray-600" />
                </div>
                <div className="grid grid-cols-7 divide-x divide-gray-800/50 bg-gray-900/20">
                    {weekDays.map(day => (
                        <div key={day}>{formatDayHeader(day)}</div>
                    ))}
                </div>
            </div>

            {/* All-day tasks section */}
            <div className="grid grid-cols-[60px_1fr] flex-shrink-0 border-b border-gray-800/50 bg-gray-950/20">
                <div className="border-r border-gray-800 flex items-center justify-center p-1">
                    <span className="text-[9px] font-black uppercase text-gray-600 [writing-mode:vertical-lr] rotate-180">All Day</span>
                </div>
                <div className="grid grid-cols-7 divide-x divide-gray-800/30">
                    {weekDays.map(dateStr => {
                        const dayData = schedule.find(d => d.date === dateStr);
                        const allDayTasks = (dayData?.tasks || [])
                            .filter(t => !t.start_time)
                            .filter(t => !activeProject || t.context === activeProject);
                        return (
                            <div key={dateStr} className="min-h-[48px] p-1 flex flex-col gap-1 bg-white/[0.01]">
                                {allDayTasks.map(task => (
                                    <div
                                        key={task.task_id}
                                        onClick={() => onTaskClick?.({ ...task, due_date: dateStr })}
                                        className="text-[10px] font-bold px-2 py-1.5 rounded-lg border border-white/5 bg-gray-900/80 cursor-pointer hover:bg-white/10 transition-colors shadow-sm truncate flex items-center gap-2"
                                        style={{ borderLeft: `3px solid ${getSpokeColor(task.context)}` }}
                                        title={task.task_name}
                                    >
                                        <span className="truncate flex-1">{task.task_name}</span>
                                        {task.is_locked && <Lock className="w-2.5 h-2.5 text-gray-600 flex-shrink-0" />}
                                    </div>
                                ))}
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Scrollable Area */}
            <div className="grid grid-cols-[60px_1fr] flex-1 overflow-y-auto no-scrollbar relative" ref={scrollContainerRef}>
                {/* Time Grid Y-Axis */}
                <div className="sticky left-0 z-20 bg-gray-950/80 backdrop-blur-md border-r border-gray-800">
                    {HOURS.map(hour => (
                        <div key={hour} style={{ height: HOUR_HEIGHT }} className="flex justify-center pt-2">
                            <span className="text-[10px] font-black text-gray-600 tabular-nums">
                                {String(hour).padStart(2, '0')}:00
                            </span>
                        </div>
                    ))}
                </div>

                {/* Timeline Grid Content */}
                <div className="relative grid grid-cols-7 divide-x divide-gray-800/20 min-h-[1360px]">
                    {/* Horizontal grid lines */}
                    {HOURS.map(hour => (
                        <div
                            key={`line-${hour}`}
                            style={{ top: (hour - 7) * HOUR_HEIGHT }}
                            className="absolute left-0 right-0 border-t border-gray-800/30 pointer-events-none"
                        />
                    ))}

                    {/* Task Slots for each day */}
                    {weekDays.map(dateStr => {
                        const dayData = schedule.find(d => d.date === dateStr);
                        const tasksToShow = (dayData?.tasks || [])
                            .filter(t => !activeProject || t.context === activeProject);

                        return (
                            <div key={dateStr} className="relative h-full px-1 py-1">
                                {tasksToShow.map(task => {
                                    if (!task.start_time) return null; // Only show tasks with times on timeline

                                    const top = getTimePosition(task.start_time);
                                    const height = getTaskDurationHeight(task.start_time, task.end_time);
                                    const contextColor = getSpokeColor(task.context);

                                    return (
                                        <div
                                            key={task.task_id}
                                            onClick={() => onTaskClick?.({ ...task, due_date: dateStr })}
                                            style={{
                                                top: top + 4,
                                                height: height - 8,
                                                borderColor: `${contextColor}40`,
                                                backgroundColor: `${contextColor}15`
                                            }}
                                            className="absolute inset-x-1.5 p-2 rounded-xl border group cursor-pointer transition-all hover:bg-white/5 active:scale-[0.98] overflow-hidden backdrop-blur-sm z-10"
                                        >
                                            <div className="flex flex-col h-full">
                                                <div className="flex items-start justify-between gap-1 mb-1">
                                                    <span className="text-[10px] sm:text-xs font-bold leading-tight line-clamp-2 transition-colors group-hover:text-white" style={{ color: contextColor }}>
                                                        {task.task_name}
                                                    </span>
                                                    {task.is_locked && <Lock className="w-2.5 h-2.5 text-gray-500 flex-shrink-0" />}
                                                </div>

                                                <div className="mt-auto flex items-center justify-between text-[8px] font-black uppercase tracking-widest opacity-60">
                                                    <span>{task.start_time.slice(0, 5)} - {task.end_time?.slice(0, 5)}</span>
                                                    {task.has_exception && <AlertCircle className="w-2.5 h-2.5 text-amber-500" />}
                                                </div>
                                            </div>

                                            {/* Accent line */}
                                            <div className="absolute left-0 top-0 bottom-0 w-1 rounded-full" style={{ backgroundColor: contextColor }} />
                                        </div>
                                    );
                                })}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
