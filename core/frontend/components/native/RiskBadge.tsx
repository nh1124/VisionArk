import type { RiskLevel } from "@/types/native"

const styles: Record<RiskLevel, string> = {
  low:      "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  medium:   "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  high:     "bg-red-500/15 text-red-400 border-red-500/30",
  critical: "bg-red-600/20 text-red-300 border-red-600/40 animate-pulse",
}

interface Props {
  level: RiskLevel
  className?: string
}

export default function RiskBadge({ level, className = "" }: Props) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${styles[level]} ${className}`}
    >
      {level.toUpperCase()}
    </span>
  )
}
