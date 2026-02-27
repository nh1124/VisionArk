import React, { useEffect, useState } from "react"
import { getDashboard } from "../lib/api"

interface DashboardData {
  today: {
    adjusted_load: number
    level: string
    task_count: number
    unique_contexts: number
    cap: number
  }
  weekly: {
    average_load: number
    over_days: number
    recovery_rate: number
  }
}

export default function DashboardView() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getDashboard()
      .then(setData)
      .catch(() => { })
      .finally(() => setLoading(false))
  }, [])

  const getLoadStatus = (pct: number) => {
    if (pct <= 60) return { label: "Focus", color: "text-emerald-400", bg: "bg-emerald-500", border: "border-emerald-500/30" }
    if (pct <= 90) return { label: "Flow", color: "text-blue-400", bg: "bg-blue-500", border: "border-blue-500/30" }
    if (pct <= 110) return { label: "Peak", color: "text-orange-400", bg: "bg-orange-500", border: "border-orange-500/30" }
    return { label: "Overload", color: "text-red-400", bg: "bg-red-500", border: "border-red-500/30" }
  }

  const getRecoveryStatus = (score: number) => {
    if (score <= 30) return { label: "Low", color: "text-red-400" }
    if (score <= 70) return { label: "Recovering", color: "text-orange-400" }
    return { label: "Ready", color: "text-emerald-400" }
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center h-full">
        <div className="text-gray-500 animate-pulse">Loading dashboard...</div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex-1 p-8">
        <div className="p-6 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm">
          Failed to load dashboard data. Please check your connection.
        </div>
      </div>
    )
  }

  const loadPct = data.today ? (data.today.adjusted_load / data.today.cap) * 100 : 0
  const loadStatus = getLoadStatus(loadPct)
  const recoveryStatus = getRecoveryStatus(data.weekly?.recovery_rate || 0)

  return (
    <div className="flex-1 overflow-y-auto p-6 lg:p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <h1 className="text-3xl font-bold text-white tracking-tight mb-8">Dashboard</h1>

        {/* Primary Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Load Capacity */}
          <div className={`bg-gray-900/40 border-2 ${loadStatus.border} rounded-2xl p-8 relative overflow-hidden backdrop-blur-sm shadow-xl`}>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Efficiency</span>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest ${loadStatus.bg}/20 ${loadStatus.color} border border-current/20`}>
                  Dynamic Target
                </span>
              </div>
              <div className="flex items-baseline gap-2 mb-4">
                <span className={`text-6xl font-bold tracking-tight ${loadStatus.color}`}>{loadStatus.label}</span>
                <span className="text-[10px] font-medium text-gray-500 tabular-nums">({loadPct.toFixed(0)}%)</span>
              </div>
              <div className="h-2 bg-gray-800/50 rounded-full overflow-hidden mb-3">
                <div
                  className={`h-full rounded-full transition-all duration-1000 ease-out ${loadStatus.bg}`}
                  style={{ width: `${Math.min(100, loadPct)}%` }}
                />
              </div>
              <div className="flex justify-between text-[9px] font-black text-gray-600 uppercase tracking-wider">
                <span>{data.today?.adjusted_load.toFixed(1)} <span className="text-[8px] opacity-50">Score</span></span>
                <span>{data.today?.cap} <span className="text-[8px] opacity-50">Limit</span></span>
              </div>
            </div>
            <div className={`absolute -right-20 -bottom-20 w-64 h-64 rounded-full blur-[100px] opacity-10 ${loadStatus.bg}`} />
          </div>

          {/* Weekly Recovery */}
          <div className="bg-gray-900/40 border-2 border-gray-800 rounded-2xl p-8 backdrop-blur-sm shadow-xl relative overflow-hidden">
            <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Sustainability</span>
            <div className="mt-8 flex items-baseline gap-2">
              <span className={`text-4xl font-bold tracking-tight ${recoveryStatus.color}`}>{recoveryStatus.label}</span>
              <span className="text-[10px] font-medium text-gray-600 tabular-nums">{(data.weekly?.recovery_rate || 0).toFixed(0)}%</span>
            </div>
            <div className="mt-8 flex gap-1.5">
              {[1, 2, 3, 4, 5, 6, 7].map((i) => (
                <div
                  key={i}
                  className={`h-1.5 flex-1 rounded-full ${i <= (data.weekly?.over_days || 0) ? "bg-red-500/50" : "bg-emerald-500/30"
                    }`}
                />
              ))}
            </div>
            <p className="text-[8px] font-black text-gray-700 mt-2.5 uppercase tracking-widest flex justify-between">
              <span>Weekly Load Strain</span>
              <span className="text-red-500/80">{data.weekly?.over_days || 0} Critical Days</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
