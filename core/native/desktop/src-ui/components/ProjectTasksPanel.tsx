import React, { useCallback, useEffect, useMemo, useState } from "react"
import { CheckCircle2, Circle, RefreshCw } from "lucide-react"
import {
  completeLBSTask,
  getOverdueTasks,
  listLBSTasks,
  listProjects,
  type LBSTask,
  type Project,
} from "../lib/api"
import TaskEditPanel from "./TaskEditPanel"

interface Props {
  projectId: string
  projectName: string
}

function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

export default function ProjectTasksPanel({ projectId, projectName }: Props) {
  const [projects, setProjects] = useState<Project[]>([])
  const [tasks, setTasks] = useState<LBSTask[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [editTargetDate, setEditTargetDate] = useState<string>(todayISO())
  const [refreshKey, setRefreshKey] = useState(0)
  const [toggling, setToggling] = useState<Set<string>>(new Set())

  const availableProjects = useMemo(() => {
    const names = projects.map((p) => p.name).filter(Boolean)
    return Array.from(new Set(["inbox", ...names]))
  }, [projects])

  const loadTasks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [projectList, activeTasks, overdueTasks] = await Promise.all([
        listProjects(),
        listLBSTasks({ active: true }),
        getOverdueTasks(),
      ])
      setProjects(projectList)
      const currentProject = projectList.find((p) => p.id === projectId)
      const contextCandidates = Array.from(
        new Set(
          [
            currentProject?.name || "",
            currentProject?.display_name || "",
            projectName || "",
          ]
            .map((v) => v.trim())
            .filter(Boolean)
        )
      )

      const candidateSet = new Set(
        [
          ...contextCandidates,
          ...(currentProject?.name ? [currentProject.name] : []),
          ...(currentProject?.display_name ? [currentProject.display_name] : []),
        ]
          .map((v) => v.trim().toLowerCase())
          .filter(Boolean)
      )

      const merged = [...activeTasks, ...overdueTasks]
      const uniq = new Map<string, LBSTask>()
      for (const task of merged) {
        const key = task.task_id
        if (!uniq.has(key)) uniq.set(key, task)
      }

      const filtered = Array.from(uniq.values())
        .filter((t) => candidateSet.has((t.context || "").trim().toLowerCase()))
        .sort((a, b) => {
          if (a.status === "done" && b.status !== "done") return 1
          if (a.status !== "done" && b.status === "done") return -1
          return (a.task_name || "").localeCompare(b.task_name || "")
        })

      setTasks(filtered)
    } catch (e: any) {
      setError(e?.message || "Failed to load tasks")
    } finally {
      setLoading(false)
    }
  }, [projectId, projectName])

  useEffect(() => {
    void loadTasks()
  }, [loadTasks, refreshKey])

  useEffect(() => {
    const onRefresh = () => {
      setRefreshKey((k) => k + 1)
    }
    window.addEventListener("va-tasks-refresh", onRefresh as EventListener)
    return () => window.removeEventListener("va-tasks-refresh", onRefresh as EventListener)
  }, [])

  const handleToggle = async (task: LBSTask) => {
    if (toggling.has(task.task_id)) return
    const nextStatus = task.status === "done" ? "todo" : "done"
    const date = task.due_date || todayISO()

    setToggling((prev) => new Set(prev).add(task.task_id))
    setTasks((prev) => prev.map((t) => (t.task_id === task.task_id ? { ...t, status: nextStatus } : t)))
    try {
      await completeLBSTask(task.task_id, date, nextStatus)
    } catch {
      setTasks((prev) => prev.map((t) => (t.task_id === task.task_id ? { ...t, status: task.status } : t)))
    } finally {
      setToggling((prev) => {
        const next = new Set(prev)
        next.delete(task.task_id)
        return next
      })
    }
  }

  const openEdit = (task: LBSTask) => {
    setEditTargetDate(task.due_date || todayISO())
    setEditingTaskId(task.task_id)
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500">Project linked tasks</p>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-800/40 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto custom-scrollbar space-y-2 pr-1">
        {loading && tasks.length === 0 ? (
          <div className="text-xs text-gray-500 py-4">Loading tasks...</div>
        ) : tasks.length === 0 ? (
          <div className="text-xs text-gray-500 py-4">No tasks linked to this project.</div>
        ) : (
          tasks.map((task) => {
            const isDone = task.status === "done"
            return (
              <div
                key={task.task_id}
                onClick={() => openEdit(task)}
                className="w-full cursor-pointer rounded-xl border border-gray-800 bg-gray-900/40 px-3 py-2.5 hover:bg-gray-800/50 transition-colors"
              >
                <div className="flex items-start gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      void handleToggle(task)
                    }}
                    className="mt-0.5 text-gray-500 hover:text-cyan-400 transition-colors"
                    title={isDone ? "Mark as todo" : "Mark as done"}
                    disabled={toggling.has(task.task_id)}
                  >
                    {isDone ? <CheckCircle2 size={16} className="text-cyan-500" /> : <Circle size={16} />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm ${isDone ? "text-gray-500 line-through" : "text-gray-200"}`}>
                      {task.task_name}
                    </p>
                    <p className="text-[10px] text-gray-500 mt-1">
                      {task.context}
                      {task.due_date ? ` | ${task.due_date}` : ""}
                    </p>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      <TaskEditPanel
        taskId={editingTaskId}
        targetDate={editTargetDate}
        onClose={() => setEditingTaskId(null)}
        onSaved={() => setRefreshKey((k) => k + 1)}
        availableProjects={availableProjects}
      />
    </div>
  )
}
