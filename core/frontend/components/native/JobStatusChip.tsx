import type { JobStatus } from "@/types/native"
import { Loader2, CheckCircle, XCircle, Clock, ShieldAlert, Ban } from "lucide-react"

const config: Record<JobStatus, { label: string; className: string; Icon: React.ComponentType<{ size?: number; className?: string }> }> = {
  queued:         { label: "Queued",     className: "bg-gray-800 text-gray-400 border-gray-700",          Icon: Clock },
  running:        { label: "Running",    className: "bg-blue-500/15 text-blue-400 border-blue-500/30",    Icon: Loader2 },
  needs_approval: { label: "Approval",   className: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30", Icon: ShieldAlert },
  succeeded:      { label: "Succeeded",  className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30", Icon: CheckCircle },
  failed:         { label: "Failed",     className: "bg-red-500/15 text-red-400 border-red-500/30",       Icon: XCircle },
  rejected:       { label: "Rejected",   className: "bg-gray-800 text-gray-500 border-gray-700",          Icon: Ban },
}

interface Props {
  status: JobStatus
  className?: string
}

export default function JobStatusChip({ status, className = "" }: Props) {
  const { label, className: chipClass, Icon } = config[status] ?? config.queued
  const spinning = status === "running"
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${chipClass} ${className}`}
    >
      <Icon size={11} className={spinning ? "animate-spin" : ""} />
      {label}
    </span>
  )
}
