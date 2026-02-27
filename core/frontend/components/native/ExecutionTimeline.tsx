interface TimelineStep {
  label: string
  time?: string
  status: "done" | "active" | "pending" | "error"
}

interface Props {
  steps: TimelineStep[]
}

const dotStyle: Record<TimelineStep["status"], string> = {
  done:    "bg-emerald-500",
  active:  "bg-blue-500 animate-pulse",
  pending: "bg-gray-700",
  error:   "bg-red-500",
}

export default function ExecutionTimeline({ steps }: Props) {
  return (
    <ol className="relative">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3 pb-4 last:pb-0">
          <div className="flex flex-col items-center">
            <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 mt-1 ${dotStyle[step.status]}`} />
            {i < steps.length - 1 && (
              <span className="w-px flex-1 bg-gray-800 mt-1" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-300">{step.label}</p>
            {step.time && (
              <p className="text-xs text-gray-600 mt-0.5">{step.time}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}
