"use client";

import React from "react";
import {
    Plus,
    RefreshCw,
    Calendar,
    ChevronDown,
    ChevronRight,
    ChevronLeft,
    MoreVertical,
    Download,
    Upload,
    Circle
} from "lucide-react";
import TaskRow from "../components/TaskRow";
import { useTasksLogic } from "../hooks/useTasksLogic";
import GridCalendar from "@/components/GridCalendar";
import { getSpokeColor } from "@/lib/colors";
import type { TaskFilter } from "@/store/useTaskStore";

type TasksLogic = ReturnType<typeof useTasksLogic>;

export default function MobileTasksView({ logic }: { logic: TasksLogic }) {
    const {
        loading,
        isCalendarPage,
        activeFilter,
        targetDate,
        currentMonth,
        refreshKey,
        pendingTasks,
        completedTasksList,
        groupedTasks,
        displayTasks,
        isCompletedCollapsed,
        isDayDetailsOpen,
        dayDetailsDate,
        todayStr,
        setIsCompletedCollapsed,
        setTargetDate,
        setDayDetailsDate,
        setIsDayDetailsOpen,
        handleMarkDone,
        handleRowClick,
        handleRefresh,
        handlePrev,
        handleNext,
        handleToday,
        handleExportCSV,
        setCreateModalOpen,
        setImportModalOpen,
        stats,
        setActiveFilter,
        setQaDueDate,
        calendarTasks
    } = logic;

    const filters: { id: TaskFilter; label: string }[] = [
        { id: 'today', label: 'Today' },
        { id: 'my-day', label: 'My Day' },
        { id: 'planned', label: 'Planned' },
        { id: 'overdue', label: 'Overdue' },
        { id: 'completed', label: 'Done' },
        { id: 'inbox', label: 'Inbox' }
    ];

    const formatDateHeader = (dateStr: string) => {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    };

    return (
        <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
            {/* Header Bar */}
            <div className="flex items-center justify-between px-4 pt-4 pb-2 border-b border-gray-900/50">
                <h2 className="text-sm font-semibold text-gray-200">{isCalendarPage ? "Calendar" : "Tasks"}</h2>
                <div className="flex items-center gap-1">
                    <button onClick={handleRefresh} className="p-2 text-gray-500 hover:text-white transition-colors">
                        <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                    </button>
                    <div className="relative group">
                        <button className="p-2 text-gray-500 hover:text-white transition-colors">
                            <MoreVertical size={16} />
                        </button>
                        <div className="absolute right-0 top-full mt-1 w-40 bg-gray-900 border border-gray-800 rounded-xl shadow-2xl z-50 py-1 hidden group-hover:block transition-all">
                            <button onClick={() => setImportModalOpen(true)} className="w-full px-4 py-3 flex items-center gap-3 text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors">
                                <Upload size={14} /> Import CSV
                            </button>
                            <button onClick={handleExportCSV} className="w-full px-4 py-3 flex items-center gap-3 text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors">
                                <Download size={14} /> Export CSV
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* View-Specific Sub-Header */}
            <div className="px-4 py-3 flex items-center justify-between border-b border-gray-900/30">
                <div className="flex items-center gap-2">
                    <h2 className="text-[13px] font-bold text-white">
                        {isCalendarPage
                            ? currentMonth.toLocaleString('en-US', { month: 'short', year: 'numeric' })
                            : activeFilter === 'today' ? formatDateHeader(targetDate) : activeFilter.charAt(0).toUpperCase() + activeFilter.slice(1)
                        }
                    </h2>
                    {!isCalendarPage && activeFilter === 'today' && (
                        <span className="text-[10px] font-black text-gray-600 uppercase tracking-widest">{stats.done}/{stats.total}</span>
                    )}
                </div>

                <div className="flex items-center gap-1 bg-gray-900/50 rounded-lg p-0.5 border border-gray-800/50">
                    <button onClick={handlePrev} className="p-1 px-2 text-gray-500 hover:text-white"><ChevronLeft size={16} /></button>
                    <button onClick={handleToday} className="px-2 text-[10px] font-black uppercase text-gray-500 hover:text-white border-x border-gray-800">Today</button>
                    <button onClick={handleNext} className="p-1 px-2 text-gray-500 hover:text-white"><ChevronRight size={16} /></button>
                </div>
            </div>

            {/* List Mode Filters */}
            {!isCalendarPage && (
                <div className="flex overflow-x-auto no-scrollbar gap-2 px-4 py-3 bg-gray-950/50 border-b border-gray-900/20">
                    {filters.map(f => (
                        <button
                            key={f.id}
                            onClick={() => setActiveFilter(f.id)}
                            className={`whitespace-nowrap px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest transition-all ${activeFilter === f.id ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 shadow-[0_0_10px_rgba(59,130,246,0.2)]" : "text-gray-500 border border-gray-800/50 hover:bg-gray-900"}`}
                        >
                            {f.label}
                        </button>
                    ))}
                </div>
            )}

            {/* Main View Area */}
            <div className="flex-1 overflow-y-auto scrolling-touch relative no-scrollbar">
                {!isCalendarPage ? (
                    <div className="px-3 py-4 space-y-4 pb-24">
                        {loading && displayTasks.length === 0 ? (
                            <div className="flex items-center justify-center py-20 animate-pulse">
                                <span className="text-[10px] font-black uppercase tracking-widest text-gray-600 italic">Synchronizing Workspace...</span>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {groupedTasks ? (
                                    groupedTasks.map(group => (
                                        <div key={group.date} className="space-y-2">
                                            <div className="flex items-center gap-2 px-1">
                                                <Calendar size={12} className="text-gray-600" />
                                                <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-600">
                                                    {group.date === todayStr ? 'Today' : group.date}
                                                </h4>
                                            </div>
                                            <div className="space-y-1">
                                                {group.tasks.map(task => (
                                                    <TaskRow key={task.task_id} task={task} isMobile={true} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                                ))}
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div className="space-y-1">
                                        {pendingTasks.map(task => (
                                            <TaskRow key={task.task_id} task={task} isMobile={true} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                        ))}
                                    </div>
                                )}

                                {completedTasksList.length > 0 && (
                                    <div className="mt-8">
                                        <button
                                            onClick={() => setIsCompletedCollapsed(!isCompletedCollapsed)}
                                            className="flex items-center gap-2 px-3 py-2 bg-gray-900/30 rounded-xl text-gray-500 hover:text-gray-400 transition-all mb-2"
                                        >
                                            {isCompletedCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                                            <span className="text-[10px] font-black uppercase tracking-wider">Completed {completedTasksList.length}</span>
                                        </button>
                                        {!isCompletedCollapsed && (
                                            <div className="space-y-1 animate-in fade-in slide-in-from-top-2 duration-300">
                                                {completedTasksList.map(task => (
                                                    <TaskRow key={task.task_id} task={task} isMobile={true} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="h-full">
                        <GridCalendar
                            month={currentMonth}
                            onDayClick={(date) => {
                                setTargetDate(date);
                                setDayDetailsDate(date);
                                setIsDayDetailsOpen(true);
                            }}
                            includeCompleted={true}
                            refreshKey={refreshKey}
                        />
                        {/* Day Details Modal for Mobile */}
                        {isDayDetailsOpen && (
                            <>
                                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[99]" onClick={() => setIsDayDetailsOpen(false)} />
                                <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 rounded-t-[2.5rem] h-[70vh] flex flex-col z-[100] animate-in slide-in-from-bottom-full duration-300">
                                    <div className="flex flex-col items-center pt-3 pb-2">
                                        <div className="w-12 h-1 bg-gray-800 rounded-full" />
                                    </div>
                                    <div className="p-6 pt-2 overflow-y-auto no-scrollbar">
                                        <div className="flex justify-between items-center mb-6">
                                            <div>
                                                <h3 className="text-[10px] font-black uppercase tracking-widest text-blue-400 mb-1">Focus List</h3>
                                                <p className="text-xl font-bold text-white">{formatDateHeader(dayDetailsDate)}</p>
                                            </div>
                                            <div className="p-4 bg-blue-600/10 rounded-2xl">
                                                <Calendar size={24} className="text-blue-500" />
                                            </div>
                                        </div>
                                        <div className="space-y-3">
                                            {calendarTasks.filter(t => t.due_date === dayDetailsDate).length === 0 ? (
                                                <div className="py-12 flex flex-col items-center justify-center opacity-40">
                                                    <Plus size={32} className="text-gray-600 mb-3" />
                                                    <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">Free Schedule</p>
                                                </div>
                                            ) : (
                                                calendarTasks.filter(t => t.due_date === dayDetailsDate).map(task => (
                                                    <div key={task.task_id} onClick={() => { handleRowClick(task); setIsDayDetailsOpen(false); }} className="bg-gray-950/60 border border-gray-800 p-5 rounded-2xl active:bg-gray-800 transition-all">
                                                        <div className="flex items-center gap-3 mb-3">
                                                            <div className={task.status === 'completed' ? 'text-blue-500' : 'text-gray-600'}>
                                                                <Circle size={18} fill={task.status === 'completed' ? 'currentColor' : 'none'} className={task.status === 'completed' ? 'opacity-20' : ''} />
                                                            </div>
                                                            <span className={`text-base font-bold ${task.status === 'completed' ? 'text-gray-500 line-through' : 'text-gray-200'}`}>{task.task_name}</span>
                                                        </div>
                                                        <div className="flex items-center justify-between pl-8">
                                                            <span className="text-[9px] font-black uppercase tracking-[0.2em]" style={{ color: getSpokeColor(task.context) }}>{task.context}</span>
                                                            <span className="text-[10px] font-bold text-gray-600 bg-gray-900 px-3 py-1 rounded-lg">Impact {task.base_load_score}</span>
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                    </div>
                                    <div className="p-6 pb-12 bg-gray-900 border-t border-gray-800/50">
                                        <button
                                            onClick={() => {
                                                setQaDueDate(dayDetailsDate);
                                                setCreateModalOpen(true);
                                                setIsDayDetailsOpen(false);
                                            }}
                                            className="w-full py-4 bg-blue-600 text-white rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] shadow-xl shadow-blue-600/20 active:scale-95 transition-all"
                                        >
                                            Add Priority Entry
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* Floating Action Button (FAB) */}
            <div className="fixed bottom-24 right-6 z-40">
                <button
                    onClick={() => setCreateModalOpen(true)}
                    className="w-16 h-16 bg-blue-600 hover:bg-blue-500 rounded-2xl flex items-center justify-center text-white shadow-2xl shadow-blue-600/40 transition-all active:scale-90"
                >
                    <Plus size={32} />
                </button>
            </div>

            <style jsx global>{`
                .no-scrollbar::-webkit-scrollbar {
                    display: none;
                }
                .no-scrollbar {
                    -ms-overflow-style: none;
                    scrollbar-width: none;
                }
            `}</style>
        </div>
    );
}
