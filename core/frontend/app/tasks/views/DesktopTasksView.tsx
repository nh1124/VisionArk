"use client";

import React from "react";
import {
    Plus,
    RefreshCw,
    CalendarDays,
    Calendar,
    ChevronDown,
    ChevronRight,
    ChevronLeft,
    List,
    Archive,
    Hash,
    X,
    CheckCircle2,
    Circle,
    Download,
    Upload
} from "lucide-react";
import GridCalendar from "@/components/GridCalendar";
import TimelineCalendar from "@/components/TimelineCalendar";
import TaskRow from "../components/TaskRow";
import { useTasksLogic } from "../hooks/useTasksLogic";
import { getSpokeColor } from "@/lib/colors";

type TasksLogic = ReturnType<typeof useTasksLogic>;

export default function DesktopTasksView({ logic }: { logic: TasksLogic }) {
    const {
        loading,
        targetDate,
        viewMode,
        activeFilter,
        calendarTasks,
        todayStr,
        dayDetailsDate,
        currentMonth,
        refreshKey,
        availableProjects,
        displayTasks,
        groupedTasks,
        pendingTasks,
        completedTasksList,
        isCompletedCollapsed,
        isDayDetailsOpen,
        quickAddName,
        quickAddLoading,
        quickAddFocused,
        activeOptions,
        qaContext,
        qaLoadScore,
        qaDueDate,
        quickAddRef,
        qaDateRef,
        setViewMode,
        setIsCompletedCollapsed,
        setTargetDate,
        setDayDetailsDate,
        setIsDayDetailsOpen,
        setQuickAddName,
        setQuickAddFocused,
        setActiveOptions,
        setQaContext,
        setQaLoadScore,
        setQaDueDate,
        setCreateModalOpen,
        setImportModalOpen,
        handleMarkDone,
        handleQuickAdd,
        handlePrev,
        handleNext,
        handleToday,
        handleExportCSV,
        handleRefresh,
        handleRowClick
    } = logic;

    const formatDateHeader = (dateStr: string) => {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    };

    return (
        <div className="w-full px-10 py-12 flex-1 flex flex-col min-h-0 overflow-hidden transition-all duration-500">
            {/* Background Style */}
            <div className={`fixed inset-0 ${viewMode === 'list' ? 'bg-gradient-to-b from-blue-900/20 to-gray-950' : 'bg-gray-950'} -z-10`} />

            {/* Header */}
            <div className="flex justify-between items-center mb-10">
                <div className="flex items-center gap-3">
                    <div className="flex flex-col items-start gap-2">
                        <div className="flex items-center gap-3">
                            {viewMode !== 'list' && (
                                <div className="flex items-center gap-1 bg-gray-900/60 border border-gray-800 rounded-xl p-1 shadow-lg">
                                    <button onClick={handlePrev} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-all"><ChevronLeft className="w-4 h-4" /></button>
                                    <button onClick={handleToday} className="px-3 py-1 text-[10px] font-black uppercase text-gray-500 hover:text-white transition-all border-x border-gray-800">Today</button>
                                    <button onClick={handleNext} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-all"><ChevronRight className="w-4 h-4" /></button>
                                </div>
                            )}
                            <h1 className="text-lg font-medium text-white whitespace-nowrap min-w-[300px]">
                                {viewMode === 'calendar'
                                    ? currentMonth.toLocaleString('en-US', { month: 'long', year: 'numeric' })
                                    : activeFilter === 'today' ? formatDateHeader(targetDate) : ""
                                }
                            </h1>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-0.5 bg-gray-900/80 border border-gray-800 rounded-xl p-1 shadow-lg">
                        <button onClick={() => setViewMode("list")} className={`p-2 rounded-lg transition-all ${viewMode === "list" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}><List className="w-4 h-4" /></button>
                        <button onClick={() => setViewMode("calendar")} className={`p-2 rounded-lg transition-all ${viewMode === "calendar" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}><CalendarDays className="w-4 h-4" /></button>
                        <button onClick={() => setViewMode("timeline")} className={`p-2 rounded-lg transition-all ${viewMode === "timeline" ? 'bg-blue-600 text-white shadow-inner' : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}><Calendar className="w-4 h-4" /></button>
                    </div>

                    <div className="flex items-center gap-2">
                        <button onClick={() => setImportModalOpen(true)} className="p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg"><Upload className="w-5 h-5" /></button>
                        <button onClick={handleExportCSV} className="p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg"><Download className="w-5 h-5" /></button>
                        <button onClick={handleRefresh} className="p-2.5 bg-gray-900/80 border border-gray-800 rounded-xl hover:bg-gray-800 transition-all text-gray-400 hover:text-white shadow-lg"><RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} /></button>
                    </div>
                </div>
            </div>

            {/* Main Content Area */}
            <div className={`flex-1 overflow-hidden relative ${viewMode === "list" ? 'max-w-5xl mx-auto w-full' : 'w-full'}`}>
                <div className={`absolute inset-0 ${(viewMode === 'list' || viewMode === 'calendar') ? 'overflow-y-auto' : 'overflow-hidden'} custom-scrollbar px-1 pb-40`}>
                    {viewMode === "list" ? (
                        <div className="space-y-6">
                            {loading && displayTasks.length === 0 ? (
                                <div className="text-center py-20 text-gray-600 font-bold animate-pulse uppercase tracking-widest text-sm">Synchronizing Tasks...</div>
                            ) : (
                                <div className="space-y-4">
                                    {groupedTasks ? (
                                        groupedTasks.map(group => (
                                            <div key={group.date} className="space-y-1">
                                                <div className="flex items-center gap-2 px-3 py-1">
                                                    <Calendar className="w-3.5 h-3.5 text-gray-500" />
                                                    <h4 className="text-[10px] font-black uppercase tracking-widest text-gray-500">{group.date === todayStr ? 'Today' : group.date}</h4>
                                                </div>
                                                {group.tasks.map(task => (
                                                    <TaskRow key={`${task.task_id}-${task.due_date}`} task={task} isMobile={false} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                                ))}
                                            </div>
                                        ))
                                    ) : (
                                        <div className="space-y-1">
                                            {pendingTasks.map(task => (
                                                <TaskRow key={task.task_id} task={task} isMobile={false} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                            ))}
                                        </div>
                                    )}

                                    {completedTasksList.length > 0 && (
                                        <div className="mt-6">
                                            <button onClick={() => setIsCompletedCollapsed(!isCompletedCollapsed)} className="flex items-center gap-2 px-3 py-1.5 bg-gray-900/50 hover:bg-gray-900/80 rounded-lg text-gray-500 hover:text-gray-300 transition-all group mb-2">
                                                {isCompletedCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                                                <span className="text-xs font-bold uppercase tracking-wider">Completed {completedTasksList.length}</span>
                                            </button>
                                            {!isCompletedCollapsed && (
                                                <div className="space-y-1 animate-in fade-in slide-in-from-top-2 duration-300">
                                                    {completedTasksList.map(task => (
                                                        <TaskRow key={`${task.task_id}-${task.due_date}`} task={task} isMobile={false} onToggle={() => handleMarkDone(task.task_id, task.status || 'todo', task.due_date || undefined)} onClick={() => handleRowClick(task)} />
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Quick Add */}
                            <div className={`mt-4 bg-gray-900/40 border border-gray-800/50 rounded-xl transition-all duration-300 ${quickAddFocused ? 'bg-gray-900/60 ring-1 ring-blue-500/50 shadow-lg shadow-blue-500/5' : 'hover:bg-gray-900/60'}`} ref={quickAddRef}>
                                <div className="flex flex-col">
                                    <div className="flex items-center gap-3 px-4 py-3">
                                        <Plus className={`w-5 h-5 ${quickAddFocused ? 'text-blue-500' : 'text-gray-500'}`} />
                                        <input
                                            type="text"
                                            placeholder="Add a task"
                                            value={quickAddName}
                                            onChange={(e) => setQuickAddName(e.target.value)}
                                            onFocus={() => { setQuickAddFocused(true); setActiveOptions(true); }}
                                            onKeyDown={(e) => e.key === 'Enter' && handleQuickAdd()}
                                            disabled={quickAddLoading}
                                            className="flex-1 bg-transparent border-none focus:ring-0 font-semibold placeholder:text-gray-600 outline-none text-sm"
                                        />
                                        {quickAddName && (
                                            <button onClick={handleQuickAdd} disabled={quickAddLoading} className="p-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg transition-all shadow-lg active:scale-95">
                                                {quickAddLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ChevronDown className="-rotate-90 w-3.5 h-3.5" />}
                                            </button>
                                        )}
                                    </div>
                                    {(activeOptions || quickAddName) && quickAddFocused && (
                                        <div className="px-4 pb-3 pt-1 flex items-center gap-2 animate-in slide-in-from-top-1 duration-200 border-t border-gray-800/30 mt-1">
                                            <div className="relative group">
                                                <select value={qaContext} onChange={(e) => setQaContext(e.target.value)} className="absolute inset-0 opacity-0 cursor-pointer z-10">
                                                    {availableProjects.map(s => <option key={s} value={s}>{s}</option>)}
                                                </select>
                                                <button className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-blue-400 transition-all"><Archive className="w-3 h-3" />{qaContext}</button>
                                            </div>
                                            <div className="relative group">
                                                <select value={qaLoadScore} onChange={(e) => setQaLoadScore(parseFloat(e.target.value))} className="absolute inset-0 opacity-0 cursor-pointer z-10">
                                                    {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n}</option>)}
                                                </select>
                                                <button className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-green-400 transition-all"><Hash className="w-3 h-3" />{qaLoadScore}</button>
                                            </div>
                                            <div className="relative group">
                                                <input ref={qaDateRef} type="date" value={qaDueDate} onChange={(e) => setQaDueDate(e.target.value)} className="absolute inset-0 opacity-0 pointer-events-none" />
                                                <button onClick={() => qaDateRef.current?.showPicker()} className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-800/30 hover:bg-gray-800/60 rounded-lg text-[10px] font-bold uppercase tracking-wider text-gray-500 group-hover:text-amber-400 transition-all"><Calendar className="w-3 h-3" />{qaDueDate === targetDate ? "Today" : qaDueDate}</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : viewMode === "calendar" ? (
                        <div className="h-full relative">
                            <GridCalendar
                                month={currentMonth}
                                onDayClick={(date) => {
                                    setTargetDate(date);
                                    setDayDetailsDate(date);
                                    setIsDayDetailsOpen(true);
                                }}
                                includeCompleted={true}
                            />
                            {isDayDetailsOpen && (
                                <>
                                    <div className="fixed inset-0 bg-black/20 backdrop-blur-sm z-[99]" onClick={() => setIsDayDetailsOpen(false)} />
                                    <div className="fixed right-4 top-24 bottom-4 w-[400px] bg-gray-900/80 border border-gray-800 rounded-2xl flex flex-col min-h-0 animate-in slide-in-from-right-full duration-300 shadow-2xl backdrop-blur-2xl z-[100]">
                                        <div className="p-5 border-b border-gray-800/50 flex items-center justify-between bg-white/[0.02]">
                                            <div>
                                                <h3 className="text-xs font-black uppercase tracking-widest text-blue-400 mb-0.5">Focus List</h3>
                                                <p className="text-sm text-gray-400 font-bold">{formatDateHeader(dayDetailsDate)}</p>
                                            </div>
                                            <button onClick={() => setIsDayDetailsOpen(false)} className="p-2 hover:bg-gray-800 rounded-xl text-gray-500 hover:text-white transition-all bg-white/5"><X className="w-5 h-5" /></button>
                                        </div>
                                        <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-3">
                                            {calendarTasks.filter(t => t.due_date === dayDetailsDate).length === 0 ? (
                                                <div className="h-full flex flex-col items-center justify-center text-center p-12 opacity-40">
                                                    <div className="w-16 h-16 bg-gray-800/30 rounded-full flex items-center justify-center mb-6"><Plus className="w-8 h-8 text-gray-500" /></div>
                                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Clear Schedule</p>
                                                </div>
                                            ) : (
                                                calendarTasks.filter(t => t.due_date === dayDetailsDate).map(task => (
                                                    <div key={task.task_id} onClick={() => { handleRowClick(task); setIsDayDetailsOpen(false); }} className="group bg-gray-950/60 border border-gray-800/40 rounded-xl p-4 hover:bg-gray-900 hover:border-blue-500/30 transition-all cursor-pointer shadow-lg">
                                                        <div className="flex items-center gap-3 mb-2">
                                                            <div className={task.status === 'done' || task.status === 'completed' ? 'text-blue-500' : 'text-gray-600'}>{task.status === 'done' || task.status === 'completed' ? <CheckCircle2 size={18} /> : <Circle size={18} />}</div>
                                                            <span className={`text-[13px] font-bold truncate flex-1 ${task.status === 'done' || task.status === 'completed' ? 'line-through text-gray-500' : 'text-gray-200 group-hover:text-blue-400'}`}>{task.task_name}</span>
                                                        </div>
                                                        <div className="flex items-center justify-between pl-8">
                                                            <span className="text-[9px] font-black uppercase tracking-widest text-gray-600" style={{ color: getSpokeColor(task.context) }}>{task.context}</span>
                                                            <span className="text-[9px] font-black text-gray-700 bg-black/40 rounded-md px-2 py-1 uppercase tracking-tighter">Impact: {task.base_load_score}</span>
                                                        </div>
                                                    </div>
                                                ))
                                            )}
                                        </div>
                                        <div className="p-4 bg-white/[0.01] border-t border-gray-800/30">
                                            <button onClick={() => { setQaDueDate(dayDetailsDate); setCreateModalOpen(true); }} className="w-full py-3.5 bg-blue-600 hover:bg-blue-500 text-white border border-blue-500/50 rounded-xl text-[11px] font-black uppercase tracking-[0.2em] transition-all shadow-xl shadow-blue-500/10 active:scale-95">Add Priority Task</button>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    ) : (
                        <TimelineCalendar targetDate={targetDate} onTaskClick={handleRowClick} refreshKey={refreshKey} />
                    )}
                </div>
            </div>
        </div>
    );
}
