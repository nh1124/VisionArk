import React, { useEffect, useState } from "react"
import { ShieldCheck, ShieldX, AlertTriangle, RefreshCw, CheckCircle } from "lucide-react"
import type { Job } from "../../../shared/types"
import { listJobs, approveJob, rejectJob } from "../../../bridge/api"

const RISK_STYLES: Record<string, string> = {
  low:      "text-emerald-400",
  medium:   "text-yellow-400",
  high:     "text-orange-400",
  critical: "text-red-400",
}

interface JobRowProps {
  job: Job
  onRefresh: () => void
}

function JobRow({ job, onRefresh }: JobRowProps) {
  const [loading, setLoading] = useState(false)

  const handle = async (action: "approve" | "reject") => {
    setLoading(true)
    try {
      if (action === "approve") await approveJob(job.id)
      else await rejectJob(job.id)
      onRefresh()
    } finally {
      setLoading(false)
    }
  }

  // Pending step from plan
  const plan = job.result?.plan as { steps?: Array<{ id: string; tool: string; description: string; risk_level: string }> } | undefined
  const stepResults = (job.result?.step_results as Array<{ step_id: string }> | undefined) ?? []
  const completedIds = new Set(stepResults.map((r) => r.step_id))
  const pendingStep = plan?.steps?.find((s) => !completedIds.has(s.id))

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-yellow-400" />
          <span className="text-sm font-semibold text-white">{job.type}</span>
        </div>
        <span className={`text-xs font-medium ${RISK_STYLES[job.risk_level] ?? "text-gray-400"}`}>
          {job.risk_level.toUpperCase()}
        </span>
      </div>

      <div className="px-4 py-3 space-y-3">
        {/* Pending step */}
        {pendingStep && (
          <div className="bg-orange-900/20 rounded-xl p-3 border border-orange-800/30">
            <p className="text-[11px] text-gray-500 mb-1 uppercase tracking-wider font-medium">承認待ちステップ</p>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-blue-300">{pendingStep.tool}</span>
              <span className={`text-[11px] ${RISK_STYLES[pendingStep.risk_level]}`}>{pendingStep.risk_level}</span>
            </div>
            <p className="text-xs text-gray-300 mt-1">{pendingStep.description}</p>
          </div>
        )}

        {/* Payload preview */}
        {Object.keys(job.payload).length > 0 && (
          <div>
            <p className="text-[11px] text-gray-600 mb-1 uppercase tracking-wider font-medium">Payload</p>
            <pre className="text-[11px] text-gray-400 font-mono bg-gray-950 rounded-lg p-2 overflow-x-auto max-h-24">
              {JSON.stringify(job.payload, null, 2)}
            </pre>
          </div>
        )}

        {/* Approve / Reject */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => handle("approve")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldCheck size={13} />
            承認
          </button>
          <button
            onClick={() => handle("reject")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-red-600/70 hover:bg-red-600 text-white rounded-xl text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldX size={13} />
            拒否
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ApprovalsView({ highlightJobId }: { highlightJobId?: string | null }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listJobs({ source: "native", limit: 50 })
      setJobs(data)
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

  const pending = jobs.filter((j) => j.status === "needs_approval")
  // Highlight job first if provided
  const sorted = highlightJobId
    ? [...pending].sort((a) => (a.id === highlightJobId ? -1 : 1))
    : pending

  const recent = jobs
    .filter((j) => ["succeeded", "rejected", "failed"].includes(j.status) && j.approved_by)
    .slice(0, 5)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
        <div>
          <h1 className="text-sm font-semibold text-white">承認センター</h1>
          <p className="text-[11px] text-gray-500 mt-0.5">
            {pending.length > 0 ? `${pending.length} 件の承認待ち` : "承認待ちなし"}
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {/* Pending approvals */}
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <CheckCircle size={32} className="text-emerald-600 mb-3" />
            <p className="text-sm text-gray-400 font-medium">承認待ちのジョブはありません</p>
            <p className="text-xs text-gray-600 mt-1">高リスクのステップが実行されると、ここに表示されます</p>
          </div>
        ) : (
          sorted.map((job) => (
            <JobRow key={job.id} job={job} onRefresh={load} />
          ))
        )}

        {/* Recent */}
        {recent.length > 0 && (
          <div className="pt-2">
            <p className="text-[11px] text-gray-600 uppercase tracking-wider font-medium mb-2 px-1">
              承認済み履歴
            </p>
            <div className="space-y-1">
              {recent.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center gap-2 px-3 py-2 bg-gray-900/40 rounded-xl"
                >
                  <CheckCircle size={12} className="text-emerald-500 flex-shrink-0" />
                  <span className="text-xs text-gray-400 truncate flex-1">{job.type}</span>
                  <span className="text-[10px] text-gray-600">
                    {job.approved_by?.slice(0, 6)}…
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
