import React, { useEffect, useState } from "react"
import {
  RefreshCw, ChevronRight, CheckCircle, XCircle, Clock,
  AlertTriangle, Loader, RotateCcw, Plus, Monitor, X,
} from "lucide-react"
import type { Job, NativeDevice } from "../../../shared/types"
import { listJobs, createJob, retryJob, listDevices } from "../../../bridge/api"

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  queued:          { label: "Queued",          className: "text-gray-400 bg-gray-800" },
  running:         { label: "Running",         className: "text-blue-400 bg-blue-400/10" },
  needs_approval:  { label: "Needs Approval",  className: "text-yellow-400 bg-yellow-400/10" },
  succeeded:       { label: "Succeeded",       className: "text-emerald-400 bg-emerald-400/10" },
  failed:          { label: "Failed",          className: "text-red-400 bg-red-400/10" },
  rejected:        { label: "Rejected",        className: "text-red-300 bg-red-300/10" },
}

const RISK_STYLES: Record<string, string> = {
  low:      "text-emerald-400",
  medium:   "text-yellow-400",
  high:     "text-orange-400",
  critical: "text-red-400",
}

type Filter = "all" | "active" | "done"

function StepIcon({ ok, isActive }: { ok?: boolean; isActive?: boolean }) {
  if (isActive) return <Loader size={13} className="text-blue-400 animate-spin" />
  if (ok === true)  return <CheckCircle size={13} className="text-emerald-400" />
  if (ok === false) return <XCircle size={13} className="text-red-400" />
  return <Clock size={13} className="text-gray-600" />
}

// ── New Job Modal ──────────────────────────────────────────────────────────────

interface NewJobModalProps {
  devices: NativeDevice[]
  onClose: () => void
  onCreated: (job: Job) => void
}

function NewJobModal({ devices, onClose, onCreated }: NewJobModalProps) {
  const [jobType, setJobType] = useState("")
  const [payload, setPayload] = useState("{}")
  const [riskLevel, setRiskLevel] = useState("low")
  const [targetDeviceId, setTargetDeviceId] = useState<string>("auto")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enabledDevices = devices.filter(d => d.is_enabled)

  const handleSubmit = async () => {
    if (!jobType.trim()) { setError("Job type is required"); return }
    let parsedPayload: Record<string, unknown> = {}
    try { parsedPayload = JSON.parse(payload) } catch {
      setError("Payload must be valid JSON"); return
    }
    setSubmitting(true)
    setError(null)
    try {
      const created = await createJob({
        type: jobType.trim(),
        payload: parsedPayload,
        risk_level: riskLevel,
        routing_mode: targetDeviceId === "auto" ? "auto" : "manual",
        target_device_id: targetDeviceId !== "auto" ? targetDeviceId : undefined,
      })
      onCreated(created)
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
            <Plus size={13} className="text-blue-400" />
            <span className="text-xs font-semibold text-white">New Job</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-gray-600 hover:text-white hover:bg-gray-800 transition-colors">
            <X size={14} />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Job type */}
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Job Type *</label>
            <input
              value={jobType}
              onChange={e => setJobType(e.target.value)}
              placeholder="e.g. local.dev, file.sync"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Payload */}
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Payload (JSON)</label>
            <textarea
              value={payload}
              onChange={e => setPayload(e.target.value)}
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white font-mono placeholder-gray-600 focus:outline-none focus:border-blue-500 resize-none"
            />
          </div>

          {/* Risk level */}
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Risk Level</label>
            <div className="flex gap-1.5">
              {(["low", "medium", "high", "critical"] as const).map(level => (
                <button
                  key={level}
                  onClick={() => setRiskLevel(level)}
                  className={`flex-1 py-1 rounded-lg text-[10px] font-medium transition-colors ${
                    riskLevel === level
                      ? level === "low" ? "bg-green-600/30 text-green-300"
                        : level === "medium" ? "bg-yellow-600/30 text-yellow-300"
                        : level === "high" ? "bg-orange-600/30 text-orange-300"
                        : "bg-red-600/30 text-red-300"
                      : "bg-gray-800 text-gray-600 hover:bg-gray-700"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Target device */}
          <div>
            <label className="block text-[10px] text-gray-500 mb-1">Target Device</label>
            <select
              value={targetDeviceId}
              onChange={e => setTargetDeviceId(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
            >
              <option value="auto">Auto-route</option>
              {enabledDevices.map(d => (
                <option key={d.id} value={d.id}>
                  {d.display_name} [{d.platform}] — {d.status}
                </option>
              ))}
            </select>
            {enabledDevices.length === 0 && (
              <p className="text-[10px] text-yellow-600 mt-1">
                No enabled devices — go to Devices to enable one.
              </p>
            )}
          </div>

          {error && (
            <p className="text-[10px] text-red-400 bg-red-950/30 px-2.5 py-1.5 rounded-lg border border-red-900/40">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 px-4 pb-4">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
          >
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

// ── Main component ─────────────────────────────────────────────────────────────

export default function JobsView() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [devices, setDevices] = useState<NativeDevice[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [filter, setFilter] = useState<Filter>("all")
  const [loading, setLoading] = useState(false)
  const [showNewJob, setShowNewJob] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listJobs({ source: "native", limit: 50 })
      setJobs(data)
      if (selected) {
        const updated = data.find(j => j.id === selected.id)
        if (updated) setSelected(updated)
      }
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    listDevices().then(setDevices).catch(() => {})
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [])

  const filtered = jobs.filter(j => {
    if (filter === "active") return ["queued", "running", "needs_approval"].includes(j.status)
    if (filter === "done")   return ["succeeded", "failed", "rejected"].includes(j.status)
    return true
  })

  // Plan step results map
  const stepResults: Record<string, { ok: boolean; data: unknown }> = {}
  if (selected?.result?.step_results) {
    for (const sr of selected.result.step_results as Array<{ step_id: string; ok: boolean; data: unknown }>) {
      stepResults[sr.step_id] = { ok: sr.ok, data: sr.data }
    }
  }
  const planSteps = (selected?.result?.plan as { steps?: Array<{ id: string; tool: string; description: string; risk_level: string }> } | undefined)?.steps ?? []
  const currentStep = selected?.result?.current_step as string | null | undefined

  const deviceName = (id?: string) => {
    if (!id) return null
    const d = devices.find(x => x.id === id)
    return d ? d.display_name : `${id.slice(0, 8)}…`
  }

  return (
    <div className="flex h-full">
      {/* Left: jobs list */}
      <div className="flex flex-col w-72 min-w-72 border-r border-gray-800">
        {/* Toolbar */}
        <div className="flex items-center gap-1.5 px-3 py-2.5 border-b border-gray-800">
          <span className="text-sm font-semibold text-white flex-1">Jobs</span>
          <div className="flex gap-1">
            {(["all", "active", "done"] as Filter[]).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-2 py-0.5 rounded-md text-[11px] font-medium transition-colors capitalize ${
                  filter === f
                    ? "bg-blue-600 text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={() => setShowNewJob(true)}
            className="p-1.5 rounded-lg hover:bg-blue-600/20 text-blue-500 hover:text-blue-400 transition-colors"
            title="New Job"
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

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-xs text-gray-600 text-center py-8">No jobs</p>
          ) : (
            filtered.map(job => {
              const s = STATUS_STYLES[job.status] ?? STATUS_STYLES.queued
              const isSelected = selected?.id === job.id
              return (
                <button
                  key={job.id}
                  onClick={() => setSelected(job)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 border-b border-gray-800/50 text-left transition-colors ${
                    isSelected ? "bg-blue-600/10" : "hover:bg-gray-900"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <p className="text-xs font-medium text-gray-200 truncate">{job.type}</p>
                      {job.target_device_id && (
                        <span className="flex items-center gap-0.5 text-[9px] text-purple-400">
                          <Monitor size={9} />
                          {deviceName(job.target_device_id)}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-gray-600 mt-0.5">
                      {new Date(job.created_at).toLocaleString("ja-JP", {
                        month: "numeric", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </p>
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium flex-shrink-0 ${s.className}`}>
                    {s.label}
                  </span>
                  <ChevronRight size={12} className="text-gray-700 flex-shrink-0" />
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* Right: detail pane */}
      <div className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-gray-700 text-sm">
            ← ジョブを選択してください
          </div>
        ) : (
          <div className="p-4 space-y-4">
            {/* Job header */}
            <div>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-white">{selected.type}</h2>
                  <p className="text-xs text-gray-500 mt-0.5 font-mono">{selected.id.slice(0, 8)}…</p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className={`text-[11px] font-medium ${RISK_STYLES[selected.risk_level] ?? "text-gray-400"}`}>
                    {selected.risk_level.toUpperCase()}
                  </span>
                  <span className={`text-[11px] px-2 py-0.5 rounded-md font-medium ${STATUS_STYLES[selected.status]?.className ?? ""}`}>
                    {STATUS_STYLES[selected.status]?.label ?? selected.status}
                  </span>
                </div>
              </div>

              {/* Device routing info */}
              {(selected.target_device_id || selected.claimed_by_device_id || selected.routing_mode === "auto") && (
                <div className="flex items-center gap-3 mt-2 text-[10px] text-gray-500">
                  {selected.target_device_id ? (
                    <span className="flex items-center gap-1">
                      <Monitor size={10} className="text-purple-400" />
                      <span className="text-gray-600">Target:</span>
                      <span className="text-purple-300">{deviceName(selected.target_device_id)}</span>
                    </span>
                  ) : (
                    <span className="flex items-center gap-1">
                      <Monitor size={10} className="text-gray-600" />
                      <span className="text-gray-600">auto-route</span>
                    </span>
                  )}
                  {selected.claimed_by_device_id && (
                    <span className="flex items-center gap-1">
                      <Monitor size={10} className="text-green-400" />
                      <span className="text-gray-600">Claimed:</span>
                      <span className="text-green-300">{deviceName(selected.claimed_by_device_id)}</span>
                    </span>
                  )}
                </div>
              )}

              {/* Tags */}
              {selected.tags.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {selected.tags.map(t => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-md bg-gray-800 text-gray-400">{t}</span>
                  ))}
                </div>
              )}
            </div>

            {/* Payload */}
            {Object.keys(selected.payload).length > 0 && (
              <section>
                <p className="text-[11px] text-gray-500 mb-1.5 font-medium uppercase tracking-wider">Payload</p>
                <pre className="text-xs text-gray-300 bg-gray-900 rounded-xl p-3 border border-gray-800 overflow-x-auto">
                  {JSON.stringify(selected.payload, null, 2)}
                </pre>
              </section>
            )}

            {/* Plan steps */}
            {planSteps.length > 0 && (
              <section>
                <p className="text-[11px] text-gray-500 mb-2 font-medium uppercase tracking-wider">
                  Execution Plan ({planSteps.length} steps)
                </p>
                <div className="space-y-1.5">
                  {planSteps.map((step, idx) => {
                    const result = stepResults[step.id]
                    const isActive = step.id === currentStep
                    return (
                      <div
                        key={step.id}
                        className={`flex items-start gap-2.5 p-2.5 rounded-xl border ${
                          isActive
                            ? "border-blue-600/40 bg-blue-600/5"
                            : result
                            ? result.ok
                              ? "border-emerald-800/40 bg-emerald-900/10"
                              : "border-red-800/40 bg-red-900/10"
                            : "border-gray-800 bg-gray-900/40"
                        }`}
                      >
                        <span className="text-[10px] text-gray-600 w-5 pt-0.5 flex-shrink-0 text-right">
                          {idx + 1}
                        </span>
                        <StepIcon ok={result?.ok} isActive={isActive} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-mono text-blue-300">{step.tool}</span>
                            <span className={`text-[10px] ${RISK_STYLES[step.risk_level] ?? "text-gray-500"}`}>
                              {step.risk_level}
                            </span>
                          </div>
                          <p className="text-[11px] text-gray-400 mt-0.5">{step.description}</p>
                          {result && !result.ok && (
                            <p className="text-[11px] text-red-400 mt-1 font-mono">
                              {String((result.data as { error?: string })?.error ?? "")}
                            </p>
                          )}
                        </div>
                        {(step.risk_level === "high" || step.risk_level === "critical") && (
                          <AlertTriangle size={12} className="text-orange-400 flex-shrink-0 mt-0.5" />
                        )}
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {/* Retry */}
            {(selected.status === "failed" || selected.status === "rejected") && (
              <div className="flex">
                <button
                  onClick={async () => {
                    try {
                      const updated = await retryJob(selected.id)
                      setSelected(updated)
                      load()
                    } catch {
                      // ignore
                    }
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl text-xs font-medium transition-colors"
                >
                  <RotateCcw size={12} />
                  再実行
                </button>
              </div>
            )}

            {/* Error log */}
            {selected.error_log && (
              <section>
                <p className="text-[11px] text-gray-500 mb-1.5 font-medium uppercase tracking-wider">Error</p>
                <pre className="text-xs text-red-400 bg-red-900/10 rounded-xl p-3 border border-red-800/30 overflow-x-auto whitespace-pre-wrap">
                  {selected.error_log}
                </pre>
              </section>
            )}
          </div>
        )}
      </div>

      {/* New Job modal */}
      {showNewJob && (
        <NewJobModal
          devices={devices}
          onClose={() => setShowNewJob(false)}
          onCreated={job => {
            setJobs(prev => [job, ...prev])
            setSelected(job)
          }}
        />
      )}
    </div>
  )
}
