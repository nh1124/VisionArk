"use client";

import { useEffect, useState, useMemo } from "react";
import { apiFetch } from "@/lib/api";
import HeatMapCalendar from "@/components/HeatMapCalendar";
import TrendLineChart from "@/components/TrendLineChart";

interface DashboardData {
    today: {
        adjusted_load: number;
        level: string;
        task_count: number;
        unique_contexts: number;
        cap: number;
        tasks: Array<{
            task_name: string;
            context: string;
            load: number;
        }>;
    };
    weekly: {
        average_load: number;
        over_days: number;
        recovery_rate: number;
    };
    config: {
        CAP: number;
        ALPHA: number;
        BETA: number;
        SWITCH_COST: number;
    };
}

export default function DashboardPage() {
    const [data, setData] = useState<DashboardData | null>(null);
    const [trendData, setTrendData] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [refreshKey, setRefreshKey] = useState(0);

    useEffect(() => {
        const loadAllData = async () => {
            setLoading(true);
            try {
                const dashRes = await apiFetch("/api/lbs/dashboard");
                const dashData = await dashRes.json();
                setData(dashData);

                const trendRes = await apiFetch("/api/lbs/trends?weeks=12");
                const trendDataJson = await trendRes.json();
                setTrendData(trendDataJson.trends || []);
            } catch (error) {
                console.error("Error loading dashboard data:", error);
            } finally {
                setLoading(false);
            }
        };
        loadAllData();
    }, [refreshKey]);

    const changeMonth = (delta: number) => {
        setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
    };

    const loadPercentage = useMemo(() => {
        if (!data?.today) return 0;
        return Math.min(100, (data.today.adjusted_load / data.today.cap) * 100);
    }, [data]);

    const getStatusTheme = (level: string) => {
        switch (level) {
            case "SAFE": return { color: "text-emerald-400", bg: "bg-emerald-500", border: "border-emerald-500/30", label: "Safe" };
            case "WARNING": return { color: "text-amber-400", bg: "bg-amber-500", border: "border-amber-500/30", label: "Warning" };
            case "DANGER": return { color: "text-orange-400", bg: "bg-orange-500", border: "border-orange-500/30", label: "High" };
            case "CRITICAL": return { color: "text-red-400", bg: "bg-red-500", border: "border-red-500/30", label: "Critical" };
            default: return { color: "text-gray-400", bg: "bg-gray-500", border: "border-gray-500/30", label: "Unknown" };
        }
    };

    if (loading) return (
        <div className="min-h-screen bg-gray-950 flex items-center justify-center">
            <div className="text-gray-500 animate-pulse">Loading dashboard...</div>
        </div>
    );

    if (!data) return (
        <div className="min-h-screen bg-gray-950 p-8">
            <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400">
                Failed to load dashboard data. Please check your connection.
            </div>
        </div>
    );

    const theme = getStatusTheme(data.today?.level || "UNKNOWN");

    return (
        <div className="min-h-screen bg-gray-950 text-white p-6 lg:p-8">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-2xl lg:text-3xl font-semibold text-white">Dashboard</h1>
                        <p className="text-gray-500 text-sm mt-1">Load balance overview</p>
                    </div>
                    <button
                        onClick={() => setRefreshKey(k => k + 1)}
                        className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors text-sm text-gray-300 flex items-center gap-2"
                    >
                        <span>↻</span> Refresh
                    </button>
                </div>

                {/* Primary Metrics */}
                <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-8">
                    {/* Load Capacity - Main Card */}
                    <div className={`lg:col-span-2 bg-gray-900/80 border ${theme.border} rounded-xl p-6`}>
                        <div className="flex items-center justify-between mb-4">
                            <span className="text-sm text-gray-400">Current Capacity</span>
                            <span className={`text-xs px-2.5 py-1 rounded-full ${theme.bg}/20 ${theme.color}`}>
                                {theme.label}
                            </span>
                        </div>
                        <div className="flex items-end gap-3 mb-4">
                            <span className="text-5xl font-semibold tabular-nums">{loadPercentage.toFixed(0)}</span>
                            <span className="text-xl text-gray-500 mb-1">%</span>
                        </div>
                        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full transition-all duration-700 ${theme.bg}`}
                                style={{ width: `${loadPercentage}%` }}
                            />
                        </div>
                        <div className="flex justify-between mt-3 text-xs text-gray-500">
                            <span>{data.today?.adjusted_load.toFixed(1)} load</span>
                            <span>Cap: {data.today?.cap}</span>
                        </div>
                    </div>

                    {/* Weekly Recovery */}
                    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
                        <span className="text-sm text-gray-400">Weekly Recovery</span>
                        <div className="mt-3 flex items-end gap-2">
                            <span className="text-4xl font-semibold tabular-nums">{data.weekly?.recovery_rate.toFixed(1)}</span>
                            <span className="text-lg text-gray-500 mb-1">%</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-2">Efficiency rate</p>
                        <div className="mt-4 flex gap-1">
                            {[1, 2, 3, 4, 5, 6, 7].map(i => (
                                <div
                                    key={i}
                                    className={`h-1.5 flex-1 rounded-full ${i <= (data.weekly?.over_days || 0) ? 'bg-red-500/50' : 'bg-emerald-500/30'}`}
                                />
                            ))}
                        </div>
                        <p className="text-[10px] text-gray-600 mt-2">Days over capacity this week</p>
                    </div>

                    {/* Daily Stats */}
                    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
                        <span className="text-sm text-gray-400">Today's Tasks</span>
                        <div className="mt-3 flex items-end gap-2">
                            <span className="text-4xl font-semibold tabular-nums">{data.today?.task_count}</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-2">Active tasks</p>
                        <div className="mt-4 flex items-center justify-between py-2 px-3 bg-gray-800/50 rounded-lg">
                            <span className="text-xs text-gray-400">Contexts</span>
                            <span className="text-sm font-medium text-blue-400">{data.today?.unique_contexts}</span>
                        </div>
                    </div>
                </div>

                {/* Charts Row */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
                    {/* Trend Chart */}
                    <div className="lg:col-span-2 bg-gray-900/50 border border-gray-800 rounded-xl p-6">
                        <div className="flex justify-between items-center mb-6">
                            <h2 className="text-lg font-medium">Performance Trends</h2>
                            <div className="flex gap-4 text-xs text-gray-500">
                                <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                                    <span>Load</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-red-500/50"></div>
                                    <span>Cap</span>
                                </div>
                            </div>
                        </div>
                        <div className="h-[320px]">
                            <TrendLineChart data={trendData} cap={data.today?.cap || 8.0} height={320} />
                        </div>
                    </div>

                    {/* Config Panel */}
                    <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
                        <h2 className="text-lg font-medium mb-6">Configuration</h2>
                        <div className="space-y-4">
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-400">Safety Cap</span>
                                <span className="text-lg font-medium">{data.config?.CAP}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-400">Alpha Factor</span>
                                <span className="text-lg font-medium">{data.config?.ALPHA}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-400">Beta Factor</span>
                                <span className="text-lg font-medium">{data.config?.BETA}</span>
                            </div>
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-400">Switch Cost</span>
                                <span className="text-lg font-medium">{data.config?.SWITCH_COST}</span>
                            </div>
                        </div>

                        {/* Status Summary */}
                        <div className={`mt-6 p-4 rounded-lg ${theme.bg}/10 border ${theme.border}`}>
                            <p className="text-xs text-gray-400 mb-1">System Status</p>
                            <p className={`text-sm ${theme.color}`}>
                                {data.today?.adjusted_load < data.today?.cap
                                    ? "Operating within safe limits"
                                    : "Capacity exceeded - consider rescheduling"}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Calendar Section */}
                <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-6">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
                        <div>
                            <h2 className="text-lg font-medium">Load Calendar</h2>
                            <p className="text-sm text-gray-500 mt-1">Daily capacity heatmap</p>
                        </div>
                        <div className="flex items-center gap-2 bg-gray-800 rounded-lg p-1">
                            <button
                                onClick={() => changeMonth(-1)}
                                className="p-2 hover:bg-gray-700 rounded-md transition-colors text-gray-400"
                            >
                                ◀
                            </button>
                            <span className="px-4 py-1 text-sm font-medium min-w-[140px] text-center">
                                {currentMonth.toLocaleString('default', { month: 'long', year: 'numeric' })}
                            </span>
                            <button
                                onClick={() => changeMonth(1)}
                                className="p-2 hover:bg-gray-700 rounded-md transition-colors text-gray-400"
                            >
                                ▶
                            </button>
                        </div>
                    </div>
                    <HeatMapCalendar month={currentMonth} refreshKey={refreshKey} onDayClick={(date) => console.log("Date clicked:", date)} />
                </div>
            </div>
        </div>
    );
}
