import React, { useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Play, Pause, Terminal, Bell } from "lucide-react"
import type { Job } from "../../../shared/types"
import { listJobs } from "../../../bridge/api"

interface Props {
  onApprovalNeeded: (jobId: string) => void
  onOpenConsole: () => void
}

export default function ResidentPanel({ onApprovalNeeded, onOpenConsole }: Props) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [paused, setPaused] = useState(false)
  // Track jobs we've already sent OS notifications for to avoid repeats
  const notifiedRef = useRef(new Set<string>())

  useEffect(() => {
    const load = async () => {
      if (paused) return
      try {
        // Fetch all recent native jobs (running + needs_approval + others)
        const data = await listJobs({ source: "native", limit: 10 })
        setJobs(data)

        const approval = data.find((j) => j.status === "needs_approval")
        if (approval) {
          // Trigger approval view
          onApprovalNeeded(approval.id)

          // Send OS notification once per job
          if (!notifiedRef.current.has(approval.id)) {
            notifiedRef.current.add(approval.id)
            invoke("send_notification", {
              title: "VisionArk — 承認が必要です",
              body: `ジョブ「${approval.type}」のステップを確認してください`,
            }).catch(() => {
              // Notification plugin may not be available in dev without permissions
            })
          }
        }
      } catch {
        // ignore — daemon may not be authenticated yet
      }
    }
    load()
    // Poll every 5s (approvals need prompt attention)
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [paused, onApprovalNeeded])

  const activeJobs = jobs.filter((j) =>
    ["queued", "running", "needs_approval"].includes(j.status)
  )

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-white">VisionArk</span>
        <div className="flex gap-2">
          <button
            onClick={() => setPaused((p) => !p)}
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            title={paused ? "Resume" : "Pause"}
          >
            {paused ? <Play size={14} /> : <Pause size={14} />}
          </button>
          <button
            onClick={onOpenConsole}
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
            title="Console"
          >
            <Terminal size={14} />
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {activeJobs.length === 0 ? (
          <p className="text-xs text-gray-600 text-center py-4">No active jobs</p>
        ) : (
          activeJobs.map((job) => (
            <div
              key={job.id}
              className="flex items-center gap-2 px-3 py-2 bg-gray-900 rounded-xl border border-gray-800"
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  job.status === "needs_approval"
                    ? "bg-yellow-500"
                    : "bg-blue-500 animate-pulse"
                }`}
              />
              <span className="text-xs text-gray-300 truncate flex-1">{job.type}</span>
              <span className="text-xs text-gray-600">{job.status}</span>
            </div>
          ))
        )}
      </div>

      {activeJobs.some((j) => j.status === "needs_approval") && (
        <div className="flex items-center gap-2 px-3 py-2 bg-yellow-500/10 rounded-xl border border-yellow-500/30">
          <Bell size={14} className="text-yellow-400 flex-shrink-0" />
          <span className="text-xs text-yellow-300">承認が必要です</span>
        </div>
      )}
    </div>
  )
}
