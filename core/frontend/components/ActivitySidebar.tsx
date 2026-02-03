"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import {
    Activity,
    ChevronDown,
    ChevronRight,
    Cpu,
    ExternalLink,
    CheckCircle2,
    AlertCircle,
    Clock,
    Terminal,
    Box
} from "lucide-react";
import MarkdownRenderer from "./MarkdownRenderer";
import { formatDistanceToNow } from "date-fns";

interface ToolCall {
    name: string;
    args: any;
    result?: string;
    is_success: boolean;
}

interface SubMessage {
    sub_id: string;
    content: string;
    tool_calls: ToolCall[];
    timestamp: string;
}

interface ActivityItem {
    id?: string;
    role: "user" | "assistant";
    content: string;
    meta_payload: any;
    created_at?: string;
    timestamp?: string;
    sub_messages: SubMessage[];
}

const safeDate = (dateStr: string | undefined | null) => {
    if (!dateStr) return new Date();
    const d = new Date(dateStr);
    return isNaN(d.getTime()) ? new Date() : d;
};

interface ActivitySidebarProps {
    projectId: string;
}

export default function ActivitySidebar({ projectId }: ActivitySidebarProps) {
    const [activities, setActivities] = useState<ActivityItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({});

    const fetchActivity = useCallback(async () => {
        try {
            setLoading(true);
            const response = await apiFetch(`/api/agents/project/${projectId}/history`);
            if (response.ok) {
                const data = await response.json();
                const history = data.history || [];
                // Filter for background agent callbacks
                const backgroundActivities = history.filter((m: any) =>
                    m.meta_payload?.type === "node_callback" ||
                    m.meta_payload?.type === "node_callback_failure"
                );
                // Sort by newest first
                setActivities(backgroundActivities.reverse());
            }
        } catch (error) {
            console.error("Failed to load activities:", error);
        } finally {
            setLoading(false);
        }
    }, [projectId]);

    useEffect(() => {
        fetchActivity();

        // Refresh every 10 seconds for pseudo-real-time updates if polling
        const interval = setInterval(fetchActivity, 10000);
        return () => clearInterval(interval);
    }, [fetchActivity]);

    const toggleStep = (id: string) => {
        setExpandedSteps(prev => ({ ...prev, [id]: !prev[id] }));
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <Activity size={16} className="text-cyan-400" />
                    <span className="text-sm font-bold text-gray-200">Recent Activity</span>
                </div>
                <button
                    onClick={fetchActivity}
                    className="text-[10px] text-gray-500 hover:text-white uppercase tracking-widest font-bold transition-colors"
                >
                    Refresh
                </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 pr-1">
                {loading && activities.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-gray-600 gap-4">
                        <Terminal size={32} className="animate-pulse" />
                        <p className="text-xs font-mono">Tracing background threads...</p>
                    </div>
                ) : activities.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-gray-600 gap-4 text-center">
                        <Box size={32} className="opacity-20" />
                        <p className="text-xs uppercase tracking-widest">No background activity yet</p>
                        <p className="text-[10px] text-gray-500 max-w-[160px]">
                            Tasks like research or deep analysis will appear here.
                        </p>
                    </div>
                ) : (
                    activities.map((activity, idx) => (
                        <div
                            key={activity.id || `activity-${idx}`}
                            className="bg-gray-800/30 border border-gray-700/50 rounded-xl overflow-hidden group hover:border-cyan-500/30 transition-all duration-300"
                        >
                            {/* Card Header */}
                            <div className="p-3 border-b border-gray-700/50 bg-gray-800/20">
                                <div className="flex items-center justify-between mb-1">
                                    <div className="flex items-center gap-2">
                                        {activity.meta_payload.type === "node_callback_failure" ? (
                                            <AlertCircle size={14} className="text-rose-400" />
                                        ) : (
                                            <CheckCircle2 size={14} className="text-emerald-400" />
                                        )}
                                        <span className="text-xs font-bold text-white truncate max-w-[140px]">
                                            {activity.meta_payload.node_name}
                                        </span>
                                    </div>
                                    <span className="text-[10px] text-gray-500 flex items-center gap-1">
                                        <Clock size={10} />
                                        {formatDistanceToNow(safeDate(activity.created_at || activity.timestamp), { addSuffix: true })}
                                    </span>
                                </div>
                                <div className="text-[10px] text-gray-400 line-clamp-1 opacity-70 italic">
                                    {activity.content.replace(/🤖 \*\*.+\*\* has completed background work:\s*/i, "").slice(0, 100)}...
                                </div>
                            </div>

                            {/* Thinking Process Accordion */}
                            {activity.sub_messages && activity.sub_messages.length > 0 && (
                                <div className="bg-gray-900/40">
                                    <button
                                        onClick={() => toggleStep(activity.id)}
                                        className="w-full flex items-center justify-between p-2 text-[10px] font-black text-gray-500 uppercase tracking-[2px] bg-gray-900/20 hover:text-cyan-400 transition-colors"
                                    >
                                        <div className="flex items-center gap-2">
                                            <Cpu size={12} />
                                            Thinking Process
                                            <span className="bg-gray-800 text-gray-400 px-1.5 rounded-full text-[9px]">
                                                {activity.sub_messages.length} steps
                                            </span>
                                        </div>
                                        {expandedSteps[activity.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    </button>

                                    {expandedSteps[activity.id] && (
                                        <div className="p-3 space-y-4 animate-in slide-in-from-top-1 duration-200">
                                            {activity.sub_messages.map((step, sIdx) => (
                                                <div key={step.sub_id || sIdx} className="space-y-2 last:mb-0">
                                                    <div className="flex items-center gap-2 text-[10px] font-mono text-cyan-500/70">
                                                        <span className="opacity-50">#0{sIdx + 1}</span>
                                                        <div className="h-[1px] flex-1 bg-cyan-950/50" />
                                                    </div>
                                                    <div className="text-xs text-gray-300 leading-relaxed pl-2 border-l border-gray-800">
                                                        <MarkdownRenderer content={step.content} />
                                                    </div>
                                                    {step.tool_calls && step.tool_calls.length > 0 && (
                                                        <div className="pl-4 space-y-1">
                                                            {step.tool_calls.map((tc, tIdx) => (
                                                                <div key={tIdx} className="flex flex-col gap-1.5 p-2 bg-black/20 rounded border border-gray-800/50 group/tool">
                                                                    <div className="flex items-center justify-between">
                                                                        <div className="flex items-center gap-1.5 text-[10px] font-mono">
                                                                            <Terminal size={10} className="text-emerald-500" />
                                                                            <span className="text-emerald-400 font-bold">{tc.name}</span>
                                                                        </div>
                                                                        {tc.is_success ? (
                                                                            <CheckCircle2 size={10} className="text-emerald-500/50" />
                                                                        ) : (
                                                                            <AlertCircle size={10} className="text-rose-500/50" />
                                                                        )}
                                                                    </div>
                                                                    <div className="text-[9px] text-gray-500 italic truncate font-mono">
                                                                        {JSON.stringify(tc.args).slice(0, 60)}...
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Action Links */}
                            <div className="p-2 flex gap-2 justify-end bg-gray-800/10">
                                <button
                                    className="text-[10px] font-bold text-gray-500 hover:text-white flex items-center gap-1 transition-colors"
                                    onClick={() => {
                                        // Scroll to message in main chat (implementation would need ref or message-id search)
                                        console.log("Locate message:", activity.id);
                                    }}
                                >
                                    <ExternalLink size={10} /> View in Chat
                                </button>
                            </div>
                        </div>
                    ))
                )}
            </div>

            <div className="mt-4 pt-4 border-t border-gray-800 text-[10px] text-gray-600 font-mono">
                System: Monitoring activity for Project Agent
            </div>
        </div>
    );
}
