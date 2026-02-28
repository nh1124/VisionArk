import React, { useCallback, useEffect, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight, X, Plus, CheckCircle2, Circle } from "lucide-react"
import { getSchedule, type LBSScheduleDay, type LBSTask } from "../lib/api"

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

function monthStart(d: Date) { return new Date(d.getFullYear(), d.getMonth(), 1) }
function monthEnd(d: Date)   { return new Date(d.getFullYear(), d.getMonth() + 1, 0) }

function gridDays(month: Date): Date[] {
  const start = monthStart(month)
  const end   = monthEnd(month)
  const firstDow = start.getDay()   // 0=Sun
  const lastDow  = end.getDay()
  const days: Date[] = []
  // pad before
  for (let i = firstDow; i > 0; i--) {
    const d = new Date(start); d.setDate(d.getDate() - i); days.push(d)
  }
  // current month
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    days.push(new Date(d))
  }
  // pad after
  for (let i = 1; i <= 6 - lastDow; i++) {
    const d = new Date(end); d.setDate(d.getDate() + i); days.push(d)
  }
  return days
}

// ── types ─────────────────────────────────────────────────────────────────────

interface Props {
  onTaskClick?: (task: LBSTask & { due_date: string }) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function CalendarView({ onTaskClick }: Props) {
  const today = getLocalDate()
  const [month, setMonth] = useState(() => {
    const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1)
  })
  const [schedule, setSchedule] = useState<LBSScheduleDay[]>([])
  const [loading, setLoading] = useState(false)
  const [dayDetails, setDayDetails] = useState<string | null>(null)

  const days = useMemo(() => gridDays(month), [month])

  const fetchMonth = useCallback(async () => {
    setLoading(true)
    try {
      // Fetch the full visible grid range
      const start = getLocalDate(days[0])
      const end   = getLocalDate(days[days.length - 1])
      const data  = await getSchedule(start, end)
      setSchedule(data)
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [days])

  useEffect(() => { fetchMonth() }, [fetchMonth])

  const tasksByDay = useMemo(() => {
    const map: Record<string, LBSScheduleDay["tasks"]> = {}
    schedule.forEach(d => { if (d.tasks?.length) map[d.date] = d.tasks })
    return map
  }, [schedule])

  function prevMonth() { setMonth(m => new Date(m.getFullYear(), m.getMonth() - 1, 1)) }
  function nextMonth() { setMonth(m => new Date(m.getFullYear(), m.getMonth() + 1, 1)) }
  function goToday()  { setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1)) }

  const dayDetailsTasks = dayDetails ? (tasksByDay[dayDetails] ?? []) : []
  const monthLabel = month.toLocaleDateString("en-US", { month: "long", year: "numeric" })
  const isCurrentMonth = (d: Date) => d.getMonth() === month.getMonth()

  return (
    <div className="flex flex-col h-full">
      {/* Month header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h2 className="text-base font-bold text-white">{monthLabel}</h2>
        <div className="flex items-center gap-1">
          <button onClick={prevMonth} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-all"><ChevronLeft size={16} /></button>
          <button onClick={goToday} className="px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-gray-500 hover:text-white transition-all border-x border-gray-800">Today</button>
          <button onClick={nextMonth} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-all"><ChevronRight size={16} /></button>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid grid-cols-7 gap-px bg-gray-800 rounded-xl overflow-hidden border border-gray-800">
          {/* Day-of-week headers */}
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
            <div key={d} className="bg-gray-900/80 py-2 text-center text-[10px] font-black uppercase tracking-widest text-gray-500">
              {d}
            </div>
          ))}

          {/* Day cells */}
          {days.map(d => {
            const ds     = getLocalDate(d)
            const isToday    = ds === today
            const inMonth    = isCurrentMonth(d)
            const dayTasks   = tasksByDay[ds] ?? []
            const doneCnt    = dayTasks.filter(t => t.status === "done" || t.status === "completed").length
            const totalCnt   = dayTasks.length

            return (
              <div
                key={ds}
                onClick={() => { setDayDetails(ds) }}
                className={`
                  min-h-[72px] p-1.5 bg-gray-900/40 transition-all cursor-pointer hover:bg-gray-800/60 relative group
                  ${!inMonth ? "opacity-30" : ""}
                  ${isToday ? "bg-blue-900/10" : ""}
                `}
              >
                {/* Date number */}
                <div className="flex justify-between items-center mb-1">
                  <span className={`text-[11px] font-black leading-none ${isToday ? "text-blue-400" : "text-gray-500"}`}>
                    {d.getDate()}
                    {isToday && <span className="ml-1 inline-block w-1.5 h-1.5 bg-blue-400 rounded-full align-middle" />}
                  </span>
                  {totalCnt > 0 && (
                    <span className="text-[9px] font-bold text-gray-600">{doneCnt}/{totalCnt}</span>
                  )}
                </div>

                {/* Task dots / chips */}
                <div className="flex flex-col gap-0.5">
                  {dayTasks.slice(0, 3).map(t => (
                    <div
                      key={t.task_id}
                      className="flex items-center gap-1 rounded-md px-1 py-0.5 bg-gray-800/80"
                      style={{ borderLeft: `2px solid ${spokeColor(t.context)}` }}
                    >
                      <span className="truncate text-[9px] text-gray-300 leading-tight">{t.task_name}</span>
                    </div>
                  ))}
                  {dayTasks.length > 3 && (
                    <span className="text-[9px] text-gray-600 pl-1">+{dayTasks.length - 3} more</span>
                  )}
                </div>

                {/* Hover border */}
                <div className="absolute inset-0 border border-transparent group-hover:border-gray-700/50 rounded-sm pointer-events-none" />
              </div>
            )
          })}
        </div>
        {loading && (
          <div className="text-center py-4 text-xs text-gray-600 animate-pulse">Loading…</div>
        )}
      </div>

      {/* Day detail panel */}
      {dayDetails && (
        <>
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm z-40" onClick={() => setDayDetails(null)} />
          <div className="fixed right-4 top-24 bottom-4 w-[360px] bg-gray-900/90 border border-gray-800 rounded-2xl flex flex-col z-50 shadow-2xl backdrop-blur-2xl animate-in slide-in-from-right-4 duration-200">
            {/* Panel header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-800">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-cyan-400">Day Tasks</p>
                <p className="text-sm font-bold text-gray-200 mt-0.5">
                  {new Date(dayDetails + "T00:00:00").toLocaleDateString("en-US", {
                    weekday: "long", month: "long", day: "numeric"
                  })}
                </p>
              </div>
              <button onClick={() => setDayDetails(null)} className="p-1.5 hover:bg-gray-800 rounded-xl text-gray-500 hover:text-white transition-all">
                <X size={16} />
              </button>
            </div>

            {/* Task list */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
              {dayDetailsTasks.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center opacity-40 py-10">
                  <Plus size={28} className="text-gray-500 mb-3" />
                  <p className="text-[10px] font-black uppercase tracking-widest text-gray-500">No Tasks</p>
                </div>
              ) : (
                dayDetailsTasks.map(t => {
                  const isDone = t.status === "done" || t.status === "completed"
                  const color  = spokeColor(t.context)
                  return (
                    <div
                      key={t.task_id}
                      onClick={() => { onTaskClick?.({ ...t, active: true, due_date: dayDetails }); setDayDetails(null) }}
                      className="group bg-gray-950/60 border border-gray-800/40 rounded-xl p-3 hover:bg-gray-900 hover:border-gray-700 transition-all cursor-pointer"
                    >
                      <div className="flex items-center gap-2.5 mb-1.5">
                        <div className={isDone ? "text-cyan-500" : "text-gray-600"}>
                          {isDone ? <CheckCircle2 size={15} /> : <Circle size={15} />}
                        </div>
                        <span className={`text-xs font-bold flex-1 truncate ${isDone ? "line-through text-gray-500" : "text-gray-200 group-hover:text-white"}`}>
                          {t.task_name}
                        </span>
                      </div>
                      <div className="flex items-center justify-between pl-6">
                        <span className="text-[9px] font-black uppercase tracking-widest" style={{ color }}>
                          {t.context}
                        </span>
                        <span className="text-[9px] text-gray-700 bg-black/30 rounded px-1.5 py-0.5">
                          Load: {t.load}
                        </span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
