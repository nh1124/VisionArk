"use client"

import { useEffect, useState } from "react"
import { ShieldCheck, RefreshCw, Clock } from "lucide-react"
import { useJobStore } from "@/store/useJobStore"
import JobStatusChip from "@/components/native/JobStatusChip"
import RiskBadge from "@/components/native/RiskBadge"
import SourceAttributionTag from "@/components/native/SourceAttributionTag"
import ApprovalDialog from "@/components/native/ApprovalDialog"
import type { Job } from "@/types/native"

export default function ApprovalCenterPage() {
  const { jobs, loading, fetchJobs, approveJob, rejectJob } = useJobStore()
  const [approvalJob, setApprovalJob] = useState<Job | null>(null)

  useEffect(() => {
    fetchJobs({ status: "needs_approval" })
  }, [])

  const pendingJobs = jobs.filter((j) => j.status === "needs_approval")

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800/50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-yellow-500/10 rounded-xl flex items-center justify-center">
            <ShieldCheck size={16} className="text-yellow-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white">Approval Center</h1>
            <p className="text-xs text-gray-500">{pendingJobs.length} pending</p>
          </div>
        </div>
        <button
          onClick={() => fetchJobs({ status: "needs_approval" })}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {loading && pendingJobs.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw size={20} className="animate-spin text-gray-600" />
          </div>
        ) : pendingJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-600">
            <ShieldCheck size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No approvals pending</p>
            <p className="text-xs text-gray-700 mt-1">High-risk jobs awaiting review appear here</p>
          </div>
        ) : (
          pendingJobs.map((job) => (
            <div
              key={job.id}
              className="bg-gray-900 border border-yellow-500/20 rounded-2xl overflow-hidden"
            >
              <div className="p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200">{job.type}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <SourceAttributionTag source={job.source} />
                      <span className="text-xs text-gray-600">
                        {new Date(job.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <RiskBadge level={job.risk_level} />
                </div>

                {job.tags.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {job.tags.map((tag) => (
                      <span key={tag} className="px-2 py-0.5 bg-gray-800 text-gray-500 rounded text-xs">{tag}</span>
                    ))}
                  </div>
                )}

                {/* Expiry indicator placeholder */}
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  <Clock size={11} />
                  <span>Awaiting your decision</span>
                </div>

                <div className="flex gap-2 pt-1">
                  <button
                    onClick={() => setApprovalJob(job)}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 rounded-xl text-xs font-semibold transition-colors border border-yellow-500/20"
                  >
                    <ShieldCheck size={13} />
                    Review
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {approvalJob && (
        <ApprovalDialog
          job={approvalJob}
          onApprove={approveJob}
          onReject={rejectJob}
          onClose={() => {
            setApprovalJob(null)
            fetchJobs({ status: "needs_approval" })
          }}
        />
      )}
    </div>
  )
}
