"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { getLocalDateString } from "@/lib/dateUtils";
import { useTaskStore } from "../store/useTaskStore";
import { useIsMobile } from "../hooks/useIsMobile";

interface TaskSummary {
    task_id: string;
    task_name: string;
    status: string;
}

interface DayData {
    date: string;
    load: number;
    adjusted_load?: number; // fallback
    level: "SAFE" | "WARNING" | "DANGER" | "CRITICAL";
    taskCount: number;
    task_count?: number; // fallback
    tasks?: TaskSummary[];
}

interface HeatMapCalendarProps {
    month: Date;
    onDayClick?: (date: string) => void;
    refreshKey?: number;
    includeCompleted?: boolean;
    activeProject?: string | null;
}

export default function HeatMapCalendar({
    month,
    onDayClick,
    refreshKey = 0,
    includeCompleted = true,
    activeProject: activeProjectProp
}: HeatMapCalendarProps) {
    const store = useTaskStore();
    const activeProject = activeProjectProp !== undefined ? activeProjectProp : store.activeProject;
    const [daysData, setDaysData] = useState<DayData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadMonthData();
    }, [month, refreshKey, includeCompleted, activeProject]);

    const loadMonthData = async () => {
        setLoading(true);
        const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
        const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);

        const startDate = `${firstDay.getFullYear()}-${String(firstDay.getMonth() + 1).padStart(2, '0')}-01`;
        const endDate = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`;

        try {
            // Use schedule API to get full task details for each day
            const response = await apiFetch(
                `/api/lbs/schedule?start_date=${startDate}&end_date=${endDate}`
            );
            const data = await response.json();

            // Map schedule data to DayData format
            const days: DayData[] = data.map((day: any) => {
                // Determine level based on load
                const load = day.total_load || 0;
                let level: "SAFE" | "WARNING" | "DANGER" | "CRITICAL" = "SAFE";
                if (load > 8) level = "CRITICAL";
                else if (load > 5) level = "DANGER";
                else if (load > 3) level = "WARNING";

                return {
                    date: day.date,
                    load: load,
                    level: level,
                    taskCount: day.tasks?.filter((t: any) => !activeProject || t.context === activeProject).length || 0,
                    tasks: day.tasks
                        ?.filter((t: any) => !activeProject || t.context === activeProject)
                        .map((t: any) => ({
                            task_id: t.task_id,
                            task_name: t.task_name,
                            status: t.status
                        })) || []
                };
            });

            setDaysData(days);
        } catch (error) {
            console.error("Failed to load heat map data:", error);
        } finally {
            setLoading(false);
        }
    };

    const getLevelDotColor = (level: string) => {
        switch (level) {
            case "SAFE": return "bg-emerald-500";
            case "WARNING": return "bg-amber-500";
            case "DANGER": return "bg-orange-500";
            case "CRITICAL": return "bg-red-500";
            default: return "bg-gray-700";
        }
    };

    const getLevelBgColor = (level: string) => {
        switch (level) {
            case "SAFE": return "bg-gray-900/40 hover:bg-gray-800/60 border-gray-800";
            case "WARNING": return "bg-amber-950/10 hover:bg-amber-900/20 border-amber-900/30";
            case "DANGER": return "bg-orange-950/20 hover:bg-orange-900/30 border-orange-900/40";
            case "CRITICAL": return "bg-red-950/20 hover:bg-red-900/30 border-red-900/40";
            default: return "bg-gray-900/40 border-gray-800";
        }
    };

    const firstDayOfMonth = new Date(month.getFullYear(), month.getMonth(), 1);
    const lastDayOfMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const startingDayOfWeek = firstDayOfMonth.getDay();
    const daysInMonth = lastDayOfMonth.getDate();

    const weeks = [];
    let currentWeek = [];

    for (let i = 0; i < startingDayOfWeek; i++) {
        currentWeek.push(null);
    }

    for (let day = 1; day <= daysInMonth; day++) {
        const year = month.getFullYear();
        const monthNum = String(month.getMonth() + 1).padStart(2, '0');
        const dayNum = String(day).padStart(2, '0');
        const dateStr = `${year}-${monthNum}-${dayNum}`;
        const dayData = daysData.find((d) => d.date === dateStr);

        currentWeek.push({ day, dateStr, data: dayData });
        if (currentWeek.length === 7) {
            weeks.push(currentWeek);
            currentWeek = [];
        }
    }

    if (currentWeek.length > 0) {
        while (currentWeek.length < 7) {
            currentWeek.push(null);
        }
        weeks.push(currentWeek);
    }

    const isMobile = useIsMobile();

    if (loading) {
        return <div className="animate-pulse h-96 bg-gray-950/40 rounded-3xl border border-gray-800"></div>;
    }

    return (
        <div className="w-full">
            <div className={`grid grid-cols-7 ${isMobile ? 'gap-1.5' : 'gap-3'} mb-4`}>
                {["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].map((day) => (
                    <div key={day} className="text-center text-[10px] font-black text-gray-700 tracking-widest">
                        {isMobile ? day.charAt(0) : day}
                    </div>
                ))}
            </div>

            <div className={isMobile ? 'space-y-1.5' : 'space-y-3'}>
                {weeks.map((week, weekIdx) => (
                    <div key={weekIdx} className={`grid grid-cols-7 ${isMobile ? 'gap-1.5' : 'gap-3'}`}>
                        {week.map((cell, cellIdx) => {
                            if (!cell) return <div key={cellIdx} className="aspect-square"></div>;
                            const level = cell.data?.level || "UNKNOWN";
                            const isActive = cell.dateStr === getLocalDateString();

                            return (
                                <div
                                    key={cellIdx}
                                    onClick={() => onDayClick?.(cell.dateStr)}
                                    className={`
                                        aspect-square rounded-xl border p-1.5 flex flex-col justify-start transition-all cursor-pointer relative group overflow-hidden
                                        ${getLevelBgColor(level)}
                                        ${isActive ? 'ring-2 ring-blue-500 ring-offset-2 ring-offset-gray-900 shadow-[0_0_15px_-3px_rgba(59,130,246,0.5)]' : ''}
                                        hover:scale-[1.02] active:scale-[0.95]
                                    `}
                                >
                                    <div className="flex justify-between items-center mb-1 relative z-10">
                                        <span className={`text-[10px] sm:text-xs font-black leading-none ${cell.data ? 'text-blue-400' : 'text-gray-600'}`}>
                                            {cell.day}
                                        </span>
                                        {cell.data && cell.data.taskCount > 0 && (
                                            <div className={`w-1.5 h-1.5 rounded-full shadow-sm ${getLevelDotColor(level)} shadow-[0_0_8px_rgba(0,0,0,0.5)]`} />
                                        )}
                                    </div>

                                    {/* Task List - Only on Desktop */}
                                    {!isMobile && (
                                        <div className="flex-1 overflow-hidden flex flex-col gap-0.5 mt-0.5 relative z-10">
                                            {cell.data?.tasks?.slice(0, 2).map((task, idx) => (
                                                <div
                                                    key={task.task_id}
                                                    className={`text-[8px] sm:text-[9px] truncate leading-none py-0.5 px-1 rounded ${task.status === 'done'
                                                        ? 'bg-emerald-500/10 text-emerald-500/70 line-through'
                                                        : 'bg-white/5 text-gray-400'
                                                        }`}
                                                >
                                                    {task.task_name}
                                                </div>
                                            ))}
                                            {cell.data && cell.data.taskCount > 2 && (
                                                <div className="text-[7px] sm:text-[8px] text-gray-600 font-bold pl-1 mt-auto">
                                                    +{cell.data.taskCount - 2}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* Mobile indicator for task count */}
                                    {isMobile && cell.data && cell.data.taskCount > 0 && (
                                        <div className="absolute bottom-1 right-1 text-[8px] font-black text-gray-600/50">
                                            {cell.data.taskCount}
                                        </div>
                                    )}

                                    {/* Decorative background glow for active/high load */}
                                    <div className={`absolute -right-4 -bottom-4 w-8 h-8 rounded-full blur-xl opacity-20 ${getLevelDotColor(level)}`} />
                                </div>
                            );
                        })}
                    </div>
                ))}
            </div>

            <div className="mt-8 flex justify-center gap-6 text-[10px] font-bold uppercase tracking-widest text-gray-500">
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500" />
                    <span>Safe</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-amber-500" />
                    <span>Warning</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-orange-500" />
                    <span>Danger</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-red-500" />
                    <span>Critical</span>
                </div>
            </div>
        </div>
    );
}
