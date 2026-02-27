import React, { useEffect, useState } from "react"
import { ArrowLeft, RefreshCw } from "lucide-react"
import type { Job } from "../../../shared/types"
import { listJobs } from "../../../bridge/api"

interface Props {
  onBack: () => void
}

export default function ExecutionConsole({ onBack }: Props) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await listJobs({ limit: 20 })
      setJobs(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const statusColor = (status: string) => {
    switch (status) {
      case "running": return "text-blue-400"
      case "succeeded": return "text-emerald-400"
      case "failed": return "text-red-400"
      case "needs_approval": return "text-yellow-400"
      case "rejected": return "text-red-300"
      default: return "text-gray-400"
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-gray-800">
        <button
          onClick={onBack}
          className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft size={14} />
        </button>
        <span className="text-sm font-semibold flex-1">Execution Console</span>
        <button
          onClick={load}
          disabled={loading}
          className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 font-mono text-xs">
        {jobs.length === 0 ? (
          <p className="text-gray-600 text-center py-8">No jobs found</p>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="flex flex-col gap-0.5 bg-gray-900 rounded-lg p-2 border border-gray-800">
              <div className="flex justify-between">
                <span className="text-gray-300">{job.type}</span>
                <span className={statusColor(job.status)}>{job.status}</span>
              </div>
              <div className="flex justify-between text-gray-600">
                <span>{job.source}</span>
                <span>{new Date(job.created_at).toLocaleTimeString()}</span>
              </div>
              {job.error_log && (
                <p className="text-red-400 mt-1">{job.error_log}</p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
