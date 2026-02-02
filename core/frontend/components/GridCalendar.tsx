"use client";

import React, { useMemo } from 'react';
import {
    format,
    startOfMonth,
    endOfMonth,
    startOfWeek,
    endOfWeek,
    eachDayOfInterval,
    isSameMonth,
    isSameDay,
    addMonths,
    subMonths,
} from 'date-fns';
import {
    DndContext,
    DragOverlay,
    useSensor,
    useSensors,
    PointerSensor,
    DragEndEvent,
} from '@dnd-kit/core';
import { useDroppable } from '@dnd-kit/core';
import { useDraggable } from '@dnd-kit/core';
import { useTaskStore } from '../store/useTaskStore';
import { Task } from '../app/tasks/types';
import { CheckCircle2, Circle } from 'lucide-react';

interface GridCalendarProps {
    month: Date;
    onDayClick?: (date: string) => void;
    includeCompleted?: boolean;
}

export default function GridCalendar({ month, onDayClick, includeCompleted = true }: GridCalendarProps) {
    const { calendarTasks, rescheduleTask, fetchMonthTasks, activeProject } = useTaskStore();

    // Fetch data for the current month view
    React.useEffect(() => {
        const start = format(startOfWeek(startOfMonth(month)), 'yyyy-MM-dd');
        const end = format(endOfWeek(endOfMonth(month)), 'yyyy-MM-dd');
        fetchMonthTasks(start, end);
    }, [month, fetchMonthTasks]);

    // Filter tasks if includeCompleted is false or if a project is selected
    const displayTasksForCalendar = useMemo(() => {
        let filtered = calendarTasks;
        if (!includeCompleted) {
            filtered = filtered.filter(t => t.status !== 'completed' && t.status !== 'done');
        }
        if (activeProject) {
            filtered = filtered.filter(t => t.context === activeProject);
        }
        return filtered;
    }, [calendarTasks, includeCompleted, activeProject]);

    // Dnd Sensors
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 5,
            },
        })
    );

    // Calendar logic
    const startDate = startOfWeek(startOfMonth(month));
    const endDate = endOfWeek(endOfMonth(month));
    const days = eachDayOfInterval({ start: startDate, end: endDate });

    // Group tasks by day
    const tasksByDay = useMemo(() => {
        const map: Record<string, Task[]> = {};
        displayTasksForCalendar.forEach((task) => {
            if (task.due_date) {
                if (!map[task.due_date]) map[task.due_date] = [];
                map[task.due_date].push(task);
            }
        });
        return map;
    }, [displayTasksForCalendar]);

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            const taskId = active.id as string;
            const newDate = over.id as string;
            rescheduleTask(taskId, newDate);
        }
    };

    return (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
            <div className="w-full bg-gray-900/50 rounded-2xl border border-gray-800 p-4 shadow-2xl backdrop-blur-xl">
                <div className="grid grid-cols-7 gap-px bg-gray-800 overflow-hidden rounded-xl border border-gray-800">
                    {/* Header Days */}
                    {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
                        <div key={d} className="bg-gray-900/80 py-2 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">
                            {d}
                        </div>
                    ))}

                    {/* Day Cells */}
                    {days.map((day) => {
                        const dateStr = format(day, 'yyyy-MM-dd');
                        const dayTasks = tasksByDay[dateStr] || [];
                        const isCurrentMonth = isSameMonth(day, month);
                        const isToday = isSameDay(day, new Date());

                        return (
                            <DayCell
                                key={dateStr}
                                date={dateStr}
                                dayNumber={day.getDate()}
                                isCurrentMonth={isCurrentMonth}
                                isToday={isToday}
                                tasks={dayTasks}
                                onClick={() => onDayClick?.(dateStr)}
                            />
                        );
                    })}
                </div>
            </div>
        </DndContext>
    );
}

interface DayCellProps {
    date: string;
    dayNumber: number;
    isCurrentMonth: boolean;
    isToday: boolean;
    tasks: Task[];
    onClick: () => void;
}

function DayCell({ date, dayNumber, isCurrentMonth, isToday, tasks, onClick }: DayCellProps) {
    const { setNodeRef, isOver } = useDroppable({
        id: date,
    });

    return (
        <div
            ref={setNodeRef}
            onClick={onClick}
            className={`min-h-[100px] sm:min-h-[120px] bg-gray-900/40 p-2 transition-all cursor-pointer relative group
                ${!isCurrentMonth ? 'opacity-30' : ''}
                ${isOver ? 'bg-blue-600/20 scale-[0.98] z-10' : ''}
                ${isToday ? 'bg-blue-900/10' : ''}
                hover:bg-gray-800/40
            `}
        >
            <div className="flex justify-between items-center mb-1">
                <span className={`text-[10px] font-black ${isToday ? 'text-blue-400' : 'text-gray-600'}`}>
                    {dayNumber}
                </span>
            </div>

            <div className="flex flex-col gap-1">
                {tasks.slice(0, 4).map((task) => (
                    <DraggableTask key={task.task_id} task={task} />
                ))}
                {tasks.length > 4 && (
                    <span className="text-[8px] font-bold text-gray-600 pl-1">
                        + {tasks.length - 4} more
                    </span>
                )}
            </div>

            {/* Hover Indicator */}
            <div className="absolute inset-0 border border-transparent group-hover:border-gray-700/50 rounded-lg pointer-events-none transition-all" />
        </div>
    );
}

function DraggableTask({ task }: { task: Task }) {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: task.task_id,
    });

    const isDone = task.status === 'completed' || task.status === 'done';

    const style = transform ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
        zIndex: 50,
    } : undefined;

    return (
        <div
            ref={setNodeRef}
            style={style}
            {...listeners}
            {...attributes}
            className={`
                group/task text-[9px] sm:text-[10px] py-1 px-1.5 rounded-lg flex items-center gap-1.5 transition-all
                ${isDragging ? 'shadow-2xl opacity-50 scale-105 bg-blue-600 border-none' : 'bg-gray-800/80 border border-gray-700/50 hover:border-blue-500/50'}
                ${isDone ? 'opacity-50' : ''}
            `}
        >
            <div className={`w-2.5 h-2.5 flex-shrink-0 ${isDone ? 'text-blue-500' : 'text-gray-600'}`}>
                {isDone ? <CheckCircle2 size={10} /> : <Circle size={10} />}
            </div>
            <span className={`truncate flex-1 font-bold ${isDone ? 'line-through text-gray-500' : 'text-gray-200'}`}>
                {task.task_name}
            </span>
        </div>
    );
}
