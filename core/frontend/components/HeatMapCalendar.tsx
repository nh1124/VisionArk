"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface DayData {
    date: string;
    load: number;
    adjusted_load?: number; // fallback
    level: "SAFE" | "WARNING" | "DANGER" | "CRITICAL";
    taskCount: number;
    task_count?: number; // fallback
}

interface HeatMapCalendarProps {
    month: Date;
    onDayClick?: (date: string) => void;
    refreshKey?: number;
    includeCompleted?: boolean;
}

export default function HeatMapCalendar({
    month,
    onDayClick,
    refreshKey = 0,
    includeCompleted = true
}: HeatMapCalendarProps) {
    const [daysData, setDaysData] = useState<DayData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadMonthData();
    }, [month, refreshKey, includeCompleted]);

    const loadMonthData = async () => {
        setLoading(true);
        const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
        const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);

        const startDate = `${firstDay.getFullYear()}-${String(firstDay.getMonth() + 1).padStart(2, '0')}-01`;
        const endDate = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`;

        try {
            // Note: The backend needs to handle include_completed if we want exact filtering there.
            // For now we pass it as a param.
            const statusParams = includeCompleted ? "status=todo&status=done" : "status=todo";
            const response = await apiFetch(
                `/api/lbs/heatmap?start=${startDate}&end=${endDate}&${statusParams}`
            );
            const data = await response.json();
            const days = Array.isArray(data) ? data : (data.days || []);
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

    if (loading) {
        return <div className="animate-pulse h-96 bg-gray-900/50 rounded-xl border border-gray-800"></div>;
    }

    return (
        <div className="w-full">
            <div className="grid grid-cols-7 gap-3 mb-4">
                {["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].map((day) => (
                    <div key={day} className="text-center text-[10px] font-bold text-gray-600 tracking-wider">
                        {day}
                    </div>
                ))}
            </div>

            <div className="space-y-3">
                {weeks.map((week, weekIdx) => (
                    <div key={weekIdx} className="grid grid-cols-7 gap-3">
                        {week.map((cell, cellIdx) => {
                            if (!cell) return <div key={cellIdx} className="aspect-square"></div>;
                            const level = cell.data?.level || "UNKNOWN";
                            const isActive = cell.dateStr === new Date().toISOString().split('T')[0];

                            return (
                                <div
                                    key={cellIdx}
                                    onClick={() => onDayClick?.(cell.dateStr)}
                                    className={`
                                        aspect-square rounded-2xl border-2 p-3 flex flex-col justify-between transition-all cursor-pointer relative group
                                        ${getLevelBgColor(level)}
                                        ${isActive ? 'ring-2 ring-blue-500/50 ring-offset-4 ring-offset-gray-950' : ''}
                                        hover:scale-[1.02] active:scale-[0.98]
                                    `}
                                >
                                    <div className="flex justify-between items-start">
                                        <span className={`text-sm font-semibold tracking-wide ${cell.data ? 'text-gray-400' : 'text-gray-700'}`}>
                                            {cell.day}
                                        </span>
                                        {cell.data && (
                                            <div className={`w-2 h-2 rounded-full shadow-sm ${getLevelDotColor(level)}`} />
                                        )}
                                    </div>

                                    <div className="flex flex-col items-center justify-center -mt-2">
                                        {/* Numerical load and task counts removed to reduce cognitive load */}
                                    </div>

                                    {/* Glass reflection effect */}
                                    <div className="absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-white/5 to-transparent rounded-t-2xl pointer-events-none" />
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
