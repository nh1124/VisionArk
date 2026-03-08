"use client";

import { usePathname, useRouter } from "next/navigation";
import { Inbox, Star, Calendar, CheckSquare, Sun, Folder, AlarmClock } from "lucide-react";
import { useTaskStore, TaskFilter } from "../store/useTaskStore";
import { getLocalDateString } from "../lib/dateUtils";
import { useMemo, useEffect, ReactNode } from "react";

interface TaskSidebarProps {
    isCollapsed: boolean;
}

export default function TaskSidebar({ isCollapsed }: TaskSidebarProps) {
    const pathname = usePathname();
    const router = useRouter();
    const { allTasks, activeFilter, setActiveFilter, activeProject, fetchAllTasks, viewMode } = useTaskStore();
    const todayStr = getLocalDateString();

    // Fetch all tasks once on mount to populate counts
    useEffect(() => {
        fetchAllTasks();
    }, [fetchAllTasks]);

    const counts = useMemo(() => {
        const pending = allTasks.filter(t => t.status !== 'done' && t.status !== 'skipped' && t.status !== 'completed');
        return {
            inbox: pending.length,
            today: pending.filter(t => t.due_date === todayStr).length,
            "my-day": pending.filter(t => t.meta_payload?.is_my_day).length,
            planned: pending.filter(t => t.due_date && t.due_date > todayStr).length,
            overdue: pending.filter(t => t.due_date && t.due_date < todayStr).length,
        };
    }, [allTasks, todayStr]);

    const projects = useMemo(() => {
        const contexts = Array.from(new Set(allTasks.map(t => t.context).filter(Boolean)));
        return contexts.sort();
    }, [allTasks]);

    const mainCategories: { id: TaskFilter; label: string; icon: ReactNode; count?: number }[] = [
        { id: "today", label: "Today", icon: <Sun size={18} />, count: counts.today },
        { id: "my-day", label: "My Day", icon: <Star size={18} />, count: counts["my-day"] },
        { id: "planned", label: "Planned", icon: <Calendar size={18} />, count: counts.planned },
        { id: "overdue", label: "Overdue", icon: <AlarmClock size={18} />, count: counts.overdue },
        { id: "inbox", label: "Inbox", icon: <Inbox size={18} />, count: counts.inbox },
    ];


    return (
        <div className="flex flex-col gap-6 py-4 animate-in fade-in duration-300">
            {!isCollapsed && (
                <div className="mx-3 space-y-1">
                    <button
                        onClick={() => router.push("/tasks")}
                        className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-base transition-colors ${pathname === "/tasks" ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
                    >
                        <CheckSquare size={17} />
                        <span>Task List</span>
                    </button>
                    <button
                        onClick={() => router.push("/tasks/calendar")}
                        className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-base transition-colors ${pathname.startsWith("/tasks/calendar") ? "bg-cyan-500/12 text-cyan-300" : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"}`}
                    >
                        <Calendar size={17} />
                        <span>Calendar</span>
                    </button>
                </div>
            )}

            {/* Top Border for Visual Separation */}
            {/* Top Border for Visual Separation - Only show for List View */}
            {viewMode === "list" && (
                <div className="mx-3 border-t border-gray-800/50 pt-4">
                    <div className="space-y-1">
                        {mainCategories.map((cat) => (
                            <button
                                key={cat.id}
                                onClick={() => setActiveFilter(cat.id)}
                                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-base font-semibold transition-all ${isCollapsed ? "justify-center" : ""
                                    } ${activeFilter === cat.id
                                        ? "bg-blue-600/10 text-blue-400"
                                        : "text-gray-400 hover:bg-gray-800/50 hover:text-gray-200"
                                    }`}
                            >
                                <span className={activeFilter === cat.id ? "text-blue-400" : "text-gray-500"}>{cat.icon}</span>
                                {!isCollapsed && (
                                    <>
                                        <span className="flex-1 text-left">{cat.label}</span>
                                        {cat.count !== undefined && cat.count > 0 && (
                                            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${activeFilter === cat.id ? "bg-blue-600/20 text-blue-400" : "bg-gray-800 text-gray-500"
                                                }`}>
                                                {cat.count}
                                            </span>
                                        )}
                                    </>
                                )}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Projects Section */}
            {!isCollapsed && (
                <div className="px-3 space-y-1">
                    <h4 className="px-3 text-[10px] font-black text-gray-600 uppercase tracking-widest mb-2">Projects</h4>

                    {/* All Tasks Button */}
                    <button
                        onClick={() => setActiveFilter("inbox")}
                        className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-semibold transition-all ${!activeProject
                            ? "bg-gray-800 text-white"
                            : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/40"
                            }`}
                    >
                        <Inbox size={14} className={!activeProject ? "text-blue-400" : "text-gray-600"} />
                        <span className="truncate flex-1 text-left">All Tasks</span>
                    </button>

                    {projects.map((ctx) => (
                        <button
                            key={ctx}
                            onClick={() => setActiveFilter("project", ctx)}
                            className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-semibold transition-all ${activeFilter === "project" && activeProject === ctx
                                ? "bg-gray-800 text-cyan-400"
                                : "text-gray-500 hover:text-gray-300 hover:bg-gray-900/40"
                                }`}
                        >
                            <Folder size={14} className={activeFilter === "project" && activeProject === ctx ? "text-cyan-400" : "text-gray-600"} />
                            <span className="truncate flex-1 text-left">{ctx}</span>
                        </button>
                    ))}
                </div>
            )}

        </div>
    );
}
