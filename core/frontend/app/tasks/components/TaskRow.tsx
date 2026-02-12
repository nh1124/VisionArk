"use client";

import React from "react";
import { CheckCircle2, Circle, Star, Calendar } from "lucide-react";
import { getSpokeColor } from "@/lib/colors";
import { Task } from "../types";
import { useTaskStore } from "@/store/useTaskStore";

interface TaskRowProps {
    task: Task;
    onToggle: () => void;
    onClick: () => void;
    isMobile: boolean;
}

export default function TaskRow({ task, onToggle, onClick, isMobile }: TaskRowProps) {
    const isCompleted = task.status === 'done' || task.status === 'skipped' || task.status === 'completed';
    const { toggleMyDay } = useTaskStore();
    const isMyDay = task.meta_payload?.is_my_day;

    return (
        <div
            onClick={onClick}
            className={`flex items-center gap-2 sm:gap-3 px-2 sm:px-3 py-2 sm:py-2.5 bg-gray-900/40 hover:bg-gray-900/80 border-b border-gray-800/10 sm:border ${isCompleted ? 'opacity-60' : ''} sm:rounded-xl group transition-all cursor-pointer`}
        >
            <button
                onClick={(e) => { e.stopPropagation(); onToggle(); }}
                className={`w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 flex items-center justify-center transition-transform active:scale-90 ${isCompleted ? 'text-blue-500' : 'text-gray-600 hover:text-gray-400'}`}
            >
                {isCompleted ? <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5" /> : <Circle className="w-4 h-4 sm:w-5 sm:h-5" />}
            </button>

            <h3 className={`flex-1 min-w-0 font-semibold truncate transition-colors group-hover:text-blue-400 ${isCompleted ? 'line-through text-gray-500' : 'text-white'} ${isMobile ? 'text-[13px]' : 'text-sm'}`}>
                {task.task_name}
            </h3>

            <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0 ml-auto">
                <span
                    className="text-[8px] sm:text-[9px] font-black uppercase tracking-wider px-1.2 sm:px-1.5 py-0.5 rounded bg-white/5"
                    style={{ color: getSpokeColor(task.context) }}
                >
                    {task.context}
                </span>
                {task.due_date && (
                    <span className="text-[8px] sm:text-[9px] font-semibold text-gray-600 flex items-center gap-1">
                        <Calendar className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                        <span className="whitespace-nowrap">{isMobile ? task.due_date.split('-').slice(1).join('/') : task.due_date}</span>
                    </span>
                )}
                <span className="text-[8px] sm:text-[9px] font-bold text-gray-600 px-1 sm:px-1.5 py-0.5 bg-gray-800/40 rounded min-w-[1.2rem] text-center">
                    {task.base_load_score}
                </span>
            </div>

            <button
                onClick={(e) => { e.stopPropagation(); toggleMyDay(task); }}
                className={`w-4 h-4 sm:w-5 sm:h-5 flex-shrink-0 flex items-center justify-center transition-transform active:scale-90 ${isMyDay ? 'text-amber-400' : 'text-gray-700 hover:text-gray-500'}`}
            >
                <Star size={isMobile ? 14 : 16} fill={isMyDay ? "currentColor" : "none"} />
            </button>
        </div>
    );
}
