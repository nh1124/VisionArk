"use client"

import { useState } from "react"
import { ShieldCheck, ShieldX, X, AlertTriangle } from "lucide-react"
import type { Job } from "@/types/native"
import RiskBadge from "./RiskBadge"

interface Props {
  job: Job
  onApprove: (id: string) => Promise<void>
  onReject: (id: string) => Promise<void>
  onClose: () => void
}

export default function ApprovalDialog({ job, onApprove, onReject, onClose }: Props) {
  const [loading, setLoading] = useState(false)

  const handle = async (action: "approve" | "reject") => {
    setLoading(true)
    try {
      if (action === "approve") await onApprove(job.id)
      else await onReject(job.id)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-3 p-5 border-b border-gray-800">
          <div className="w-9 h-9 rounded-xl bg-yellow-500/10 flex items-center justify-center">
            <AlertTriangle size={18} className="text-yellow-400" />
          </div>
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-white">Approval Required</h2>
            <p className="text-xs text-gray-500">{job.type}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Risk Level</span>
            <RiskBadge level={job.risk_level} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Source</span>
            <span className="text-xs text-gray-300 capitalize">{job.source}</span>
          </div>
          {job.tags.length > 0 && (
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs text-gray-500 flex-shrink-0">Tags</span>
              <div className="flex flex-wrap gap-1 justify-end">
                {job.tags.map((tag) => (
                  <span key={tag} className="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs">{tag}</span>
                ))}
              </div>
            </div>
          )}
          {Object.keys(job.payload).length > 0 && (
            <div className="bg-gray-950 rounded-xl p-3 border border-gray-800">
              <p className="text-xs text-gray-500 mb-2">Payload</p>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all max-h-36 overflow-y-auto">
                {JSON.stringify(job.payload, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-3 p-5 border-t border-gray-800">
          <button
            onClick={() => handle("approve")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldCheck size={15} />
            Approve
          </button>
          <button
            onClick={() => handle("reject")}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600/80 hover:bg-red-500 text-white rounded-xl text-sm font-semibold transition-colors disabled:opacity-50"
          >
            <ShieldX size={15} />
            Reject
          </button>
        </div>
      </div>
    </div>
  )
}
