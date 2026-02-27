import React, { useEffect, useState } from "react"
import { ShieldCheck, ShieldX, AlertTriangle } from "lucide-react"
import type { Job } from "../../../shared/types"
import { getJob, approveJob, rejectJob } from "../../../bridge/api"

interface Props {
  jobId: string
  onDone: () => void
}

export default function ApprovalPopup({ jobId, onDone }: Props) {
  const [job, setJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getJob(jobId).then(setJob).catch(console.error)
  }, [jobId])

  const handleApprove = async () => {
    setLoading(true)
    try {
      await approveJob(jobId)
    } finally {
      setLoading(false)
      onDone()
    }
  }

  const handleReject = async () => {
    setLoading(true)
    try {
      await rejectJob(jobId)
    } finally {
      setLoading(false)
      onDone()
    }
  }

  if (!job) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <span className="text-gray-500 text-sm">Loading...</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle size={18} className="text-yellow-400" />
        <span className="text-sm font-semibold text-white">Approval Required</span>
      </div>

      <div className="bg-gray-900 rounded-2xl p-3 space-y-2 border border-gray-800">
        <div className="flex justify-between text-xs">
          <span className="text-gray-500">Type</span>
          <span className="text-gray-200">{job.type}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-gray-500">Risk</span>
          <span className={
            job.risk_level === "critical" ? "text-red-400" :
            job.risk_level === "high" ? "text-orange-400" :
            job.risk_level === "medium" ? "text-yellow-400" :
            "text-emerald-400"
          }>{job.risk_level.toUpperCase()}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-gray-500">Source</span>
          <span className="text-gray-200">{job.source}</span>
        </div>
      </div>

      {Object.keys(job.payload).length > 0 && (
        <div className="bg-gray-900/60 rounded-xl p-3 border border-gray-800">
          <p className="text-xs text-gray-500 mb-1">Payload</p>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all">
            {JSON.stringify(job.payload, null, 2)}
          </pre>
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleApprove}
          disabled={loading}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
        >
          <ShieldCheck size={15} />
          Approve
        </button>
        <button
          onClick={handleReject}
          disabled={loading}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 bg-red-600/80 hover:bg-red-500 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
        >
          <ShieldX size={15} />
          Reject
        </button>
      </div>
    </div>
  )
}
