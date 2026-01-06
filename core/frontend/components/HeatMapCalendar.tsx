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
    refreshKey?: number;  // ✅ NEW: Parent can increment this to trigger refresh
}

export default function HeatMapCalendar({
    month,
    onDayClick,
    refreshKey = 0  // ✅ Default to 0
}: HeatMapCalendarProps) {
    const [daysData, setDaysData] = useState<DayData[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadMonthData();
    }, [month, refreshKey]);  // ✅ Reload when refreshKey changes

    const loadMonthData = async () => {
        // Get first and last day of month
        const firstDay = new Date(month.getFullYear(), month.getMonth(), 1);
        const lastDay = new Date(month.getFullYear(), month.getMonth() + 1, 0);

        // Build date strings WITHOUT timezone conversion
        const startDate = `${firstDay.getFullYear()}-${String(firstDay.getMonth() + 1).padStart(2, '0')}-01`;
        const endDate = `${lastDay.getFullYear()}-${String(lastDay.getMonth() + 1).padStart(2, '0')}-${String(lastDay.getDate()).padStart(2, '0')}`;

        try {
            const response = await apiFetch(
                `/api/lbs/heatmap?start=${startDate}&end=${endDate}`
            );
            const data = await response.json();

            // Handle both { days: [...] } and plain array [...]
            const days = Array.isArray(data) ? data : (data.days || []);
            setDaysData(days);
        } catch (error) {
            console.error("Failed to load heat map data:", error);
        } finally {
            setLoading(false);
        }
    };

    const getLevelColor = (level: string) => {
        switch (level) {
            case "SAFE":
                return "bg-green-500/30 hover:bg-green-500/50 border-green-500";
            case "WARNING":
                return "bg-yellow-500/30 hover:bg-yellow-500/50 border-yellow-500";
            case "DANGER":
                return "bg-orange-500/30 hover:bg-orange-500/50 border-orange-500";
            case "CRITICAL":
                return "bg-red-500/30 hover:bg-red-500/50 border-red-500";
            default:
                return "bg-gray-700/30 hover:bg-gray-700/50 border-gray-700";
        }
    };

    // Generate calendar grid
    const firstDayOfMonth = new Date(month.getFullYear(), month.getMonth(), 1);
    const lastDayOfMonth = new Date(
        month.getFullYear(),
        month.getMonth() + 1,
        0
    );
    const startingDayOfWeek = firstDayOfMonth.getDay(); // 0 = Sunday
    const daysInMonth = lastDayOfMonth.getDate();

    const weeks = [];
    let currentWeek = [];

    // Add empty cells for days before month starts
    for (let i = 0; i < startingDayOfWeek; i++) {
        currentWeek.push(null);
    }

    // Add all days of month
    for (let day = 1; day <= daysInMonth; day++) {
        // Build date string WITHOUT timezone conversion
        const year = month.getFullYear();
        const monthNum = String(month.getMonth() + 1).padStart(2, '0');
        const dayNum = String(day).padStart(2, '0');
        const dateStr = `${year}-${monthNum}-${dayNum}`;

        const dayData = daysData.find((d) => d.date === dateStr);

        currentWeek.push({
            day,
            dateStr,
            data: dayData,
        });

        // Start new week on Sunday
        if (currentWeek.length === 7) {
            weeks.push(currentWeek);
            currentWeek = [];
        }
    }

    // Add remaining days to last week
    if (currentWeek.length > 0) {
        while (currentWeek.length < 7) {
            currentWeek.push(null);
        }
        weeks.push(currentWeek);
    }

    if (loading) {
        return (
            <div className="animate-pulse">
                <div className="h-64 bg-gray-800 rounded"></div>
            </div>
        );
    }

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="mb-4 flex items-center justify-end">
                <div className="flex gap-2 text-xs">
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-green-500/30 border border-green-500"></div>
                        <span className="text-gray-400">Safe</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-yellow-500/30 border border-yellow-500"></div>
                        <span className="text-gray-400">Warning</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-orange-500/30 border border-orange-500"></div>
                        <span className="text-gray-400">Danger</span>
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-3 rounded bg-red-500/30 border border-red-500"></div>
                        <span className="text-gray-400">Critical</span>
                    </div>
                </div>
            </div>

            {/* Weekday headers */}
            <div className="grid grid-cols-7 gap-1 mb-2">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => (
                    <div
                        key={day}
                        className="text-center text-xs font-semibold text-gray-500 py-1"
                    >
                        {day}
                    </div>
                ))}
            </div>

            {/* Calendar grid */}
            <div className="space-y-1">
                {weeks.map((week, weekIdx) => (
                    <div key={weekIdx} className="grid grid-cols-7 gap-1">
                        {week.map((cell, cellIdx) => (
                            <div
                                key={cellIdx}
                                className={`
                  aspect-square rounded border transition-all cursor-pointer
                  ${cell
                                        ? getLevelColor(cell.data?.level || "")
                                        : "bg-transparent border-transparent"
                                    }
                `}
                                onClick={() => {
                                    if (cell && onDayClick) {
                                        onDayClick(cell.dateStr);
                                    }
                                }}
                            >
                                {cell && (
                                    <div className="w-full h-full flex flex-col items-center justify-center p-1">
                                        <div className="text-sm font-semibold">{cell.day}</div>
                                        {cell.data && (
                                            <div className="text-xs text-gray-400">
                                                {((cell.data.load ?? cell.data.adjusted_load) ?? 0).toFixed(1)}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                ))}
            </div>
        </div>
    );
}
