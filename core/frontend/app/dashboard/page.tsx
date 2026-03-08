"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
    Activity,
    ArrowUpRight,
    Calendar,
    CheckSquare,
    ChevronRight,
    Cloud,
    History,
    Layout,
    ListTodo,
    Target,
    Zap,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

type WeatherData = { temp: number; code: number; description: string };

interface MeResponse {
    username?: string;
}

interface SettingsResponse {
    general_settings?: {
        location?: string;
    };
}

interface LBSTask {
    task_id: string;
    task_name: string;
    context: string;
    status?: string | null;
    start_time?: string | null;
    end_time?: string | null;
}

interface ScheduleDay {
    date: string;
    tasks: Array<{
        task_id: string;
        task_name: string;
        context: string;
        start_time: string | null;
        end_time: string | null;
    }>;
}

interface Project {
    id: string;
    name: string;
    display_name?: string | null;
}

interface RunItem {
    id: string;
    created_at: string;
    summary?: string;
}

interface MemoryItem {
    id: string;
    created_at: string;
    content: string;
}

interface ActivityItem {
    type: "run" | "memory";
    timestamp: number;
    summary: string;
}

interface ProjectWithProgress extends Project {
    completed_tasks: number;
    total_tasks: number;
    progress: number;
}

function getWeatherDescription(code: number): string {
    if (code === 0) return "Clear sky";
    if (code <= 3) return "Partly cloudy";
    if (code <= 48) return "Foggy";
    if (code <= 57) return "Drizzle";
    if (code <= 67) return "Rainy";
    if (code <= 77) return "Snowy";
    if (code <= 82) return "Showers";
    if (code <= 99) return "Thunderstorm";
    return "Unknown";
}

async function fetchWeather(location: string): Promise<WeatherData | null> {
    try {
        const geoRes = await fetch(
            `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(location)}&count=1&language=en&format=json`
        );
        const geoData = await geoRes.json();
        if (!geoData.results?.length) return null;

        const { latitude, longitude } = geoData.results[0];
        const weatherRes = await fetch(
            `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current_weather=true`
        );
        const weatherData = await weatherRes.json();
        const cw = weatherData.current_weather;
        return {
            temp: Math.round(cw.temperature),
            code: cw.weathercode,
            description: getWeatherDescription(cw.weathercode),
        };
    } catch {
        return null;
    }
}

export default function DashboardPage() {
    const router = useRouter();
    const [loading, setLoading] = useState(true);
    const [currentTime, setCurrentTime] = useState(new Date());
    const [username, setUsername] = useState("Commander");
    const [location, setLocation] = useState("Tokyo");
    const [weather, setWeather] = useState<WeatherData | null>(null);
    const [tasks, setTasks] = useState<LBSTask[]>([]);
    const [schedule, setSchedule] = useState<ScheduleDay[]>([]);
    const [projects, setProjects] = useState<ProjectWithProgress[]>([]);
    const [activities, setActivities] = useState<ActivityItem[]>([]);

    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        let cancelled = false;

        async function load() {
            try {
                const todayStr = new Date().toISOString().split("T")[0];
                const [
                    meRes,
                    settingsRes,
                    tasksRes,
                    scheduleRes,
                    projectsRes,
                    activeTasksRes,
                    overdueRes,
                    memoriesRes,
                    runsRes,
                ] = await Promise.all([
                    apiFetch("/api/auth/me").catch(() => null),
                    apiFetch("/api/settings").catch(() => null),
                    apiFetch(`/api/lbs/tasks?target_date=${todayStr}`).catch(() => null),
                    apiFetch(`/api/lbs/schedule?start_date=${todayStr}&end_date=${todayStr}`).catch(() => null),
                    apiFetch("/api/agents/project/list").catch(() => null),
                    apiFetch("/api/lbs/tasks?active=true").catch(() => null),
                    apiFetch("/api/lbs/overdue").catch(() => null),
                    apiFetch("/api/lbs/memories?limit=10").catch(() => null),
                    apiFetch("/api/runs?limit=10").catch(() => null),
                ]);

                const me = meRes?.ok ? ((await meRes.json()) as MeResponse) : null;
                const settings = settingsRes?.ok ? ((await settingsRes.json()) as SettingsResponse) : null;
                const todayTasks = tasksRes?.ok ? ((await tasksRes.json()) as LBSTask[]) : [];
                const todaySchedule = scheduleRes?.ok ? ((await scheduleRes.json()) as ScheduleDay[]) : [];
                const projectList = projectsRes?.ok
                    ? ((((await projectsRes.json()) as { projects?: Project[] }).projects) ?? [])
                    : [];
                const activeTasks = activeTasksRes?.ok ? ((await activeTasksRes.json()) as LBSTask[]) : [];
                const overdueTasks = overdueRes?.ok ? ((await overdueRes.json()) as LBSTask[]) : [];
                const memories = memoriesRes?.ok
                    ? ((((await memoriesRes.json()) as { memories?: MemoryItem[] }).memories) ?? [])
                    : [];
                const runsRaw = runsRes?.ok
                    ? ((await runsRes.json()) as { runs?: RunItem[] } | RunItem[])
                    : [];
                const runs = Array.isArray(runsRaw) ? runsRaw : runsRaw.runs ?? [];

                if (cancelled) return;

                if (me?.username) setUsername(me.username);
                const locationRaw = settings?.general_settings?.location ?? "Tokyo, Japan";
                setLocation(locationRaw.split(",")[0] || "Tokyo");
                setTasks(todayTasks ?? []);
                setSchedule(todaySchedule ?? []);

                const statMap = new Map<string, { done: number; total: number }>();
                for (const task of [...activeTasks, ...overdueTasks]) {
                    const context = task.context || "inbox";
                    if (!statMap.has(context)) statMap.set(context, { done: 0, total: 0 });
                    const stat = statMap.get(context)!;
                    stat.total += 1;
                    if (task.status === "done") stat.done += 1;
                }

                const withProgress: ProjectWithProgress[] = projectList.map((p) => {
                    const stat = statMap.get(p.name) ?? { done: 0, total: 0 };
                    return {
                        ...p,
                        completed_tasks: stat.done,
                        total_tasks: stat.total,
                        progress: stat.total > 0 ? (stat.done / stat.total) * 100 : 0,
                    };
                });
                withProgress.sort((a, b) => b.total_tasks - a.total_tasks);
                setProjects(withProgress);

                const merged: ActivityItem[] = [
                    ...runs.map((r) => ({
                        type: "run" as const,
                        timestamp: new Date(r.created_at).getTime(),
                        summary: r.summary || `Execution Run ${r.id.slice(0, 8)}`,
                    })),
                    ...memories.map((m) => ({
                        type: "memory" as const,
                        timestamp: new Date(m.created_at).getTime(),
                        summary: m.content,
                    })),
                ].sort((a, b) => b.timestamp - a.timestamp);
                setActivities(merged);

                const weatherData = await fetchWeather(locationRaw);
                if (!cancelled) setWeather(weatherData);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        load();
        return () => {
            cancelled = true;
        };
    }, []);

    const greeting = useMemo(() => {
        const hour = currentTime.getHours();
        if (hour < 12) return "Good morning";
        if (hour < 18) return "Good afternoon";
        return "Good evening";
    }, [currentTime]);

    if (loading) {
        return (
            <div className="h-full w-full flex items-center justify-center bg-gray-950">
                <div className="flex flex-col items-center gap-4">
                    <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin" />
                    <p className="text-gray-500 font-medium text-xs tracking-widest uppercase animate-pulse">
                        Initializing Dashboard
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex-1 h-full flex flex-col overflow-y-auto bg-gray-950 p-5 lg:p-8">
            <div className="max-w-7xl mx-auto w-full space-y-4 lg:space-y-6">
                <div className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-indigo-700 via-purple-700 to-pink-600 p-6 lg:p-7 shadow-2xl border border-white/5">
                    <div className="relative z-10 flex flex-col xl:flex-row xl:items-center justify-between gap-4">
                        <div className="space-y-1">
                            <h1 className="text-3xl lg:text-5xl font-bold text-white tracking-tight leading-[1.05]">
                                {greeting},
                                <br />
                                <span className="text-white/70 font-semibold">{username}</span>
                            </h1>
                            <div className="flex items-center gap-2 text-white/40 text-[10px] font-bold uppercase tracking-[0.2em] pt-1">
                                <Target size={11} className="text-cyan-300" />
                                {tasks.filter((t) => t.status !== "done").length} tasks remaining
                            </div>
                        </div>

                        <div className="flex items-center gap-6 bg-black/20 backdrop-blur-3xl rounded-[24px] p-4 lg:p-5 border border-white/5 shadow-2xl">
                            <div className="text-right">
                                <p className="text-3xl lg:text-5xl font-mono font-bold tracking-tighter tabular-nums text-white leading-none">
                                    {currentTime.toLocaleTimeString("en-US", {
                                        hour12: false,
                                        hour: "2-digit",
                                        minute: "2-digit",
                                        second: "2-digit",
                                    })}
                                </p>
                                <p className="text-[9px] font-bold text-purple-200/40 uppercase tracking-[0.35em] mt-2">
                                    {currentTime
                                        .toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
                                        .replace(",", " /")}
                                </p>
                            </div>
                            <div className="h-10 w-px bg-white/10" />
                            <div className="flex items-center gap-3">
                                <div className="p-3 bg-white/5 rounded-xl">
                                    <Cloud size={20} className="text-blue-200" />
                                </div>
                                <div>
                                    <p className="text-2xl lg:text-4xl font-bold text-white leading-none">{weather?.temp ?? "--"}°C</p>
                                    <p className="text-[8px] font-bold text-blue-200/60 uppercase tracking-widest mt-1">
                                        {location} / {weather?.description || "Syncing"}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div className="absolute top-[-20%] right-[-10%] w-96 h-96 bg-white/5 rounded-full blur-3xl opacity-50" />
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 lg:gap-5 pb-2">
                    <GlassCard title="Project Progress" icon={<Layout size={16} />} action="Project Page" onAction={() => router.push("/projects")}>
                        <div className="space-y-4">
                            {projects.length > 0 ? projects.slice(0, 3).map((project) => (
                                <button
                                    key={project.id}
                                    onClick={() => router.push(`/projects/${project.id}`)}
                                    className="w-full text-left space-y-1.5 group"
                                >
                                    <div className="flex justify-between items-end">
                                        <div className="flex items-center gap-2.5">
                                            <div className="w-1 h-1 rounded-full bg-cyan-500 shadow-[0_0_6px_rgba(6,182,212,0.4)]" />
                                            <span className="text-[13px] font-semibold text-gray-200 group-hover:text-white truncate">
                                                {project.display_name || project.name}
                                            </span>
                                        </div>
                                        <span className="text-[9px] font-bold text-gray-600 tracking-widest uppercase">
                                            {project.completed_tasks}/{project.total_tasks}
                                            <span className="text-cyan-500/60 ml-1">{Math.round(project.progress)}%</span>
                                        </span>
                                    </div>
                                    <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
                                        <div
                                            className="h-full bg-gradient-to-r from-indigo-500 via-cyan-500 to-emerald-400 opacity-80"
                                            style={{ width: `${project.progress}%` }}
                                        />
                                    </div>
                                </button>
                            )) : <EmptyState message="No trackable projects" />}
                        </div>
                    </GlassCard>

                    <GlassCard title="Recent Activity" icon={<Activity size={16} />} action="Run Center" onAction={() => router.push("/jobs")}>
                        <div className="space-y-5">
                            {activities.length > 0 ? activities.slice(0, 3).map((item, idx) => (
                                <button key={`${item.type}-${idx}`} onClick={() => router.push("/jobs")} className="w-full text-left relative pl-5">
                                    <div className={`absolute left-0 top-1.5 w-1 h-1 rounded-full ${item.type === "run" ? "bg-orange-500" : "bg-purple-500"}`} />
                                    <div className="flex flex-col gap-0.5">
                                        <div className="flex items-center gap-1.5">
                                            <span className="text-[8px] font-bold text-gray-600 uppercase tracking-[0.2em]">
                                                {item.type === "run" ? "Agent Run" : "Core Memory"}
                                            </span>
                                            <span className="text-[8px] font-medium text-gray-700 font-mono">
                                                {new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                            </span>
                                        </div>
                                        <p className="text-[12px] font-medium text-gray-400 leading-tight line-clamp-1">{item.summary}</p>
                                    </div>
                                </button>
                            )) : <EmptyState message="Quiet for now" />}
                        </div>
                    </GlassCard>

                    <GlassCard title="Today's Tasks" icon={<ListTodo size={16} />} action="Tasks Page" onAction={() => router.push("/tasks")}>
                        <div className="space-y-3">
                            {tasks.length > 0 ? tasks.slice(0, 3).map((task) => (
                                <button
                                    key={task.task_id}
                                    onClick={() => router.push("/tasks")}
                                    className="w-full flex items-center gap-3 p-3 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all group"
                                >
                                    <div className={`flex-shrink-0 w-2 h-2 rounded-full border ${task.status === "done" ? "bg-cyan-500 border-cyan-400/50" : "bg-transparent border-gray-700"}`} />
                                    <div className="flex-1 min-w-0 text-left">
                                        <p className={`text-[14px] font-bold truncate ${task.status === "done" ? "text-gray-600 line-through" : "text-gray-200"}`}>
                                            {task.task_name}
                                        </p>
                                        <p className="text-[9px] font-bold text-gray-600 uppercase tracking-widest mt-0.5">{task.context}</p>
                                    </div>
                                    <ArrowUpRight size={11} className="text-gray-700 group-hover:text-cyan-500" />
                                </button>
                            )) : <EmptyState message="All tasks clear" />}
                        </div>
                    </GlassCard>

                    <GlassCard title="Today's Schedule" icon={<Calendar size={16} />} action="Calendar Page" onAction={() => router.push("/tasks")}>
                        <div className="space-y-3">
                            {(schedule[0]?.tasks.length || 0) > 0 ? schedule[0].tasks.slice(0, 3).map((item) => (
                                <button
                                    key={item.task_id}
                                    onClick={() => router.push("/tasks")}
                                    className="w-full flex items-center gap-4 p-3 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all group"
                                >
                                    <div className="min-w-[58px] flex flex-col items-center">
                                        <p className="text-[10px] font-bold text-indigo-400 font-mono tracking-tighter">{item.start_time || "00:00"}</p>
                                        <div className="h-2 w-px bg-white/10 my-0.5" />
                                        <p className="text-[8px] text-gray-700 font-bold font-mono tracking-tighter">{item.end_time || "N/A"}</p>
                                    </div>
                                    <div className="flex-1 min-w-0 text-left">
                                        <p className="text-[14px] font-bold text-gray-200 truncate group-hover:text-white">{item.task_name}</p>
                                        <p className="text-[9px] text-gray-600 font-bold uppercase tracking-[0.2em] mt-0.5">{item.context}</p>
                                    </div>
                                    <History size={11} className="text-gray-700 group-hover:text-indigo-400" />
                                </button>
                            )) : <EmptyState message="Free schedule" />}
                        </div>
                    </GlassCard>
                </div>
            </div>
        </div>
    );
}

function GlassCard({
    title,
    icon,
    action,
    onAction,
    children,
}: {
    title: string;
    icon: React.ReactNode;
    action: string;
    onAction?: () => void;
    children: React.ReactNode;
}) {
    return (
        <div className="flex flex-col bg-white/[0.03] border border-white/5 backdrop-blur-3xl rounded-[24px] lg:rounded-[32px] overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-5 lg:px-7 py-4 border-b border-white/5 bg-white/[0.015]">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-500/10 rounded-xl text-indigo-400 shadow-inner">{icon}</div>
                    <h3 className="text-[10px] font-bold text-white/80 uppercase tracking-[0.25em]">{title}</h3>
                </div>
                <button
                    onClick={onAction}
                    className="text-[9px] font-bold text-gray-600 hover:text-white uppercase tracking-widest flex items-center gap-1.5 transition-all hover:translate-x-1"
                >
                    {action} <ChevronRight size={8} className="text-indigo-500/80" />
                </button>
            </div>
            <div className="px-6 lg:px-8 py-5">{children}</div>
        </div>
    );
}

function EmptyState({ message }: { message: string }) {
    return (
        <div className="flex flex-col items-center justify-center text-gray-800 py-8">
            <div className="p-3 bg-white/5 rounded-[16px] mb-2">
                <Zap size={20} className="opacity-20" />
            </div>
            <p className="text-[9px] font-bold uppercase tracking-[0.2em] opacity-50">{message}</p>
        </div>
    );
}
