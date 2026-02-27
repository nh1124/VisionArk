import React, { useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Activity, Bell, Pause, Play } from "lucide-react"
import type { Job } from "../../../shared/types"
import { listJobs } from "../../../bridge/api"

const STATUS_COLORS: Record<string, string> = {
  queued:          "bg-gray-500",
  running:         "bg-blue-500 animate-pulse",
  needs_approval:  "bg-yellow-500",
  succeeded:       "bg-emerald-500",
  failed:          "bg-red-500",
  rejected:        "bg-red-400",
}

interface Props {
  onApprovalNeeded: (jobId: string) => void
  onJobsUpdated: (jobs: Job[]) => void
}

export default function StatusPanel({ onApprovalNeeded, onJobsUpdated }: Props) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [paused, setPaused] = useState(false)
  const notifiedRef = useRef(new Set<string>())

  useEffect(() => {
    const load = async () => {
      if (paused) return
      try {
        const data = await listJobs({ source: "native", limit: 15 })
        setJobs(data)
        onJobsUpdated(data)

        const approval = data.find((j) => j.status === "needs_approval")
        if (approval) {
          onApprovalNeeded(approval.id)
          if (!notifiedRef.current.has(approval.id)) {
            notifiedRef.current.add(approval.id)
            invoke("send_notification", {
              title: "VisionArk — 承認が必要です",
              body: `ジョブ「${approval.type}」のステップを確認してください`,
            }).catch(() => {})
          }
        }
      } catch {
        // daemon not yet authenticated
      }
    }

    load()
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [paused, onApprovalNeeded, onJobsUpdated])

  const active = jobs.filter((j) =>
    ["queued", "running", "needs_approval"].includes(j.status)
  )
  const needsApproval = jobs.filter((j) => j.status === "needs_approval")

  return (
    <aside className="flex flex-col w-52 min-w-52 border-l border-gray-800 bg-gray-950/60">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-3 border-b border-gray-800">
        <div className="flex items-center gap-1.5">
          <Activity size={13} className="text-gray-400" />
          <span className="text-xs font-semibold text-gray-300">Activity</span>
        </div>
        <button
          onClick={() => setPaused((p) => !p)}
          title={paused ? "Resume polling" : "Pause polling"}
          className="p-1 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
        >
          {paused ? <Play size={12} /> : <Pause size={12} />}
        </button>
      </div>

      {/* Approval alert */}
      {needsApproval.length > 0 && (
        <button
          onClick={() => onApprovalNeeded(needsApproval[0].id)}
          className="mx-2 mt-2 flex items-center gap-2 px-2.5 py-2 bg-yellow-500/10 hover:bg-yellow-500/20 rounded-xl border border-yellow-500/30 transition-colors text-left"
        >
          <Bell size={12} className="text-yellow-400 flex-shrink-0" />
          <span className="text-xs text-yellow-300 leading-tight">
            {needsApproval.length} 件の承認待ち
          </span>
        </button>
      )}

      {/* Stats row */}
      <div className="flex gap-2 px-2 py-2">
        {[
          { label: "Running", count: jobs.filter((j) => j.status === "running").length, color: "text-blue-400" },
          { label: "Queued",  count: jobs.filter((j) => j.status === "queued").length,  color: "text-gray-400" },
          { label: "Done",    count: jobs.filter((j) => j.status === "succeeded").length, color: "text-emerald-400" },
        ].map(({ label, count, color }) => (
          <div key={label} className="flex-1 flex flex-col items-center py-1.5 bg-gray-900 rounded-lg">
            <span className={`text-sm font-semibold ${color}`}>{count}</span>
            <span className="text-[10px] text-gray-600 mt-0.5">{label}</span>
          </div>
        ))}
      </div>

      {/* Active jobs list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-2">
        {active.length === 0 ? (
          <p className="text-[11px] text-gray-700 text-center py-4">No active jobs</p>
        ) : (
          active.map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-900/60 border border-gray-800"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${STATUS_COLORS[job.status] ?? "bg-gray-500"}`}
              />
              <span className="text-[11px] text-gray-300 truncate flex-1">{job.type}</span>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}
