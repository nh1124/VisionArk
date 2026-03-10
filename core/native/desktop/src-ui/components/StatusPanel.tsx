import React, { useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Activity, Bell, Pause, Play } from "lucide-react"
import type { NativeRun, RunExecution } from "../../../shared/types"
import { listRuns } from "../../../bridge/api"

const EXEC_STATUS_COLORS: Record<string, string> = {
  pending:          "bg-gray-500",
  running:          "bg-blue-500 animate-pulse",
  waiting_approval: "bg-yellow-500",
  succeeded:        "bg-emerald-500",
  failed:           "bg-red-500",
  rejected:         "bg-red-400",
}

interface Props {
  onApprovalNeeded: (runId: string) => void
  onRunsUpdated: (runs: NativeRun[]) => void
}

export default function StatusPanel({ onApprovalNeeded, onRunsUpdated }: Props) {
  const [runs, setRuns] = useState<NativeRun[]>([])
  const [paused, setPaused] = useState(false)
  const notifiedRef = useRef(new Set<string>())

  useEffect(() => {
    const load = async () => {
      if (paused) return
      try {
        const data = await listRuns({ limit: 15 })
        setRuns(data)
        onRunsUpdated(data)

        for (const run of data) {
          for (const exec of run.executions) {
            if (exec.status === "waiting_approval") {
              onApprovalNeeded(run.id)
              if (!notifiedRef.current.has(exec.id)) {
                notifiedRef.current.add(exec.id)
                invoke("send_notification", {
                  title: "VisionArk 窶・謇ｿ隱阪′蠢・ｦ√〒縺・,
                  body: `縲・{exec.kind}縲阪・螳溯｡後ｒ遒ｺ隱阪＠縺ｦ縺上□縺輔＞`,
                }).catch(() => {})
              }
            }
          }
        }
      } catch {
        // not yet authenticated
      }
    }

    load()
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [paused, onApprovalNeeded, onRunsUpdated])

  // Flatten executions for display
  const allExecs: RunExecution[] = runs.flatMap(r => r.executions)
  const activeExecs = allExecs.filter(e => ["pending", "running", "waiting_approval"].includes(e.status))
  const needsApproval = allExecs.filter(e => e.status === "waiting_approval")
  const firstApprovalRun = needsApproval.length > 0
    ? runs.find(r => r.executions.some(e => e.status === "waiting_approval"))
    : null

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
      {needsApproval.length > 0 && firstApprovalRun && (
        <button
          onClick={() => onApprovalNeeded(firstApprovalRun.id)}
          className="mx-2 mt-2 flex items-center gap-2 px-2.5 py-2 bg-yellow-500/10 hover:bg-yellow-500/20 rounded-xl border border-yellow-500/30 transition-colors text-left"
        >
          <Bell size={12} className="text-yellow-400 flex-shrink-0" />
          <span className="text-xs text-yellow-300 leading-tight">
            {needsApproval.length} 莉ｶ縺ｮ謇ｿ隱榊ｾ・■
          </span>
        </button>
      )}

      {/* Stats row */}
      <div className="flex gap-2 px-2 py-2">
        {[
          { label: "Running", count: allExecs.filter(e => e.status === "running").length,   color: "text-blue-400" },
          { label: "Pending", count: allExecs.filter(e => e.status === "pending").length,   color: "text-gray-400" },
          { label: "Done",    count: allExecs.filter(e => e.status === "succeeded").length, color: "text-emerald-400" },
        ].map(({ label, count, color }) => (
          <div key={label} className="flex-1 flex flex-col items-center py-1.5 bg-gray-900 rounded-lg">
            <span className={`text-sm font-semibold ${color}`}>{count}</span>
            <span className="text-[10px] text-gray-600 mt-0.5">{label}</span>
          </div>
        ))}
      </div>

      {/* Active executions list */}
      <div className="flex-1 overflow-y-auto px-2 space-y-1 pb-2">
        {activeExecs.length === 0 ? (
          <p className="text-[11px] text-gray-700 text-center py-4">No active executions</p>
        ) : (
          activeExecs.map((exec) => (
            <div
              key={exec.id}
              className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-900/60 border border-gray-800"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${EXEC_STATUS_COLORS[exec.status] ?? "bg-gray-500"}`}
              />
              <span className="text-[11px] text-gray-300 truncate flex-1">{exec.kind}</span>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}

