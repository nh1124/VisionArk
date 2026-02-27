import { Mail, Monitor, MousePointer, Cloud } from "lucide-react"
import type { JobSource } from "@/types/native"

const config: Record<string, { label: string; className: string; Icon: React.ComponentType<{ size?: number }> }> = {
  native: { label: "Native",  className: "bg-purple-500/15 text-purple-400 border-purple-500/30", Icon: Monitor },
  web:    { label: "Web",     className: "bg-blue-500/15 text-blue-400 border-blue-500/30",       Icon: Cloud },
  cloud:  { label: "Cloud",   className: "bg-sky-500/15 text-sky-400 border-sky-500/30",           Icon: Cloud },
  mobile: { label: "Mobile",  className: "bg-indigo-500/15 text-indigo-400 border-indigo-500/30", Icon: Monitor },
  email:  { label: "Email",   className: "bg-orange-500/15 text-orange-400 border-orange-500/30", Icon: Mail },
  manual: { label: "Manual",  className: "bg-gray-800 text-gray-400 border-gray-700",             Icon: MousePointer },
}

interface Props {
  source: JobSource
  className?: string
}

export default function SourceAttributionTag({ source, className = "" }: Props) {
  const { label, className: tagClass, Icon } = config[source] ?? {
    label: source,
    className: "bg-gray-800 text-gray-400 border-gray-700",
    Icon: Monitor,
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${tagClass} ${className}`}
    >
      <Icon size={10} />
      {label}
    </span>
  )
}
