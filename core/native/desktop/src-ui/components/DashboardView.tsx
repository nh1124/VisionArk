import React, { useEffect, useState, useMemo } from "react"
import {
  Clock, Cloud, CheckCircle2, Layout, Calendar,
  Activity, ArrowUpRight, ChevronRight, Zap, Target,
  Star, Briefcase, ListTodo, BrainCircuit, Play, History,
  Thermometer, Wind, Droplets
} from "lucide-react"
import {
  getMe, listLBSTasks, getSchedule,
  listProjectsWithProgress, getRecentMemories, getSettings, listRuns,
  type LBSTask, type LBSScheduleDay, type ProjectWithProgress, type Memory
} from "../lib/api"

type WeatherData = { temp: number, code: number, description: string }
type DashboardSnapshot = {
  profile: any
  settings: any
  tasks: LBSTask[]
  schedule: LBSScheduleDay[]
  projects: ProjectWithProgress[]
  mergedActivities: any[]
  weather: WeatherData | null
  fetchedAt: number
}

const DASHBOARD_CACHE_TTL_MS = 2 * 60 * 1000
let dashboardSnapshotCache: DashboardSnapshot | null = null

/**
 * Brushed up Dashboard View - No-Scroll Version
 * Features:
 * - Full-height layout (h-full) with overflow-hidden
 * - 2x2 Equal-size Grid scaled to fit viewport
 * - Exactly 3 items per section
 */
export default function DashboardView({ onNavigate }: { onNavigate?: (v: any, id?: string) => void }) {
  const initialSnapshot = dashboardSnapshotCache
  const [currentTime, setCurrentTime] = useState(new Date())
  const [profile, setProfile] = useState<any>(initialSnapshot?.profile ?? null)
  const [settings, setSettings] = useState<any>(initialSnapshot?.settings ?? null)
  const [weather, setWeather] = useState<WeatherData | null>(initialSnapshot?.weather ?? null)

  const [tasks, setTasks] = useState<LBSTask[]>(initialSnapshot?.tasks ?? [])
  const [schedule, setSchedule] = useState<LBSScheduleDay[]>(initialSnapshot?.schedule ?? [])
  const [projects, setProjects] = useState<ProjectWithProgress[]>(initialSnapshot?.projects ?? [])
  const [mergedActivities, setMergedActivities] = useState<any[]>(initialSnapshot?.mergedActivities ?? [])

  const [loading, setLoading] = useState(!initialSnapshot)

  // Real-time clock
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  // Initial Data Fetch
  useEffect(() => {
    const applySnapshot = (snapshot: DashboardSnapshot) => {
      setProfile(snapshot.profile)
      setSettings(snapshot.settings)
      setTasks(snapshot.tasks)
      setSchedule(snapshot.schedule)
      setProjects(snapshot.projects)
      setMergedActivities(snapshot.mergedActivities)
      setWeather(snapshot.weather)
    }

    async function loadData() {
      const now = Date.now()
      if (dashboardSnapshotCache && now - dashboardSnapshotCache.fetchedAt < DASHBOARD_CACHE_TTL_MS) {
        applySnapshot(dashboardSnapshotCache)
        setLoading(false)
        return
      }

      if (!dashboardSnapshotCache) {
        setLoading(true)
      }

      try {
        const todayStr = new Date().toISOString().split("T")[0]
        const [me, sets, t, s, p, m, r] = await Promise.all([
          getMe().catch(() => null),
          getSettings().catch(() => ({ general_settings: { location: "Tokyo, Japan" } })),
          listLBSTasks({ targetDate: todayStr }).catch(() => []),
          getSchedule(todayStr, todayStr).catch(() => []),
          listProjectsWithProgress().catch(() => []),
          getRecentMemories(10).catch(() => []),
          listRuns({ limit: 10 }).catch(() => [])
        ])

        setProfile(me)
        setSettings(sets)
        setTasks(t)
        setSchedule(s || [])

        const combined = [
          ...m.map((i: any) => ({ ...i, type: 'memory', timestamp: new Date(i.created_at).getTime() })),
          ...r.map((i: any) => ({ ...i, type: 'run', timestamp: new Date(i.created_at).getTime() }))
        ].sort((a, b) => b.timestamp - a.timestamp)

        setMergedActivities(combined)
        const sortedProjects = p.sort((a, b) => b.total_tasks - a.total_tasks)
        setProjects(sortedProjects)

        const location = sets?.general_settings?.location || "Tokyo, Japan"
        const weatherData = await fetchWeather(location)
        setWeather(weatherData)

        dashboardSnapshotCache = {
          profile: me,
          settings: sets,
          tasks: t,
          schedule: s || [],
          projects: sortedProjects,
          mergedActivities: combined,
          weather: weatherData,
          fetchedAt: Date.now(),
        }

      } catch (err) {
        console.error("Dashboard data load failed:", err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const fetchWeather = async (location: string): Promise<WeatherData | null> => {
    try {
      const geoRes = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(location)}&count=1&language=en&format=json`)
      const geoData = await geoRes.json()
      if (!geoData.results?.length) return null
      const { latitude, longitude } = geoData.results[0]
      const weatherRes = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current_weather=true`)
      const weatherData = await weatherRes.json()
      const cw = weatherData.current_weather
      return {
        temp: Math.round(cw.temperature),
        code: cw.weathercode,
        description: getWeatherDescription(cw.weathercode)
      }
    } catch (e) {
      console.warn("Weather fetch failed:", e)
      return null
    }
  }

  const getWeatherDescription = (code: number) => {
    if (code === 0) return "Clear sky"
    if (code <= 3) return "Partly cloudy"
    if (code <= 48) return "Foggy"
    if (code <= 57) return "Drizzle"
    if (code <= 67) return "Rainy"
    if (code <= 77) return "Snowy"
    if (code <= 82) return "Showers"
    if (code <= 99) return "Thunderstorm"
    return "Unknown"
  }

  const greeting = useMemo(() => {
    const hour = currentTime.getHours()
    if (hour < 12) return "Good morning"
    if (hour < 18) return "Good afternoon"
    return "Good evening"
  }, [currentTime])

  if (loading) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-gray-950">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin" />
          <p className="text-gray-500 font-medium font-mono text-xs tracking-widest uppercase animate-pulse">Initializing Dashboard</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 h-full flex flex-col overflow-hidden bg-gray-950 p-6 lg:p-8">
      <div className="flex-1 flex flex-col max-w-7xl mx-auto w-full space-y-4 lg:space-y-6">

        {/* --- Top Banner (Fixed height or constrained) --- */}
        <div className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-indigo-700 via-purple-700 to-pink-600 p-6 lg:p-7 shadow-2xl flex-shrink-0 border border-white/5">
          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <h1 className="text-3xl lg:text-4xl font-bold text-white tracking-tight leading-[1.1]">
                {greeting},<br />
                <span className="text-white/70 font-medium">{profile?.username || "Commander"}</span>
              </h1>
              <div className="flex items-center gap-2 text-white/40 text-[9px] font-bold uppercase tracking-[0.2em] pt-1">
                <Target size={11} className="text-emerald-400" />
                {tasks.filter(t => t.status !== "done").length} tasks remaining
              </div>
            </div>

            <div className="flex items-center gap-6 lg:gap-8 bg-black/20 backdrop-blur-3xl rounded-[24px] p-4 lg:p-5 border border-white/5 shadow-2xl">
              <div className="text-right">
                <p className="text-3xl lg:text-4xl font-mono font-bold tracking-tighter tabular-nums text-white leading-none">
                  {currentTime.toLocaleTimeString("en-US", { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </p>
                <p className="text-[8px] font-bold text-purple-200/30 uppercase tracking-[0.4em] mt-2">
                  {currentTime.toLocaleDateString("en-US", { weekday: 'long', month: 'short', day: 'numeric' }).replace(',', ' /')}
                </p>
              </div>
              <div className="h-8 lg:h-10 w-px bg-white/10" />
              <div className="flex items-center gap-3 lg:gap-4">
                <div className="p-2.5 lg:p-3 bg-white/5 rounded-xl">
                  <Cloud size={20} className="text-blue-200" />
                </div>
                <div>
                  <p className="text-xl lg:text-3xl font-bold text-white leading-none">{weather?.temp ?? "--"}°C</p>
                  <p className="text-[8px] font-bold text-blue-200/50 uppercase tracking-widest mt-1">
                    {settings?.general_settings?.location?.split(',')[0] || "Tokyo"} / {weather?.description || "Syncing"}
                  </p>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute top-[-20%] right-[-10%] w-64 lg:w-96 h-64 lg:h-96 bg-white/5 rounded-full blur-3xl opacity-50" />
          <div className="absolute bottom-[-30%] left-[5%] w-[400px] lg:w-[600px] h-[400px] lg:h-[600px] bg-purple-500/5 rounded-full blur-[140px]" />
        </div>

        {/* --- 2x2 Equal-Size Grid (Flexible to fill space) --- */}
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-4 lg:gap-5 pb-1">

          {/* Tile 1: Project Progress */}
          <GlassCard title="Project Progress" icon={<Layout size={16} />} action="Project Page" onAction={() => onNavigate?.("projects")}>
            <div className="space-y-3 lg:space-y-4 flex flex-col justify-center h-full">
              {projects.length > 0 ? projects.slice(0, 3).map(project => (
                <div key={project.id} className="space-y-1.5 group cursor-pointer" onClick={() => onNavigate?.("chat", project.id)}>
                  <div className="flex justify-between items-end">
                    <div className="flex items-center gap-2.5">
                      <div className="w-1 h-1 rounded-full bg-cyan-500 shadow-[0_0_6px_rgba(6,182,212,0.4)]" />
                      <span className="text-[12px] font-semibold text-gray-200 group-hover:text-white transition-colors tracking-tight truncate max-w-[150px] lg:max-w-none">
                        {project.display_name || project.name}
                      </span>
                    </div>
                    <span className="text-[8px] font-bold text-gray-600 tracking-widest uppercase">
                      {project.completed_tasks}/{project.total_tasks} <span className="text-cyan-500/50 ml-1">{Math.round(project.progress)}%</span>
                    </span>
                  </div>
                  <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden border border-white/5">
                    <div
                      className="h-full bg-gradient-to-r from-indigo-500 via-cyan-500 to-emerald-400 opacity-70 group-hover:opacity-100 transition-all duration-1000"
                      style={{ width: `${project.progress}%` }}
                    />
                  </div>
                </div>
              )) : (
                <EmptyState message="No trackable projects" />
              )}
            </div>
          </GlassCard>

          {/* Tile 2: Recent Activity */}
          <GlassCard title="Recent Activity" icon={<Activity size={16} />} action="Run Center" onAction={() => onNavigate?.("run_center")}>
            <div className="space-y-4 lg:space-y-5 flex flex-col justify-center h-full pr-1">
              {mergedActivities.length > 0 ? mergedActivities.slice(0, 3).map((item, idx) => (
                <div key={idx} className="relative pl-5 group cursor-pointer" onClick={() => onNavigate?.("run_center")}>
                  <div className={`absolute left-0 top-1.5 w-1 h-1 rounded-full ${item.type === 'run' ? 'bg-orange-500 shadow-[0_0_8px_rgba(249,115,22,0.4)]' : 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.4)]'}`} />
                  <div className="absolute left-[1.5px] top-4 bottom-[-20px] w-[0.5px] bg-white/5 group-last:hidden" />
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[8px] font-bold text-gray-600 uppercase tracking-[0.2em]">
                        {item.type === 'run' ? 'Agent Run' : 'Core Memory'}
                      </span>
                      <span className="text-[7px] font-medium text-gray-700 font-mono">
                        {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="text-[11px] font-medium text-gray-400 leading-tight group-hover:text-white transition-colors line-clamp-1">
                      {item.type === 'run' ? (item.summary || `Execution Run ${item.id.slice(0, 8)}`) : item.content}
                    </p>
                  </div>
                </div>
              )) : (
                <EmptyState message="Quiet for now" />
              )}
            </div>
          </GlassCard>

          {/* Tile 3: Today's Tasks */}
          <GlassCard title="Today's Tasks" icon={<ListTodo size={16} />} action="Tasks Page" onAction={() => onNavigate?.("tasks")}>
            <div className="space-y-2 lg:space-y-3 flex flex-col justify-center h-full">
              {tasks.length > 0 ? tasks.slice(0, 3).map(task => (
                <div key={task.task_id} onClick={() => onNavigate?.("tasks")} className="flex items-center gap-3 p-2.5 lg:p-3 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-white/10 transition-all group cursor-pointer">
                  <div className={`flex-shrink-0 w-2 h-2 rounded-full border-1.5 ${task.status === "done" ? "bg-cyan-500 border-cyan-400/50 shadow-[0_0_8px_rgba(6,182,212,0.3)]" : "bg-transparent border-gray-700"}`} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-[12px] font-bold truncate ${task.status === "done" ? "text-gray-600 line-through" : "text-gray-200"}`}>
                      {task.task_name}
                    </p>
                    <p className="text-[8px] font-bold text-gray-600 uppercase tracking-widest mt-0.5 group-hover:text-gray-500 transition-colors">
                      {task.context}
                    </p>
                  </div>
                  <ArrowUpRight size={10} className="text-gray-800 group-hover:text-cyan-500 transition-colors" />
                </div>
              )) : (
                <EmptyState message="All tasks clear" />
              )}
            </div>
          </GlassCard>

          {/* Tile 4: Today's Schedule */}
          <GlassCard title="Today's Schedule" icon={<Calendar size={16} />} action="Calendar Page" onAction={() => onNavigate?.("calendar")}>
            <div className="space-y-2 lg:space-y-3 flex flex-col justify-center h-full">
              {(schedule[0]?.tasks.length || 0) > 0 ? schedule[0].tasks.slice(0, 3).map(item => (
                <div key={item.task_id} onClick={() => onNavigate?.("calendar")} className="flex items-center gap-4 p-2.5 lg:p-3 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-all group cursor-pointer">
                  <div className="min-w-[45px] lg:min-w-[55px] flex flex-col items-center">
                    <p className="text-[10px] font-bold text-indigo-400 group-hover:text-indigo-300 transition-colors font-mono tracking-tighter">{item.start_time || "00:00"}</p>
                    <div className="h-2 w-px bg-white/10 my-0.5" />
                    <p className="text-[8px] text-gray-700 font-bold font-mono tracking-tighter">{item.end_time || "N/A"}</p>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`text-[12px] font-bold text-gray-200 truncate group-hover:text-white transition-colors`}>{item.task_name}</p>
                    <p className="text-[8px] text-gray-600 font-bold uppercase tracking-[0.2em] mt-0.5">{item.context}</p>
                  </div>
                  <History size={10} className="text-gray-800 group-hover:text-indigo-400 transition-colors" />
                </div>
              )) : (
                <EmptyState message="Free schedule" />
              )}
            </div>
          </GlassCard>

        </div>
      </div>
    </div>
  )
}

// --- Sub-components ---

function GlassCard({ title, icon, action, onAction, children }: { title: string, icon: React.ReactNode, action: string, onAction?: () => void, children: React.ReactNode }) {
  return (
    <div className="flex flex-col bg-white/[0.03] border border-white/5 backdrop-blur-3xl rounded-[24px] lg:rounded-[32px] overflow-hidden shadow-2xl min-h-0 flex-1">
      <div className="flex items-center justify-between px-5 lg:px-7 py-3 lg:py-4 border-b border-white/5 bg-white/[0.015] flex-shrink-0">
        <div className="flex items-center gap-2.5 lg:gap-3">
          <div className="p-1.5 lg:p-2 bg-indigo-500/10 rounded-xl text-indigo-400 shadow-inner">{icon}</div>
          <h3 className="text-[9px] lg:text-[10px] font-bold text-white/80 uppercase tracking-[0.25em]">{title}</h3>
        </div>
        <button onClick={onAction} className="text-[8px] lg:text-[9px] font-bold text-gray-600 hover:text-white uppercase tracking-widest flex items-center gap-1.5 transition-all hover:translate-x-1">
          {action} <ChevronRight size={8} className="text-indigo-500/80" />
        </button>
      </div>
      <div className="px-6 lg:px-8 py-4 lg:py-6 flex-1 flex flex-col min-h-0">
        {children}
      </div>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 text-gray-800">
      <div className="p-3 bg-white/2 rounded-[16px] mb-2">
        <Zap size={20} className="opacity-10" />
      </div>
      <p className="text-[8px] font-bold uppercase tracking-[0.2em] opacity-40">{message}</p>
    </div>
  )
}
