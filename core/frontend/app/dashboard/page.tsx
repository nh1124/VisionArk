"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import HeatMapCalendar from "@/components/HeatMapCalendar";
import HubSuggestionBanner from "@/components/HubSuggestionBanner";
import ScheduleView from "@/components/ScheduleView";
import { suggestSchedule, ScheduleResult } from "@/lib/schedule";

interface DashboardData {
    today: {
        adjusted_load: number;
        level: string;
        task_count: number;
        unique_contexts: number;
        cap: number;
        tasks: Array<{
            task_id: string;
            task_name: string;
            context: string;
            load: number;
            status?: string;
        }>;
    };
    weekly: {
        average_load: number;
        over_days: number;
        recovery_rate: number;
    };
}

export default function DashboardPage() {
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [refreshKey, setRefreshKey] = useState(0);
    const [selectedDate, setSelectedDate] = useState<string | null>(null);
    const [dayDetails, setDayDetails] = useState<any>(null);
    const [scheduleData, setScheduleData] = useState<ScheduleResult | null>(null);
    const [scheduleLoading, setScheduleLoading] = useState(false);

    useEffect(() => {
        const loadAllData = async () => {
            setLoading(true);
            setScheduleLoading(true);
            try {
                const dashRes = await apiFetch("/api/lbs/dashboard");
                const dashData = await dashRes.json();
                setData(dashData);

                // Fetch schedule suggestion
                try {
                    const schedule = await suggestSchedule({ fatigue: 0 });
                    setScheduleData(schedule);
                } catch (schedErr) {
                    console.error("Error loading schedule:", schedErr);
                }
            } catch (error) {
                console.error("Error loading dashboard data:", error);
            } finally {
                setLoading(false);
                setScheduleLoading(false);
            }
        };
        loadAllData();
    }, [refreshKey]);

    useEffect(() => {
        if (selectedDate) {
            fetchDayDetails(selectedDate);
        }
    }, [selectedDate]);

    const fetchDayDetails = async (dateStr: string) => {
        try {
            const res = await apiFetch(`/api/lbs/calculate/${dateStr}`);
            const detailJson = await res.json();

            // Fetch tasks for that day to show in list
            const taskRes = await apiFetch(`/api/lbs/tasks?target_date=${dateStr}`);
            const taskJson = await taskRes.json();

            setDayDetails({
                ...detailJson,
                tasks: taskJson
            });
        } catch (error) {
            console.error("Error fetching day details:", error);
        }
    };

    const changeMonth = (delta: number) => {
        setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
    };

    const getLoadStatus = (pct: number) => {
        if (pct <= 60) return { label: "Focus", color: "text-emerald-400", bg: "bg-emerald-500", border: "border-emerald-500/30" };
        if (pct <= 90) return { label: "Flow", color: "text-blue-400", bg: "bg-blue-500", border: "border-blue-500/30" };
        if (pct <= 110) return { label: "Peak", color: "text-orange-400", bg: "bg-orange-500", border: "border-orange-500/30" };
        return { label: "Overload", color: "text-red-400", bg: "bg-red-500", border: "border-red-500/30" };
    };

    const getRecoveryStatus = (score: number) => {
        if (score <= 30) return { label: "Low", color: "text-red-400" };
        if (score <= 70) return { label: "Recovering", color: "text-orange-400" };
        return { label: "Ready", color: "text-emerald-400" };
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

    const loadPercentageActual = data.today ? (data.today.adjusted_load / data.today.cap) * 100 : 0;
    const loadStatus = getLoadStatus(loadPercentageActual);
    const recoveryStatus = getRecoveryStatus(data.weekly?.recovery_rate || 0);

    return (
        <div className="min-h-screen bg-gray-950 text-white p-6 lg:p-8">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex justify-between items-center mb-8 hidden sm:flex">
                    <div>
                        <h1 className="text-3xl font-bold text-white tracking-tight">Dashboard</h1>
                        <p className="text-gray-500 text-sm mt-1">Human State OS / Personal Load Balance</p>
                    </div>
                    <button
                        onClick={() => setRefreshKey(k => k + 1)}
                        className="px-5 py-2.5 bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-xl transition-all text-sm text-gray-300 font-medium flex items-center gap-2 shadow-sm"
                    >
                        <span>↺</span> Refresh
                    </button>
                </div>

                {/* Hub Proactive Suggestions */}
                <HubSuggestionBanner onRefresh={() => setRefreshKey(k => k + 1)} />

                {/* Primary Metrics */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    {/* Load Capacity - Main Card */}
                    <div className={`md:col-span-2 bg-gray-900/40 border-2 ${loadStatus.border} rounded-2xl p-8 relative overflow-hidden backdrop-blur-sm shadow-xl`}>
                        <div className="relative z-10">
                            <div className="flex items-center justify-between mb-6">
                                <span className="text-sm font-bold text-gray-400 uppercase tracking-widest">Current State</span>
                                <span className={`text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-widest ${loadStatus.bg}/20 ${loadStatus.color}`}>
                                    LBS Core
                                </span>
                            </div>
                            <div className="flex items-baseline gap-4 mb-6">
                                <span className={`text-6xl font-bold tracking-tight ${loadStatus.color}`}>{loadStatus.label}</span>
                                <span className="text-xs font-medium text-gray-500 tabular-nums">({loadPercentageActual.toFixed(0)}%)</span>
                            </div>
                            <div className="h-3 bg-gray-800/50 rounded-full overflow-hidden mb-4">
                                <div
                                    className={`h-full rounded-full transition-all duration-1000 ease-out ${loadStatus.bg}`}
                                    style={{ width: `${Math.min(100, loadPercentageActual)}%` }}
                                />
                            </div>
                            <div className="flex justify-between text-[10px] font-bold text-gray-600 uppercase tracking-wider">
                                <span>{data.today?.adjusted_load.toFixed(1)} / {data.today?.cap} load units</span>
                            </div>
                        </div>
                        {/* Decorative background glow */}
                        <div className={`absolute -right-20 -bottom-20 w-64 h-64 rounded-full blur-[100px] opacity-10 ${loadStatus.bg}`} />
                    </div>

                    {/* Weekly Recovery */}
                    <div className="md:col-span-2 bg-gray-900/40 border-2 border-gray-800 rounded-2xl p-8 backdrop-blur-sm shadow-xl">
                        <span className="text-sm font-bold text-gray-400 uppercase tracking-widest">Recovery Level</span>
                        <div className="mt-8 flex items-baseline gap-3">
                            <span className={`text-5xl font-bold tracking-tight ${recoveryStatus.color}`}>{recoveryStatus.label}</span>
                            <span className="text-sm font-medium text-gray-600 tabular-nums">{data.weekly?.recovery_rate.toFixed(0)}%</span>
                        </div>
                        <p className="text-xs font-bold text-gray-600 mt-4 uppercase">Efficiency Context</p>
                        <div className="mt-8 flex gap-1.5">
                            {[1, 2, 3, 4, 5, 6, 7].map(i => (
                                <div
                                    key={i}
                                    className={`h-2 flex-1 rounded-full ${i <= (data.weekly?.over_days || 0) ? 'bg-red-500/50 shadow-[0_0_10px_rgba(239,68,68,0.2)]' : 'bg-emerald-500/30'}`}
                                />
                            ))}
                        </div>
                        <p className="text-[10px] font-bold text-gray-600 mt-3 uppercase tracking-wider">Days over capacity this week</p>
                    </div>
                </div>

                {/* Dynamic Schedule */}
                <div className="mb-8">
                    {scheduleLoading ? (
                        <div className="bg-gray-900/40 border-2 border-gray-800 rounded-2xl p-8 text-center">
                            <div className="text-gray-500 animate-pulse">Loading schedule...</div>
                        </div>
                    ) : scheduleData ? (
                        <ScheduleView
                            schedule={scheduleData.schedule}
                            overflow={scheduleData.overflow}
                            shutdownTime={scheduleData.shutdown_time}
                            fatigueLevel={scheduleData.fatigue_level}
                            className="border-2 border-gray-800"
                        />
                    ) : (
                        <div className="bg-gray-900/40 border-2 border-gray-800 rounded-2xl p-8 text-center text-gray-500">
                            Could not load schedule
                        </div>
                    )}
                </div>

                {/* LBS Calendar */}
                <div className="bg-gray-900/40 border-2 border-gray-800 rounded-2xl p-6 backdrop-blur-sm shadow-xl relative">
                    <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
                        <div>
                            <h2 className="text-lg font-medium tracking-tight text-gray-200">LBS Calendar</h2>
                        </div>

                        <div className="flex items-center gap-4">
                            {/* Month Selector */}
                            <div className="flex items-center gap-1 bg-gray-900 border border-gray-800 rounded-xl p-1 shadow-inner">
                                <button
                                    onClick={() => changeMonth(-1)}
                                    className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-500 font-bold"
                                >
                                    ◀
                                </button>
                                <span className="px-6 py-1.5 text-xs font-bold min-w-[160px] text-center uppercase tracking-widest text-gray-200">
                                    {currentMonth.toLocaleString('en-US', { month: 'long', year: 'numeric' })}
                                </span>
                                <button
                                    onClick={() => changeMonth(1)}
                                    className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-500 font-bold"
                                >
                                    ▶
                                </button>
                            </div>
                        </div>
                    </div>

                    <HeatMapCalendar
                        month={currentMonth}
                        refreshKey={refreshKey}
                        includeCompleted={true}
                        onDayClick={(date) => setSelectedDate(date)}
                    />
                </div>
            </div>

            {/* Detailed Log Modal */}
            {selectedDate && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                    <div
                        className="absolute inset-0 bg-black/80 backdrop-blur-md"
                        onClick={() => setSelectedDate(null)}
                    />
                    <div className="relative bg-gray-900 border-2 border-gray-800 rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
                        {/* Modal Header */}
                        <div className="p-8 border-b border-gray-800 flex justify-between items-start font-display">
                            <div>
                                <p className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.3em] mb-2">Detailed Log</p>
                                <h3 className="text-3xl font-bold tracking-tight">
                                    {new Date(selectedDate).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
                                </h3>
                            </div>
                            <button
                                onClick={() => setSelectedDate(null)}
                                className="p-2 hover:bg-gray-800 rounded-xl text-gray-500 transition-colors"
                            >
                                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>

                        {/* Modal Content */}
                        <div className="p-8 overflow-y-auto custom-scrollbar">
                            {dayDetails ? (
                                <div className="space-y-10">
                                    <div className="grid grid-cols-3 gap-4 font-display">
                                        <div className="bg-gray-800/30 border border-gray-700/50 rounded-2xl p-5">
                                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2 block">Total Load</span>
                                            <span className="text-3xl font-bold text-emerald-400 tabular-nums">
                                                {dayDetails.adjusted_load.toFixed(2)}
                                            </span>
                                        </div>
                                        <div className="bg-gray-800/30 border border-gray-700/50 rounded-2xl p-5">
                                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2 block">Tasks</span>
                                            <span className="text-3xl font-bold text-white tabular-nums">
                                                {dayDetails.tasks_count || dayDetails.tasks?.length || 0}
                                            </span>
                                        </div>
                                        <div className="bg-gray-800/30 border border-gray-700/50 rounded-2xl p-5">
                                            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2 block">Contexts</span>
                                            <span className="text-3xl font-bold text-blue-400 tabular-nums">
                                                {dayDetails.contexts_count || new Set(dayDetails.tasks?.map((t: any) => t.context)).size}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Load Breakdown */}
                                    <div>
                                        <div className="flex items-center gap-2 mb-4">
                                            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                            </svg>
                                            <h4 className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em]">Load Calculation Breakdown</h4>
                                        </div>
                                        <div className="bg-gray-950 border-2 border-emerald-500/30 rounded-2xl p-6 space-y-4">
                                            <div className="flex justify-between items-center text-sm">
                                                <span className="text-gray-400">Base Task Scores (Sum)</span>
                                                <span className="font-bold tabular-nums">{(dayDetails.raw_load || 0).toFixed(2)}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm italic">
                                                <span className="text-gray-500">+ Task Count Multiplier (α * N^β)</span>
                                                <span className="font-bold tabular-nums">{(dayDetails.multiplier_penalty || (dayDetails.adjusted_load - (dayDetails.raw_load || 0) - (dayDetails.context_switch_penalty || 0))).toFixed(2)}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-sm italic">
                                                <span className="text-gray-500">+ Context Switch Cost (Cost * (C-1))</span>
                                                <span className="font-bold tabular-nums">{(dayDetails.context_switch_penalty || 0).toFixed(2)}</span>
                                            </div>
                                            <div className="pt-4 border-t border-gray-800 flex justify-between items-center font-display">
                                                <span className="text-lg font-bold">Final Adjusted Load</span>
                                                <span className="text-2xl font-bold text-emerald-400 tabular-nums">{dayDetails.adjusted_load.toFixed(2)}</span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Scheduled Tasks */}
                                    <div>
                                        <h4 className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] mb-4">Scheduled Tasks</h4>
                                        <div className="space-y-3">
                                            {dayDetails.tasks && dayDetails.tasks.length > 0 ? (
                                                dayDetails.tasks.map((task: any) => (
                                                    <div
                                                        key={task.task_id}
                                                        className="group bg-gray-800/20 border border-gray-800 hover:border-emerald-500/30 rounded-2xl p-5 flex items-center justify-between transition-all"
                                                    >
                                                        <div className="flex flex-col gap-1">
                                                            <span className={`font-bold tracking-tight ${task.status === 'done' ? 'text-gray-600 line-through' : 'text-gray-200'}`}>
                                                                {task.task_name}
                                                            </span>
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-[8px] font-black uppercase tracking-widest text-gray-600">
                                                                    {task.context}
                                                                </span>
                                                                {task.status === 'done' && (
                                                                    <span className="text-[8px] font-black uppercase px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">Done</span>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-6">
                                                            <span className="text-sm font-bold text-gray-500 bg-gray-900/50 px-3 py-1.5 rounded-lg tabular-nums">
                                                                {task.load?.toFixed(1) || task.base_load_score?.toFixed(1)}
                                                            </span>
                                                            <div className="flex items-center gap-2 opacity-50 group-hover:opacity-100 transition-opacity">
                                                                <button className={`p-2 rounded-lg border transition-all ${task.status === 'done' ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400' : 'bg-gray-800 border-gray-700 hover:border-emerald-500/50 text-gray-500'}`}>
                                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                                                    </svg>
                                                                </button>
                                                                <button className="p-2 bg-gray-800 border border-gray-700 rounded-lg hover:border-red-500/50 text-gray-500 transition-all">
                                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                                    </svg>
                                                                </button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                ))
                                            ) : (
                                                <div className="text-center py-12 bg-gray-800/10 border border-dashed border-gray-800 rounded-3xl">
                                                    <p className="text-sm font-bold text-gray-600 uppercase tracking-widest">No tasks scheduled for this day</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center py-20 space-y-4">
                                    <div className="w-12 h-12 border-4 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin" />
                                    <p className="text-xs font-black text-gray-600 uppercase tracking-widest">Processing Data...</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <style jsx global>{`
                .custom-scrollbar::-webkit-scrollbar {
                    width: 6px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: transparent;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background: #1f2937;
                    border-radius: 10px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: #374151;
                }
            `}</style>
        </div>
    );
}
