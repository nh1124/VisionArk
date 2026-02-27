import React, { useEffect, useState } from "react"
import { RefreshCw, ChevronRight, CheckCircle, XCircle, Clock, AlertTriangle, Loader } from "lucide-react"
import type { Job } from "../../../shared/types"
import { listJobs } from "../../../bridge/api"

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

export default function JobsView() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [filter, setFilter] = useState<Filter>("all")
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listJobs({ source: "native", limit: 50 })
      setJobs(data)
      // Keep selected job in sync
      if (selected) {
        const updated = data.find((j) => j.id === selected.id)
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
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [])

  const filtered = jobs.filter((j) => {
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

  return (
    <div className="flex h-full">
      {/* Left: jobs list */}
      <div className="flex flex-col w-72 min-w-72 border-r border-gray-800">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-gray-800">
          <span className="text-sm font-semibold text-white flex-1">Jobs</span>
          <div className="flex gap-1">
            {(["all", "active", "done"] as Filter[]).map((f) => (
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
            filtered.map((job) => {
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
                    <p className="text-xs font-medium text-gray-200 truncate">{job.type}</p>
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

              {/* Tags */}
              {selected.tags.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {selected.tags.map((t) => (
                    <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-md bg-gray-800 text-gray-400">
                      {t}
                    </span>
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
                        {step.risk_level === "high" || step.risk_level === "critical" ? (
                          <AlertTriangle size={12} className="text-orange-400 flex-shrink-0 mt-0.5" />
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </section>
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
    </div>
  )
}
