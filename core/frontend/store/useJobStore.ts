import { create } from "zustand"
import { apiFetch } from "@/lib/api"
import type { Job, JobStatus, JobSource } from "@/types/native"

interface JobFilter {
  status?: JobStatus
  type?: string
  source?: JobSource
}

interface JobState {
  jobs: Job[]
  loading: boolean
  filter: JobFilter

  setFilter: (filter: JobFilter) => void
  fetchJobs: (filter?: JobFilter) => Promise<void>
  approveJob: (id: string) => Promise<void>
  rejectJob: (id: string) => Promise<void>
}

export const useJobStore = create<JobState>((set, get) => ({
  jobs: [],
  loading: false,
  filter: {},

  setFilter: (filter) => {
    set({ filter })
    get().fetchJobs(filter)
  },

  fetchJobs: async (filter) => {
    set({ loading: true })
    const active = filter ?? get().filter
    const params = new URLSearchParams()
    if (active.status) params.set("status", active.status)
    if (active.type) params.set("type", active.type)
    if (active.source) params.set("source", active.source)
    params.set("limit", "100")
    try {
      const res = await apiFetch(`/api/jobs?${params.toString()}`)
      const data: Job[] = await res.json()
      set({ jobs: Array.isArray(data) ? data : [], loading: false })
    } catch {
      set({ loading: false })
    }
  },

  approveJob: async (id) => {
    const res = await apiFetch(`/api/jobs/${id}/approve`, { method: "POST" })
    if (res.ok) {
      const updated: Job = await res.json()
      set((state) => ({
        jobs: state.jobs.map((j) => (j.id === id ? updated : j)),
      }))
    }
  },

  rejectJob: async (id) => {
    const res = await apiFetch(`/api/jobs/${id}/reject`, { method: "POST" })
    if (res.ok) {
      const updated: Job = await res.json()
      set((state) => ({
        jobs: state.jobs.map((j) => (j.id === id ? updated : j)),
      }))
    }
  },
}))
