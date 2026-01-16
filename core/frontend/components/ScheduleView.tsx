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
        work: 'bg-blue-500/20 border-blue-500',
        health: 'bg-green-500/20 border-green-500',
        research: 'bg-purple-500/20 border-purple-500',
        admin: 'bg-gray-500/20 border-gray-500',
        personal: 'bg-orange-500/20 border-orange-500',
    };
    return colors[context.toLowerCase()] || 'bg-slate-500/20 border-slate-500';
}

// ============================================================================
// Subcomponents
// ============================================================================

function ScheduleItem({ item }: { item: ScheduledItem }) {
    if (item.is_buffer) {
        return (
            <div className="flex items-center gap-3 py-2 px-3 rounded-lg bg-amber-500/10 border border-amber-500/30">
                <div className="text-amber-500 text-xs font-medium">
                    {formatTime(item.start)} - {formatTime(item.end)}
                </div>
                <div className="flex-1 text-amber-400/80 text-sm">
                    ☕ Break ({getDuration(item.start, item.end)} min)
                </div>
            </div>
        );
    }

    if (!item.task) return null;

    const contextColor = getContextColor(item.task.context || '');

    return (
        <div className={`flex items-center gap-3 py-2 px-3 rounded-lg border ${contextColor}`}>
            <div className="text-slate-400 text-xs font-medium min-w-[90px]">
                {formatTime(item.start)} - {formatTime(item.end)}
            </div>
            <div className="flex-1">
                <div className="text-slate-200 text-sm font-medium">{item.task.task_name}</div>
                <div className="text-slate-500 text-xs">
                    {item.task.context || 'General'} · Load {(item.task.load ?? 1).toFixed(1)}
                </div>
            </div>
            <div className="text-slate-500 text-xs">
                {getDuration(item.start, item.end)} min
            </div>
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
    const shutdownDisplay = shutdownTime
        ? new Date(shutdownTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '--:--';

    return (
        <div className={`bg-slate-900 rounded-xl p-4 ${className}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-slate-200 font-semibold">Today&apos;s Schedule</h3>
                <div className="flex items-center gap-3 text-xs">
                    <span className="text-slate-500">
                        Shutdown: <span className="text-slate-400">{shutdownDisplay}</span>
                    </span>
                    {fatigueLevel > 0 && (
                        <span className={`px-2 py-0.5 rounded ${fatigueLevel >= 3 ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                            Fatigue {fatigueLevel}
                        </span>
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
