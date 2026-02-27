"use client"

import { useEffect, useState } from "react"
import { Play, RefreshCw, RotateCcw } from "lucide-react"
import { useJobStore } from "@/store/useJobStore"
import JobStatusChip from "@/components/native/JobStatusChip"
import RiskBadge from "@/components/native/RiskBadge"
import SourceAttributionTag from "@/components/native/SourceAttributionTag"
import ApprovalDialog from "@/components/native/ApprovalDialog"
import type { Job, JobStatus } from "@/types/native"

const STATUS_FILTERS: { label: string; value: JobStatus | "" }[] = [
  { label: "All", value: "" },
  { label: "Queued", value: "queued" },
  { label: "Running", value: "running" },
  { label: "Approval", value: "needs_approval" },
  { label: "Succeeded", value: "succeeded" },
  { label: "Failed", value: "failed" },
  { label: "Rejected", value: "rejected" },
]

export default function JobCenterPage() {
  const { jobs, loading, filter, fetchJobs, setFilter, approveJob, rejectJob } = useJobStore()
  const [approvalJob, setApprovalJob] = useState<Job | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<JobStatus | "">("")

  useEffect(() => {
    fetchJobs()
  }, [])

  const handleStatusFilter = (value: JobStatus | "") => {
    setStatusFilter(value)
    setFilter(value ? { ...filter, status: value } : { ...filter, status: undefined })
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800/50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-600/20 rounded-xl flex items-center justify-center">
            <Play size={16} className="text-blue-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white">Job Center</h1>
            <p className="text-xs text-gray-500">{jobs.length} jobs</p>
          </div>
        </div>
        <button
          onClick={() => fetchJobs()}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-2 px-6 py-3 border-b border-gray-800/30 flex-shrink-0 overflow-x-auto">
        {STATUS_FILTERS.map(({ label, value }) => (
          <button
            key={value}
            onClick={() => handleStatusFilter(value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
              statusFilter === value
                ? "bg-cyan-500 text-white"
                : "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Job List */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
        {loading && jobs.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <RefreshCw size={20} className="animate-spin text-gray-600" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-600">
            <Play size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No jobs found</p>
          </div>
        ) : (
          jobs.map((job) => (
            <div
              key={job.id}
              className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden"
            >
              <button
                className="w-full flex items-center gap-3 p-4 text-left hover:bg-gray-800/40 transition-colors"
                onClick={() => setExpanded(expanded === job.id ? null : job.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-200 truncate">{job.type}</span>
                    <SourceAttributionTag source={job.source} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {new Date(job.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <RiskBadge level={job.risk_level} />
                  <JobStatusChip status={job.status} />
                </div>
              </button>

              {expanded === job.id && (
                <div className="border-t border-gray-800 p-4 space-y-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    {job.tags.map((tag) => (
                      <span key={tag} className="px-2 py-0.5 bg-gray-800 text-gray-400 rounded text-xs">{tag}</span>
                    ))}
                  </div>
                  {Object.keys(job.payload).length > 0 && (
                    <div className="bg-gray-950 rounded-xl p-3 border border-gray-800">
                      <p className="text-xs text-gray-500 mb-1">Payload</p>
                      <pre className="text-xs text-gray-400 whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
                        {JSON.stringify(job.payload, null, 2)}
                      </pre>
                    </div>
                  )}
                  {job.error_log && (
                    <div className="bg-red-500/10 rounded-xl p-3 border border-red-500/20">
                      <p className="text-xs text-red-400">{job.error_log}</p>
                    </div>
                  )}
                  <div className="flex gap-2">
                    {job.status === "needs_approval" && (
                      <button
                        onClick={() => setApprovalJob(job)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 rounded-lg text-xs font-medium transition-colors"
                      >
                        Review
                      </button>
                    )}
                    {job.status === "failed" && (
                      <button
                        onClick={() => fetchJobs()}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-xs font-medium transition-colors"
                      >
                        <RotateCcw size={11} />
                        Retry
                      </button>
                    )}
                  </div>
                </div>
              )}
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
            fetchJobs()
          }}
        />
      )}
    </div>
  )
}
