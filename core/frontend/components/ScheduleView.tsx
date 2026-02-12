'use client';

/**
 * ScheduleView Component
 * 
 * Displays the dynamic schedule with tasks and buffer periods
 */

import React from 'react';
import { ScheduledItem, ScheduledTask } from '@/lib/schedule';

// ============================================================================
// Types
// ============================================================================

interface ScheduleViewProps {
    schedule: ScheduledItem[];
    overflow: ScheduledTask[];
    shutdownTime?: string;
    fatigueLevel?: number;
    className?: string;
}

import { useIsMobile } from '@/hooks/useIsMobile';

// ============================================================================
// Helpers
// ============================================================================

function formatTime(isoString: string): string {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getDuration(start: string, end: string): number {
    return Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000);
}

function getContextColor(context: string): string {
    const colors: Record<string, string> = {
        work: 'bg-blue-500/10 border-blue-500/40 text-blue-400',
        health: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-400',
        research: 'bg-purple-500/10 border-purple-500/40 text-purple-400',
        admin: 'bg-gray-500/10 border-gray-500/40 text-gray-400',
        personal: 'bg-orange-500/10 border-orange-500/40 text-orange-400',
    };
    return colors[context.toLowerCase()] || 'bg-slate-500/10 border-slate-500/40 text-slate-400';
}

// ============================================================================
// Subcomponents
// ============================================================================

function ScheduleItem({ item }: { item: ScheduledItem }) {
    const isMobile = useIsMobile();

    if (item.is_buffer) {
        return (
            <div className={`flex ${isMobile ? 'flex-col items-start gap-1' : 'items-center gap-3'} py-3 px-4 rounded-xl bg-amber-500/5 border border-amber-500/20 backdrop-blur-sm`}>
                <div className="text-amber-500/60 text-[10px] font-black uppercase tracking-widest">
                    {formatTime(item.start)} — {formatTime(item.end)}
                </div>
                <div className="flex-1 text-amber-200/90 text-sm font-medium">
                    Rest Period <span className="text-[10px] opacity-40 ml-1">({getDuration(item.start, item.end)}m)</span>
                </div>
            </div>
        );
    }

    if (!item.task) return null;

    const contextStyle = getContextColor(item.task.context || '');

    return (
        <div className={`flex ${isMobile ? 'flex-col items-start gap-2' : 'items-center gap-3'} py-3 px-4 rounded-xl border border-gray-800 bg-gray-900/40 hover:bg-gray-800/60 transition-all duration-300`}>
            {isMobile ? (
                <div className="flex justify-between w-full items-baseline">
                    <div className="text-gray-500 text-[10px] font-black uppercase tracking-widest">
                        {formatTime(item.start)} — {formatTime(item.end)}
                    </div>
                    <div className="text-[10px] font-bold text-gray-600 px-2 py-0.5 rounded-full bg-gray-800 border border-gray-700">
                        {getDuration(item.start, item.end)}m
                    </div>
                </div>
            ) : (
                <div className="text-gray-500 text-[10px] font-black uppercase tracking-widest min-w-[100px]">
                    {formatTime(item.start)} — {formatTime(item.end)}
                </div>
            )}

            <div className="flex-1">
                <div className="text-gray-200 text-sm font-bold tracking-tight">{item.task.task_name}</div>
                <div className="flex items-center gap-2 mt-1">
                    <span className={`text-[8px] font-black uppercase tracking-[0.1em] px-1.5 py-0.5 rounded ${contextStyle}`}>
                        {item.task.context || 'General'}
                    </span>
                    <span className="text-[9px] font-medium text-gray-500 tabular-nums">
                        Load {(item.task.load ?? 1).toFixed(1)}
                    </span>
                </div>
            </div>

            {!isMobile && (
                <div className="text-gray-600 text-[10px] font-bold tabular-nums">
                    {getDuration(item.start, item.end)}m
                </div>
            )}
        </div>
    );
}

function OverflowSection({ tasks }: { tasks: ScheduledTask[] }) {
    if (tasks.length === 0) return null;

    return (
        <div className="mt-4 pt-4 border-t border-slate-700">
            <h4 className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wider">
                Overflow ({tasks.length})
            </h4>
            <div className="space-y-1">
                {tasks.map((task) => (
                    <div key={task.task_id} className="text-slate-500 text-sm py-1">
                        <span className="text-slate-400">{task.task_name}</span>
                        <span className="text-slate-600 ml-2">· {task.context}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

export default function ScheduleView({
    schedule,
    overflow,
    shutdownTime,
    fatigueLevel = 0,
    className = '',
}: ScheduleViewProps) {
    const isMobile = useIsMobile();
    const shutdownDisplay = shutdownTime
        ? new Date(shutdownTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '--:--';

    return (
        <div className={`bg-gray-950/20 border border-gray-800 rounded-3xl ${isMobile ? 'p-5' : 'p-8'} ${className}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-gray-200 font-bold tracking-tight">Today&apos;s Focus</h3>
                    <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mt-0.5">Automated Intelligence</p>
                </div>
                <div className="flex flex-col items-end gap-1">
                    <div className="flex items-center gap-2">
                        <span className="text-[9px] font-black text-gray-600 uppercase tracking-widest">Shutdown</span>
                        <span className="text-xs font-bold text-gray-300 tabular-nums">{shutdownDisplay}</span>
                    </div>
                    {fatigueLevel > 0 && (
                        <div className={`px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-widest ${fatigueLevel >= 3 ? 'bg-red-500/20 text-red-500 border border-red-500/30' : 'bg-yellow-500/20 text-yellow-500 border border-yellow-500/30'}`}>
                            Strain: {fatigueLevel}
                        </div>
                    )}
                </div>
            </div>

            {/* Schedule Items */}
            {schedule.length === 0 ? (
                <div className="text-slate-500 text-sm text-center py-8">
                    No tasks scheduled
                </div>
            ) : (
                <div className="space-y-2">
                    {schedule.map((item, index) => (
                        <ScheduleItem key={index} item={item} />
                    ))}
                </div>
            )}

            {/* Overflow */}
            <OverflowSection tasks={overflow} />
        </div>
    );
}
