import React, { useEffect, useState } from "react"
import {
  RefreshCw, CheckCircle, XCircle, Clock, AlertTriangle, Loader,
  Plus, ShieldCheck, ShieldX, ChevronRight, Activity, X, Monitor,
  Square, RotateCcw,
} from "lucide-react"
import type { AgentRun, RunExecution, RunApproval, NativeDevice } from "../../../shared/types"
import {
  listRuns, createRun, approveExecution, rejectExecution, listDevices,
  cancelRun, retryExecution,
} from "../../../bridge/api"

// ── Status styles ──────────────────────────────────────────────────────────────

const RUN_STATUS: Record<string, { label: string; cls: string }> = {
  queued: { label: "Queued", cls: "text-gray-400 bg-gray-800" },
  running: { label: "Running", cls: "text-blue-400 bg-blue-400/10" },
  waiting_approval: { label: "Needs Approval", cls: "text-yellow-400 bg-yellow-400/10" },
  completed: { label: "Completed", cls: "text-emerald-400 bg-emerald-400/10" },
  failed: { label: "Failed", cls: "text-red-400 bg-red-400/10" },
  canceled: { label: "Canceled", cls: "text-red-300 bg-red-300/10" },
}

const EXEC_STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: "Pending", cls: "text-gray-400 bg-gray-800" },
  running: { label: "Running", cls: "text-blue-400 bg-blue-400/10" },
  waiting_approval: { label: "Needs Approval", cls: "text-yellow-400 bg-yellow-400/10" },
  succeeded: { label: "Succeeded", cls: "text-emerald-400 bg-emerald-400/10" },
  failed: { label: "Failed", cls: "text-red-400 bg-red-400/10" },
  rejected: { label: "Rejected", cls: "text-red-300 bg-red-300/10" },
}

const RISK_CLS: Record<string, string> = {
  low: "text-emerald-400",
  medium: "text-yellow-400",
  high: "text-orange-400",
  critical: "text-red-400",
}

function StatusBadge({ status, map }: { status: string; map: typeof RUN_STATUS }) {
  const s = map[status] ?? { label: status, cls: "text-gray-400 bg-gray-800" }
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium flex-shrink-0 ${s.cls}`}>
      {s.label}
    </span>
  )
}

function ExecIcon({ status }: { status: string }) {
  if (status === "running") return <Loader size={12} className="text-blue-400 animate-spin" />
  if (status === "succeeded") return <CheckCircle size={12} className="text-emerald-400" />
  if (status === "failed" || status === "rejected") return <XCircle size={12} className="text-red-400" />
  if (status === "waiting_approval") return <AlertTriangle size={12} className="text-yellow-400" />
  return <Clock size={12} className="text-gray-600" />
}

// ── New Run Modal ──────────────────────────────────────────────────────────────

interface NewRunModalProps {
  onClose: () => void
  onCreated: (run: AgentRun) => void
}

function NewRunModal({ onClose, onCreated }: NewRunModalProps) {
  const [summary, setSummary] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    setSubmitting(true); setError(null)
    try {
      const run = await createRun({ summary: summary.trim() || undefined })
      onCreated(run)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-sm mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Activity size={13} className="text-blue-400" />
            <span className="text-xs font-semibold text-white">New Run</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-gray-600 hover:text-white hover:bg-gray-800 transition-colors">
            <X size={14} />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Summary (optional)</label>
            <input
              value={summary}
              onChange={e => setSummary(e.target.value)}
              placeholder="e.g. File organization task"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </div>
          {error && (
            <p className="text-[10px] text-red-400 bg-red-950/30 px-2.5 py-1.5 rounded-lg border border-red-900/40">{error}</p>
          )}
        </div>
        <div className="flex justify-end gap-2 px-4 pb-4">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-white hover:bg-gray-800 transition-colors">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors disabled:opacity-50"
          >
            {submitting ? <RefreshCw size={11} className="animate-spin" /> : <Plus size={11} />}
            Create
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Approval card ──────────────────────────────────────────────────────────────

interface ApprovalCardProps {
  approval: RunApproval
  exec: RunExecution
  run: AgentRun
  onDecided: () => void
}

function ApprovalCard({ approval, exec, run, onDecided }: ApprovalCardProps) {
  const [loading, setLoading] = useState(false)

  const handle = async (action: "approve" | "reject") => {
    setLoading(true)
    try {
      if (action === "approve") await approveExecution(run.id, approval.id)
      else await rejectExecution(run.id, approval.id)
      onDecided()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-2xl border border-yellow-800/40 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <AlertTriangle size={13} className="text-yellow-400" />
          <span className="text-xs font-semibold text-white truncate max-w-[120px]">{exec.kind}</span>
        </div>
        <span className={`text-[10px] font-medium ${RISK_CLS[exec.risk_level] ?? "text-gray-400"}`}>
          {exec.risk_level.toUpperCase()}
        </span>
      </div>
      <div className="px-3 py-2.5 space-y-2">
        {approval.reason && (
          <p className="text-[11px] text-gray-300 bg-orange-900/20 rounded-lg px-2 py-1.5 border border-orange-800/30">
            {approval.reason}
          </p>
        )}
        {Object.keys(exec.payload).length > 0 && (
          <pre className="text-[10px] text-gray-500 font-mono bg-gray-950 rounded-lg p-2 overflow-x-auto max-h-16">
            {JSON.stringify(exec.payload, null, 2)}
          </pre>
        )}
        <div className="flex gap-2 pt-0.5">
          <button
            onClick={() => handle("approve")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-[11px] font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldCheck size={12} /> Approve
          </button>
          <button
            onClick={() => handle("reject")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-red-600/70 hover:bg-red-600 text-white rounded-xl text-[11px] font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldX size={12} /> Reject
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main: RunCenterView ────────────────────────────────────────────────────────

type RunFilter = "all" | "active" | "done"

export default function RunCenterView() {
  const [runs, setRuns] = useState<AgentRun[]>([])
  const [devices, setDevices] = useState<NativeDevice[]>([])
  const [selectedRun, setSelectedRun] = useState<AgentRun | null>(null)
  const [filter, setFilter] = useState<RunFilter>("all")
  const [loading, setLoading] = useState(false)
  const [showNewRun, setShowNewRun] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listRuns({ limit: 50 })
      setRuns(data)
      // Keep selected run in sync
      if (selectedRun) {
        const updated = data.find(r => r.id === selectedRun.id)
        if (updated) setSelectedRun(updated)
      }
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    listDevices().then(setDevices).catch(() => { })
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [])

  const filtered = runs.filter(r => {
    if (filter === "active") return ["queued", "running", "waiting_approval"].includes(r.status)
    if (filter === "done") return ["completed", "failed", "canceled"].includes(r.status)
    return true
  })

  // Pending approvals for selected run (right pane)
  const pendingApprovals: Array<{ approval: RunApproval; exec: RunExecution }> = []
  if (selectedRun) {
    for (const exec of selectedRun.executions) {
      for (const a of exec.approvals) {
        if (a.status === "pending") {
          pendingApprovals.push({ approval: a, exec })
        }
      }
    }
  }

  // All pending approvals across all runs (for the right pane when no run is selected)
  const allPendingApprovals: Array<{ approval: RunApproval; exec: RunExecution; run: AgentRun }> = []
  for (const run of runs) {
    for (const exec of run.executions) {
      for (const a of exec.approvals) {
        if (a.status === "pending") {
          allPendingApprovals.push({ approval: a, exec, run })
        }
      }
    }
  }

  const deviceName = (id?: string) => {
    if (!id) return null
    const d = devices.find(x => x.id === id)
    return d ? d.display_name : `${id.slice(0, 8)}…`
  }

  const approvalSource = selectedRun
    ? pendingApprovals.map(({ approval, exec }) => ({ approval, exec, run: selectedRun }))
    : allPendingApprovals

  return (
    <div className="flex h-full">
      {/* ── Left: Run list ─────────────────────────────────────────────────── */}
      <div className="flex flex-col w-64 min-w-64 border-r border-gray-800">
        {/* Toolbar */}
        <div className="flex items-center gap-1.5 px-3 py-2.5 border-b border-gray-800">
          <span className="text-sm font-semibold text-white flex-1">Run Center</span>
          <div className="flex gap-1">
            {(["all", "active", "done"] as RunFilter[]).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2 py-0.5 rounded-md text-[10px] font-medium transition-colors capitalize ${filter === f ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-300"
                  }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowNewRun(true)}
            className="p-1.5 rounded-lg hover:bg-blue-600/20 text-blue-500 hover:text-blue-400 transition-colors"
            title="New Run"
          >
            <Plus size={13} />
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* Run list */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-xs text-gray-600 text-center py-8">No runs</p>
          ) : (
            filtered.map(run => {
              const s = RUN_STATUS[run.status] ?? RUN_STATUS.queued
              const isSelected = selectedRun?.id === run.id
              const pendingCount = run.executions.reduce(
                (n, e) => n + e.approvals.filter(a => a.status === "pending").length,
                0
              )
              return (
                <button
                  key={run.id}
                  onClick={() => setSelectedRun(run)}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 border-b border-gray-800/50 text-left transition-colors ${isSelected ? "bg-blue-600/10" : "hover:bg-gray-900"
                    }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-gray-200 truncate">
                      {run.summary || `Run ${run.id.slice(0, 8)}`}
                    </p>
                    <p className="text-[10px] text-gray-600 mt-0.5">
                      {new Date(run.created_at).toLocaleString(undefined, {
                        month: "numeric", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                  </div>
                  {pendingCount > 0 && (
                    <span className="w-4 h-4 rounded-full bg-yellow-500 text-[9px] text-black font-bold flex items-center justify-center flex-shrink-0">
                      {pendingCount}
                    </span>
                  )}
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium flex-shrink-0 ${s.cls}`}>
                    {s.label}
                  </span>
                  <ChevronRight size={11} className="text-gray-700 flex-shrink-0" />
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* ── Center: Execution timeline ─────────────────────────────────────── */}
      <div className="flex-1 flex flex-col border-r border-gray-800 min-w-0">
        {!selectedRun ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-700 gap-2">
            <Activity size={32} className="text-gray-800" />
            <p className="text-sm">← Select a run</p>
          </div>
        ) : (
          <>
            {/* Run header */}
            <div className="px-4 py-3 border-b border-gray-800 flex-shrink-0">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    {selectedRun.summary || `Run ${selectedRun.id.slice(0, 8)}`}
                  </h2>
                  <p className="text-[10px] font-mono text-gray-600 mt-0.5">{selectedRun.id}</p>
                </div>
                <StatusBadge status={selectedRun.status} map={RUN_STATUS} />
                {["queued", "running", "waiting_approval"].includes(selectedRun.status) && (
                  <button
                    onClick={async () => {
                      try {
                        await cancelRun(selectedRun.id)
                        load()
                      } catch { /* ignore */ }
                    }}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-red-600/20 text-red-400 hover:bg-red-600/40 transition-colors"
                    title="Stop Run"
                  >
                    <Square size={10} />
                    Stop
                  </button>
                )}
              </div>
              {(selectedRun.project_id || selectedRun.session_id) && (
                <div className="flex gap-3 mt-1.5 text-[10px] text-gray-600">
                  {selectedRun.project_id && <span>project: {selectedRun.project_id.slice(0, 8)}</span>}
                  {selectedRun.session_id && <span>session: {selectedRun.session_id.slice(0, 8)}</span>}
                </div>
              )}
            </div>

            {/* Execution timeline */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {selectedRun.executions.length === 0 ? (
                <p className="text-xs text-gray-600 text-center py-8">No executions</p>
              ) : (
                selectedRun.executions.map((exec, idx) => {
                  const hasPending = exec.approvals.some(a => a.status === "pending")
                  return (
                    <div
                      key={exec.id}
                      className={`rounded-xl border p-3 ${hasPending
                        ? "border-yellow-800/50 bg-yellow-900/5"
                        : exec.status === "succeeded"
                          ? "border-emerald-800/30 bg-emerald-900/5"
                          : exec.status === "failed" || exec.status === "rejected"
                            ? "border-red-800/30 bg-red-900/5"
                            : exec.status === "running"
                              ? "border-blue-700/30 bg-blue-900/5"
                              : "border-gray-800 bg-gray-900/30"
                        }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-600 w-5 text-right flex-shrink-0">{idx + 1}</span>
                        <ExecIcon status={hasPending ? "waiting_approval" : exec.status} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[11px] font-mono text-blue-300 truncate">{exec.kind}</span>
                            <span className={`text-[10px] ${RISK_CLS[exec.risk_level] ?? "text-gray-500"}`}>
                              {exec.risk_level}
                            </span>
                            <StatusBadge status={hasPending ? "waiting_approval" : exec.status} map={EXEC_STATUS} />
                          </div>
                          {exec.target_device_id && (
                            <span className="flex items-center gap-1 text-[10px] text-purple-400 mt-0.5">
                              <Monitor size={9} />{deviceName(exec.target_device_id)}
                            </span>
                          )}
                          {exec.error_log && (
                            <p className="text-[10px] text-red-400 mt-1 font-mono truncate">{exec.error_log}</p>
                          )}
                        </div>
                      </div>
                      {/* Approval decisions history */}
                      {exec.approvals.filter(a => a.status !== "pending").map(a => (
                        <div key={a.id} className="mt-1.5 ml-7 flex items-center gap-2 text-[10px] text-gray-600">
                          {a.status === "approved"
                            ? <CheckCircle size={10} className="text-emerald-500" />
                            : <XCircle size={10} className="text-red-500" />
                          }
                          <span>{a.status === "approved" ? "Approved" : "Rejected"}</span>
                          {a.decided_at && (
                            <span>{new Date(a.decided_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>
                          )}
                        </div>
                      ))}
                      {/* Retry button for failed/rejected */}
                      {(exec.status === "failed" || exec.status === "rejected") && (
                        <button
                          onClick={async () => {
                            try {
                              await retryExecution(selectedRun.id, exec.id)
                              load()
                            } catch { /* ignore */ }
                          }}
                          className="ml-7 mt-1.5 flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium bg-blue-600/20 text-blue-400 hover:bg-blue-600/40 transition-colors"
                          title="Retry this execution"
                        >
                          <RotateCcw size={10} />
                          Retry
                        </button>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Right: Approval queue ─────────────────────────────────────────── */}
      <div className="flex flex-col w-64 min-w-64">
        <div className="px-3 py-2.5 border-b border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-2">
            <ShieldCheck size={13} className="text-yellow-400" />
            <span className="text-sm font-semibold text-white">Approval Queue</span>
            {approvalSource.length > 0 && (
              <span className="ml-auto text-[10px] font-bold text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded-full">
                {approvalSource.length}
              </span>
            )}
          </div>
          {!selectedRun && (
            <p className="text-[10px] text-gray-600 mt-0.5">All runs pending approval</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {approvalSource.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <CheckCircle size={28} className="text-emerald-700 mb-2" />
              <p className="text-xs text-gray-500">No pending approvals</p>
            </div>
          ) : (
            approvalSource.map(({ approval, exec, run }) => (
              <ApprovalCard
                key={approval.id}
                approval={approval}
                exec={exec}
                run={run}
                onDecided={load}
              />
            ))
          )}
        </div>
      </div>

      {/* New Run modal */}
      {showNewRun && (
        <NewRunModal
          onClose={() => setShowNewRun(false)}
          onCreated={run => {
            setRuns(prev => [run, ...prev])
            setSelectedRun(run)
          }}
        />
      )}
    </div>
  )
}
