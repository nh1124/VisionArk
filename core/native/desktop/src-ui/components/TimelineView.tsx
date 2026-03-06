import React, { useEffect, useMemo, useRef, useState } from "react"
import { Clock, Lock } from "lucide-react"
import { getSchedule, type LBSScheduleDay, type LBSTask } from "../lib/api"
import type { CalendarStatusFilter } from "./NavSidebar"

// ── helpers ───────────────────────────────────────────────────────────────────

function getLocalDate(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

const SPOKE_COLORS: Record<string, string> = {
  research: "#3B82F6", development: "#10B981", writing: "#F59E0B",
  testing: "#EF4444", planning: "#8B5CF6", review: "#EC4899",
  deployment: "#14B8A6", documentation: "#F97316",
}
function spokeColor(name?: string | null) {
  if (!name) return "#6B7280"
  return SPOKE_COLORS[name.toLowerCase()] ?? "#6B7280"
}

const HOURS = Array.from({ length: 17 }, (_, i) => i + 7) // 07:00 – 23:00
const HOUR_H = 72 // px per hour

function getWeekDays(anchorDate: string): string[] {
  const d = new Date(anchorDate + "T00:00:00")
  const dow = d.getDay() // 0=Sun
  const sun = new Date(d); sun.setDate(d.getDate() - dow)
  return Array.from({ length: 7 }, (_, i) => {
    const next = new Date(sun); next.setDate(sun.getDate() + i)
    return getLocalDate(next)
  })
}

function timeToY(t: string | null): number {
  if (!t) return 0
  const [h, m] = t.split(":").map(Number)
  return ((h * 60 + m) - 7 * 60) / 60 * HOUR_H
}

function timeDuration(start: string | null, end: string | null): number {
  if (!start || !end) return HOUR_H
  const [h1, m1] = start.split(":").map(Number)
  const [h2, m2] = end.split(":").map(Number)
  const mins = (h2 * 60 + m2) - (h1 * 60 + m1)
  return Math.max(mins / 60 * HOUR_H, 24)
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  targetDate: string
  onTaskClick?: (task: LBSTask & { due_date: string }) => void
  refreshKey?: number
  filterContext?: string
  statusFilter?: CalendarStatusFilter
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function TimelineView({
  targetDate,
  onTaskClick,
  refreshKey,
  filterContext,
  statusFilter = "all",
}: Props) {
  const today = getLocalDate()
  const [schedule, setSchedule] = useState<LBSScheduleDay[]>([])
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const weekDays = useMemo(() => getWeekDays(targetDate), [targetDate])

  useEffect(() => {
    setLoading(true)
    getSchedule(weekDays[0], weekDays[6])
      .then(d => setSchedule(Array.isArray(d) ? d : []))
      .catch(() => { })
      .finally(() => setLoading(false))
  }, [weekDays, refreshKey])

  // Scroll to 8am on mount
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = HOUR_H * 1 // 8am = 1h from 7am
    }
  }, [])

  if (loading && schedule.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-900/20 rounded-2xl border border-gray-800 animate-pulse text-gray-600 text-xs font-bold uppercase tracking-widest">
        Loading Timeline…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-gray-900/10 border border-gray-800 rounded-2xl overflow-hidden">
      {/* Min-width wrapper for horizontal scroll on small screens */}
      <div className="flex flex-col h-full min-w-[600px]">

        {/* Week header */}
        <div className="grid grid-cols-[52px_1fr] flex-shrink-0">
          <div className="border-r border-b border-gray-800 flex items-center justify-center bg-gray-900/40">
            <Clock size={14} className="text-gray-600" />
          </div>
          <div className="grid grid-cols-7 divide-x divide-gray-800/50 bg-gray-900/20">
            {weekDays.map(ds => {
              const d = new Date(ds + "T00:00:00")
              const isToday = ds === today
              return (
                <div key={ds} className={`flex flex-col items-center py-2.5 border-b border-gray-800 ${isToday ? "bg-blue-600/10" : ""}`}>
                  <span className={`text-[9px] font-black uppercase tracking-widest ${isToday ? "text-blue-400" : "text-gray-500"}`}>
                    {d.toLocaleDateString("en-US", { weekday: "short" })}
                  </span>
                  <span className={`text-lg font-bold mt-0.5 leading-none ${isToday ? "text-white" : "text-gray-400"}`}>
                    {d.getDate()}
                  </span>
                  {isToday && <div className="w-1 h-1 bg-blue-500 rounded-full mt-1 animate-pulse" />}
                </div>
              )
            })}
          </div>
        </div>

        {/* All-day row */}
        <div className="grid grid-cols-[52px_1fr] flex-shrink-0 border-b border-gray-800/50 bg-gray-950/20">
          <div className="border-r border-gray-800 flex items-center justify-center p-1">
            <span className="text-[8px] font-black uppercase text-gray-600 [writing-mode:vertical-lr] rotate-180">All Day</span>
          </div>
          <div className="grid grid-cols-7 divide-x divide-gray-800/30">
            {weekDays.map(ds => {
              const day = schedule.find(d => d.date === ds)
              const filtered = (day?.tasks ?? []).filter((t) => {
                const done = t.status === "done" || t.status === "completed"
                if (filterContext && t.context !== filterContext) return false
                if (statusFilter === "open") return !done
                if (statusFilter === "done") return done
                return true
              })
              const allDay = filtered.filter(t => !t.start_time)
              return (
                <div key={ds} className="min-h-[40px] p-1 flex flex-col gap-0.5 bg-white/[0.01]">
                  {allDay.map(t => (
                    <div
                      key={t.task_id}
                      onClick={() => onTaskClick?.({ ...t, base_load_score: t.load, rule_type: "ONCE", active: true, due_date: ds })}
                      className="text-[9px] font-bold px-1.5 py-1 rounded-md border border-white/5 bg-gray-900/80 cursor-pointer hover:bg-white/10 transition-colors truncate"
                      style={{ borderLeft: `2px solid ${spokeColor(t.context)}` }}
                      title={t.task_name}
                    >
                      {t.task_name}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>

        {/* Scrollable time grid */}
        <div
          className="grid grid-cols-[52px_1fr] flex-1 overflow-y-auto relative"
          ref={scrollRef}
          style={{ scrollbarWidth: "none" }}
        >
          {/* Y-axis */}
          <div className="sticky left-0 z-20 bg-gray-950/80 backdrop-blur-md border-r border-gray-800">
            {HOURS.map(h => (
              <div key={h} style={{ height: HOUR_H }} className="flex justify-center pt-1.5">
                <span className="text-[9px] font-black text-gray-600 tabular-nums">
                  {String(h).padStart(2, "0")}:00
                </span>
              </div>
            ))}
          </div>

          {/* Grid */}
          <div className="relative grid grid-cols-7 divide-x divide-gray-800/20" style={{ minHeight: HOUR_H * HOURS.length }}>
            {/* Horizontal lines */}
            {HOURS.map(h => (
              <div
                key={`line-${h}`}
                style={{ top: (h - 7) * HOUR_H }}
                className="absolute left-0 right-0 border-t border-gray-800/30 pointer-events-none"
              />
            ))}

            {/* Day columns */}
            {weekDays.map(ds => {
              const day = schedule.find(d => d.date === ds)
              const timed = (day?.tasks ?? []).filter((t) => {
                const done = t.status === "done" || t.status === "completed"
                if (!t.start_time) return false
                if (filterContext && t.context !== filterContext) return false
                if (statusFilter === "open") return !done
                if (statusFilter === "done") return done
                return true
              })
              return (
                <div key={ds} className="relative px-0.5 py-0.5">
                  {timed.map(t => {
                    const top = timeToY(t.start_time)
                    const height = timeDuration(t.start_time, t.end_time)
                    const color = spokeColor(t.context)
                    return (
                      <div
                        key={t.task_id}
                        onClick={() => onTaskClick?.({ ...t, base_load_score: t.load, rule_type: "ONCE", active: true, due_date: ds })}
                        style={{
                          top: top + 2,
                          height: height - 4,
                          borderColor: `${color}40`,
                          backgroundColor: `${color}15`,
                        }}
                        className="absolute inset-x-1 p-1.5 rounded-xl border cursor-pointer group hover:bg-white/5 transition-all overflow-hidden z-10 backdrop-blur-sm"
                      >
                        {/* Accent line */}
                        <div className="absolute left-0 top-0 bottom-0 w-0.5 rounded-full" style={{ backgroundColor: color }} />

                        <div className="flex flex-col h-full pl-1.5">
                          <span
                            className="text-[9px] font-bold leading-tight line-clamp-2 group-hover:text-white transition-colors"
                            style={{ color }}
                          >
                            {t.task_name}
                          </span>
                          {height > 36 && (
                            <div className="mt-auto flex items-center justify-between text-[7px] font-black uppercase tracking-widest opacity-60">
                              <span>{t.start_time?.slice(0, 5)} – {t.end_time?.slice(0, 5)}</span>
                              {t.is_locked && <Lock size={8} className="text-gray-500" />}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
