"use client"

import { useEffect, useState, useCallback } from "react"
import { RefreshCw, Square, RotateCcw, ChevronDown, ChevronRight, Activity } from "lucide-react"
import { apiFetch } from "@/lib/api"

// ── Types ─────────────────────────────────────────────────────────────────────

type RunStatus = "queued" | "running" | "waiting_approval" | "completed" | "failed" | "canceled"
type ExecStatus = "pending" | "running" | "waiting_approval" | "succeeded" | "failed" | "rejected"

interface AgentRun {
  id: string
  status: RunStatus
  summary: string | null
  project_id: string | null
  session_id: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  executions: RunExecution[]
}

interface RunExecution {
  id: string
  run_id: string
  kind: string
  status: ExecStatus
  risk_level: string
  payload: Record<string, unknown>
  result: Record<string, unknown> | null
  error_log: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const RUN_STATUS_COLOR: Record<RunStatus, string> = {
  queued: "text-gray-400 bg-gray-800",
  running: "text-blue-300 bg-blue-900/40",
  waiting_approval: "text-yellow-300 bg-yellow-900/40",
  completed: "text-green-300 bg-green-900/40",
  failed: "text-red-300 bg-red-900/40",
  canceled: "text-gray-500 bg-gray-800",
}

const EXEC_STATUS_COLOR: Record<ExecStatus, string> = {
  pending: "text-gray-400 bg-gray-800",
  running: "text-blue-300 bg-blue-900/40",
  waiting_approval: "text-yellow-300 bg-yellow-900/40",
  succeeded: "text-green-300 bg-green-900/40",
  failed: "text-red-300 bg-red-900/40",
  rejected: "text-orange-300 bg-orange-900/40",
}

function StatusChip({ status, map }: { status: string; map: Record<string, string> }) {
  const cls = map[status] ?? "text-gray-400 bg-gray-800"
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {status.replace("_", " ")}
    </span>
  )
}

function fmtDate(s: string | null) {
  if (!s) return "—"
  return new Date(s).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  })
}

const ACTIVE_STATUSES: RunStatus[] = ["queued", "running", "waiting_approval"]

// ── Execution Row ─────────────────────────────────────────────────────────────

function ExecutionRow({ exec, runId, onRefresh }: {
  exec: RunExecution
  runId: string
  onRefresh: () => void
}) {
  const [retrying, setRetrying] = useState(false)
  const canRetry = exec.status === "failed" || exec.status === "rejected"

  const handleRetry = async () => {
    setRetrying(true)
    try {
      const res = await apiFetch(`/api/runs/${runId}/executions/${exec.id}/retry`, { method: "POST" })
      if (res.ok) onRefresh()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="flex items-center justify-between px-4 py-2.5 bg-gray-800/50 rounded-lg gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-mono text-gray-300 truncate">{exec.kind}</span>
          <StatusChip status={exec.status} map={EXEC_STATUS_COLOR} />
          <span className="text-xs text-gray-600">{exec.risk_level}</span>
        </div>
        {exec.error_log && (
          <p className="text-xs text-red-400 mt-0.5 truncate">{exec.error_log}</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-600 hidden sm:block">{fmtDate(exec.created_at)}</span>
        {canRetry && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="flex items-center gap-1 px-2 py-1 text-xs rounded-md bg-gray-700 hover:bg-blue-700/60 text-gray-300 hover:text-white transition-colors disabled:opacity-50"
          >
            <RotateCcw size={11} />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

// ── Run Row ───────────────────────────────────────────────────────────────────

function RunRow({ run, onRefresh }: { run: AgentRun; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false)
  const [stopping, setStopping] = useState(false)
  const isActive = ACTIVE_STATUSES.includes(run.status)

  const handleStop = async () => {
    setStopping(true)
    try {
      const res = await apiFetch(`/api/runs/${run.id}/cancel`, { method: "POST" })
      if (res.ok) onRefresh()
    } finally {
      setStopping(false)
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-800/40 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="text-gray-600">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <StatusChip status={run.status} map={RUN_STATUS_COLOR} />
            <span className="text-sm text-gray-200 truncate">
              {run.summary || run.id.slice(0, 12)}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs text-gray-600">{fmtDate(run.created_at)}</span>
            {run.executions.length > 0 && (
              <span className="text-xs text-gray-600">{run.executions.length} exec</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0" onClick={e => e.stopPropagation()}>
          {isActive && (
            <button
              onClick={handleStop}
              disabled={stopping}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md bg-red-900/40 hover:bg-red-700/60 text-red-300 hover:text-white transition-colors disabled:opacity-50"
            >
              <Square size={11} />
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Executions */}
      {expanded && run.executions.length > 0 && (
        <div className="border-t border-gray-800 p-3 space-y-2">
          {run.executions.map(exec => (
            <ExecutionRow key={exec.id} exec={exec} runId={run.id} onRefresh={onRefresh} />
          ))}
        </div>
      )}
      {expanded && run.executions.length === 0 && (
        <div className="border-t border-gray-800 px-4 py-3 text-xs text-gray-600">
          No executions yet.
        </div>
      )}
    </div>
  )
}

// ── Status filter tabs ────────────────────────────────────────────────────────

const STATUS_TABS = [
  { label: "All", value: "" },
  { label: "Active", value: "active" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
  { label: "Canceled", value: "canceled" },
]

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RunCenterPage() {
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState("")
  const [refreshing, setRefreshing] = useState(false)

  const fetchRuns = useCallback(async () => {
    try {
      const params = statusFilter && statusFilter !== "active"
        ? `?status=${statusFilter}&limit=50`
        : "?limit=50"
      const res = await apiFetch(`/api/runs${params}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      let list: AgentRun[] = Array.isArray(data) ? data : (data.runs ?? [])
      // Client-side filter for "active"
      if (statusFilter === "active") {
        list = list.filter(r => ACTIVE_STATUSES.includes(r.status))
      }
      setRuns(list)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load runs")
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [statusFilter])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  // Auto-refresh every 5 s when there are active runs
  useEffect(() => {
    const hasActive = runs.some(r => ACTIVE_STATUSES.includes(r.status))
    if (!hasActive) return
    const id = setInterval(fetchRuns, 5000)
    return () => clearInterval(id)
  }, [runs, fetchRuns])

  const handleRefresh = () => {
    setRefreshing(true)
    fetchRuns()
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-gray-950/90 backdrop-blur border-b border-gray-800">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-blue-400" />
            <h1 className="text-lg font-semibold text-white">Run Center</h1>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="max-w-5xl mx-auto px-4 pb-3 flex gap-1 overflow-x-auto">
          {STATUS_TABS.map(tab => (
            <button
              key={tab.value}
              onClick={() => setStatusFilter(tab.value)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${statusFilter === tab.value
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-4 py-6">
        {loading && (
          <div className="flex items-center justify-center py-20 text-gray-600 text-sm">
            Loading runs…
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-900/20 border border-red-800 rounded-xl p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {!loading && !error && runs.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-600">
            <Activity size={32} className="opacity-30" />
            <p className="text-sm">No runs yet.</p>
          </div>
        )}

        {!loading && !error && runs.length > 0 && (
          <div className="space-y-3">
            {runs.map(run => (
              <RunRow key={run.id} run={run} onRefresh={fetchRuns} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
