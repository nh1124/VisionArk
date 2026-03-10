import React, { useEffect, useRef, useState } from "react"
import { invoke } from "@tauri-apps/api/core"
import { Play, Pause, Terminal, Bell } from "lucide-react"
import type { NativeRun, RunExecution } from "../../../shared/types"
import { listRuns } from "../../../bridge/api"

interface Props {
  onApprovalNeeded: (runId: string) => void
  onOpenConsole: () => void
}

export default function ResidentPanel({ onApprovalNeeded, onOpenConsole }: Props) {
  const [runs, setRuns] = useState<NativeRun[]>([])
  const [paused, setPaused] = useState(false)
  const notifiedRef = useRef(new Set<string>())

  useEffect(() => {
    const load = async () => {
      if (paused) return
      try {
        const data = await listRuns({ limit: 10 })
        setRuns(data)

        // Find any execution waiting for approval
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
        // ignore 窶・not authenticated yet
      }
    }
    load()
    const timer = setInterval(load, 5_000)
    return () => clearInterval(timer)
  }, [paused, onApprovalNeeded])

  // Flatten active executions across all runs
  const activeExecs: Array<{ run: NativeRun; exec: RunExecution }> = []
  for (const run of runs) {
    for (const exec of run.executions) {
      if (["pending", "running", "waiting_approval"].includes(exec.status)) {
        activeExecs.push({ run, exec })
      }
    }
  }

  const hasApproval = activeExecs.some(({ exec }) => exec.status === "waiting_approval")

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
        {activeExecs.length === 0 ? (
          <p className="text-xs text-gray-600 text-center py-4">No active executions</p>
        ) : (
          activeExecs.map(({ exec }) => (
            <div
              key={exec.id}
              className="flex items-center gap-2 px-3 py-2 bg-gray-900 rounded-xl border border-gray-800"
            >
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  exec.status === "waiting_approval"
                    ? "bg-yellow-500"
                    : "bg-blue-500 animate-pulse"
                }`}
              />
              <span className="text-xs text-gray-300 truncate flex-1">{exec.kind}</span>
              <span className="text-xs text-gray-600">{exec.status}</span>
            </div>
          ))
        )}
      </div>

      {hasApproval && (
        <div className="flex items-center gap-2 px-3 py-2 bg-yellow-500/10 rounded-xl border border-yellow-500/30">
          <Bell size={14} className="text-yellow-400 flex-shrink-0" />
          <span className="text-xs text-yellow-300">謇ｿ隱阪′蠢・ｦ√〒縺・/span>
        </div>
      )}
    </div>
  )
}

