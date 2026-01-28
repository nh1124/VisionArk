"use client";

import { usePathname } from "next/navigation";
import { Inbox, Star, Calendar, CheckSquare, Sun, Folder } from "lucide-react";
import { useTaskStore, TaskFilter } from "../store/useTaskStore";
import { useMemo, useEffect, ReactNode } from "react";

interface TaskSidebarProps {
    isCollapsed: boolean;
}

export default function TaskSidebar({ isCollapsed }: TaskSidebarProps) {
    const { tasks, allTasks, activeFilter, setActiveFilter, activeProject, fetchAllTasks } = useTaskStore();
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

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
        { id: "inbox", label: "Inbox", icon: <Inbox size={18} />, count: counts.inbox },
    ];

    const integrations = [
        { id: "google", label: "Google Calendar", active: true },
        { id: "outlook", label: "Outlook", active: false },
    ];

    return (
        <div className="flex flex-col gap-6 py-4 animate-in fade-in duration-300">
            {/* Top Border for Visual Separation */}
            <div className="mx-3 border-t border-gray-800/50 pt-4">
                <div className="space-y-1">
                    {mainCategories.map((cat) => (
                        <button
                            key={cat.id}
                            onClick={() => setActiveFilter(cat.id)}
                            className={`w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-bold transition-all ${isCollapsed ? "justify-center" : ""
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

            {/* Projects Section */}
            {!isCollapsed && projects.length > 0 && (
                <div className="px-3 space-y-1">
                    <h4 className="px-3 text-[10px] font-black text-gray-600 uppercase tracking-widest mb-2">Projects</h4>
                    {projects.map((ctx) => (
                        <button
                            key={ctx}
                            onClick={() => setActiveFilter("project", ctx)}
                            className={`w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${activeFilter === "project" && activeProject === ctx
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

            {/* Integrations Toggle Area */}
            {!isCollapsed && (
                <div className="px-3 space-y-4">
                    <div className="px-3">
                        <h4 className="text-[10px] font-black text-gray-600 uppercase tracking-widest mb-4">Integrations</h4>
                        <div className="space-y-3">
                            {integrations.map((ext) => (
                                <div key={ext.id} className="flex items-center justify-between group">
                                    <span className="text-xs font-bold text-gray-500 group-hover:text-gray-400 transition-colors">{ext.label}</span>
                                    <div className={`w-8 h-4 rounded-full relative cursor-pointer transition-colors ${ext.active ? 'bg-cyan-500/50' : 'bg-gray-800'}`}>
                                        <div className={`absolute top-0.5 w-3 h-3 bg-white rounded-full shadow-sm transition-all ${ext.active ? 'right-0.5' : 'left-0.5'}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
