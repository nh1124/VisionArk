"use client"

import { useEffect, useState } from "react"
import { Play, RefreshCw, RotateCcw, Plus, Monitor, X } from "lucide-react"
import { apiFetch } from "@/lib/api"
import { useJobStore } from "@/store/useJobStore"
import JobStatusChip from "@/components/native/JobStatusChip"
import RiskBadge from "@/components/native/RiskBadge"
import SourceAttributionTag from "@/components/native/SourceAttributionTag"
import ApprovalDialog from "@/components/native/ApprovalDialog"
import type { Job, JobStatus, NativeDevice } from "@/types/native"

const STATUS_FILTERS: { label: string; value: JobStatus | "" }[] = [
  { label: "All", value: "" },
  { label: "Queued", value: "queued" },
  { label: "Running", value: "running" },
  { label: "Approval", value: "needs_approval" },
  { label: "Succeeded", value: "succeeded" },
  { label: "Failed", value: "failed" },
  { label: "Rejected", value: "rejected" },
]

function DeviceStatusDot({ status }: { status: string }) {
  if (status === "online") return <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
  if (status === "stale") return <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
  return <span className="w-1.5 h-1.5 rounded-full bg-gray-600 inline-block" />
}

// ── New Job Modal ─────────────────────────────────────────────────────────────

interface NewJobModalProps {
  devices: NativeDevice[]
  onClose: () => void
  onCreated: () => void
}

function NewJobModal({ devices, onClose, onCreated }: NewJobModalProps) {
  const [jobType, setJobType] = useState("")
  const [payload, setPayload] = useState("{}")
  const [riskLevel, setRiskLevel] = useState("low")
  const [targetDeviceId, setTargetDeviceId] = useState<string>("auto")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enabledDevices = devices.filter(d => d.is_enabled)

  const handleSubmit = async () => {
    if (!jobType.trim()) { setError("Job type is required"); return }
    let parsedPayload: Record<string, unknown> = {}
    try { parsedPayload = JSON.parse(payload) } catch {
      setError("Payload must be valid JSON"); return
    }
    setSubmitting(true)
    setError(null)
    try {
      const body: Record<string, unknown> = {
        type: jobType.trim(),
        payload: parsedPayload,
        risk_level: riskLevel,
        routing_mode: targetDeviceId === "auto" ? "auto" : "manual",
      }
      if (targetDeviceId !== "auto") body.target_device_id = targetDeviceId
      const res = await apiFetch("/api/jobs", {
        method: "POST",
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error((d as { detail?: string }).detail ?? "Failed to create job")
      }
      onCreated()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <Play size={15} className="text-blue-400" />
            <span className="text-sm font-semibold text-white">New Job</span>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors">
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Job type */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Job Type <span className="text-red-400">*</span></label>
            <input
              value={jobType}
              onChange={e => setJobType(e.target.value)}
              placeholder="e.g. local.dev, file.sync"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Payload */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Payload (JSON)</label>
            <textarea
              value={payload}
              onChange={e => setPayload(e.target.value)}
              rows={3}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder-gray-600 focus:outline-none focus:border-blue-500 resize-none"
            />
          </div>

          {/* Risk level */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Risk Level</label>
            <div className="flex gap-2">
              {(["low", "medium", "high", "critical"] as const).map(level => (
                <button
                  key={level}
                  onClick={() => setRiskLevel(level)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                    riskLevel === level
                      ? level === "low" ? "bg-green-600/30 text-green-300"
                        : level === "medium" ? "bg-yellow-600/30 text-yellow-300"
                        : level === "high" ? "bg-orange-600/30 text-orange-300"
                        : "bg-red-600/30 text-red-300"
                      : "bg-gray-800 text-gray-500 hover:bg-gray-700"
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Target device */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Target Device</label>
            <select
              value={targetDeviceId}
              onChange={e => setTargetDeviceId(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              <option value="auto">Auto-route (best available device)</option>
              {enabledDevices.map(d => (
                <option key={d.id} value={d.id}>
                  {d.display_name} ({d.platform}) — {d.status}
                </option>
              ))}
            </select>
            {enabledDevices.length === 0 && (
              <p className="text-xs text-yellow-500 mt-1">No enabled devices. Enable a device in Settings › Devices.</p>
            )}
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-950/30 px-3 py-2 rounded-lg border border-red-900/50">{error}</p>
          )}
        </div>

        <div className="flex justify-end gap-2 px-5 pb-5">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm bg-blue-600 hover:bg-blue-500 text-white font-medium transition-colors disabled:opacity-50"
          >
            {submitting ? <RefreshCw size={13} className="animate-spin" /> : <Plus size={13} />}
            Create Job
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function JobCenterPage() {
  const { jobs, loading, filter, fetchJobs, setFilter, approveJob, rejectJob } = useJobStore()
  const [approvalJob, setApprovalJob] = useState<Job | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<JobStatus | "">("")
  const [showNewJob, setShowNewJob] = useState(false)
  const [devices, setDevices] = useState<NativeDevice[]>([])

  useEffect(() => {
    fetchJobs()
    apiFetch("/api/native/devices")
      .then(r => r.json())
      .then(d => setDevices(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  const handleStatusFilter = (value: JobStatus | "") => {
    setStatusFilter(value)
    setFilter(value ? { ...filter, status: value } : { ...filter, status: undefined })
  }

  const deviceName = (id?: string) => {
    if (!id) return null
    const d = devices.find(x => x.id === id)
    return d ? d.display_name : id.slice(0, 8) + "…"
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
        <div className="flex items-center gap-2">
          <button
            onClick={() => fetchJobs()}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
          <button
            onClick={() => setShowNewJob(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
          >
            <Plus size={13} />
            New Job
          </button>
        </div>
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
                    {job.target_device_id && (
                      <span className="flex items-center gap-1 px-2 py-0.5 bg-purple-900/30 text-purple-300 rounded text-xs">
                        <Monitor size={10} />
                        {deviceName(job.target_device_id)}
                      </span>
                    )}
                    {!job.target_device_id && job.routing_mode === "auto" && (
                      <span className="px-2 py-0.5 bg-gray-800 text-gray-500 rounded text-xs">auto-route</span>
                    )}
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
                  {/* Device info */}
                  {(job.target_device_id || job.claimed_by_device_id) && (
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      {job.target_device_id && (
                        <span className="flex items-center gap-1">
                          <Monitor size={11} className="text-purple-400" />
                          <span className="text-gray-400">Target:</span>
                          {deviceName(job.target_device_id)}
                        </span>
                      )}
                      {job.claimed_by_device_id && (
                        <span className="flex items-center gap-1">
                          <Monitor size={11} className="text-green-400" />
                          <span className="text-gray-400">Claimed by:</span>
                          {deviceName(job.claimed_by_device_id)}
                        </span>
                      )}
                    </div>
                  )}

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
                    {(job.status === "failed" || job.status === "rejected") && (
                      <button
                        onClick={async () => {
                          await apiFetch(`/api/jobs/${job.id}/retry`, { method: "POST" })
                          fetchJobs()
                        }}
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

      {showNewJob && (
        <NewJobModal
          devices={devices}
          onClose={() => setShowNewJob(false)}
          onCreated={() => fetchJobs()}
        />
      )}
    </div>
  )
}
