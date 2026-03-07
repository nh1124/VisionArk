import React, { useEffect, useMemo, useState } from "react"
import {
    Activity,
    Bell,
    CircleHelp,
    PauseCircle,
    PlayCircle,
    Plus,
    RefreshCw,
    ShieldCheck,
    TestTube2,
    X,
} from "lucide-react"
import { apiFetch, listProjects, listSessions, Project } from "../lib/api"

interface MonitorJob {
    id: string
    name: string
    source_type: string
    source_config: Record<string, any>
    schedule_cron: string
    timezone: string
    detector_type: string
    detector_config: Record<string, any>
    notification_config: Record<string, any>
    cooldown_seconds: number
    max_retries: number
    retry_backoff_seconds: number
    is_active: boolean
    next_run_at: string | null
    last_run_at: string | null
    last_status: string | null
    last_error: string | null
    consecutive_failures: number
    created_at: string
}

interface MonitorRun {
    id: string
    monitor_job_id: string
    status: string
    severity: string | null
    retry_count: number
    started_at: string
    finished_at: string | null
    latency_ms: number | null
    error_log: string | null
    result_payload: Record<string, any>
}

interface MonitorAlert {
    id: string
    monitor_job_id: string
    monitor_job_run_id: string | null
    severity: string
    reason: string
    dedupe_key: string | null
    triggered_at: string
    sent_at: string | null
    notification_status: string
    metadata_payload: Record<string, any>
}

type Tab = "jobs" | "alerts"
type CronMode = "every5m" | "hourly" | "daily" | "weekly" | "custom"

const COMMON_TIMEZONES = [
    "UTC",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Asia/Singapore",
    "Asia/Shanghai",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
]

const CRON_MODE_OPTIONS: Array<{ value: CronMode; label: string; cron: string | null }> = [
    { value: "every5m", label: "Every 5 minutes", cron: "*/5 * * * *" },
    { value: "hourly", label: "Hourly", cron: "@hourly" },
    { value: "daily", label: "Daily", cron: "@daily" },
    { value: "weekly", label: "Weekly", cron: "@weekly" },
    { value: "custom", label: "Custom Cron", cron: null },
]

function resolveCron(mode: CronMode, custom: string): string {
    const matched = CRON_MODE_OPTIONS.find((opt) => opt.value === mode)
    if (!matched) return "*/5 * * * *"
    if (matched.cron) return matched.cron
    return custom.trim()
}

function createInitialForm() {
    return {
        name: "",
        url: "",
        cron_mode: "every5m" as CronMode,
        cron_custom: "",
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
        expected_status: "200",
        max_latency_ms: "",
        cooldown_seconds: "300",
        agent_delivery_enabled: false,
        agent_project_id: "",
        agent_session_id: "",
        agent_min_severity: "warn",
    }
}

export default function MonitoringJobsView() {
    const [jobs, setJobs] = useState<MonitorJob[]>([])
    const [alerts, setAlerts] = useState<MonitorAlert[]>([])
    const [runs, setRuns] = useState<MonitorRun[]>([])
    const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [runsLoading, setRunsLoading] = useState(false)
    const [tab, setTab] = useState<Tab>("jobs")

    const [isCreateOpen, setIsCreateOpen] = useState(false)
    const [showCronHelp, setShowCronHelp] = useState(false)
    const [projects, setProjects] = useState<Project[]>([])
    const [sessions, setSessions] = useState<Array<{ id: string; title: string | null; last_message_at: string | null }>>([])
    const [sessionsLoading, setSessionsLoading] = useState(false)
    const [form, setForm] = useState(createInitialForm)

    const selectedJob = useMemo(
        () => jobs.find((j) => j.id === selectedJobId) || null,
        [jobs, selectedJobId],
    )

    const formatDate = (value: string | null) => {
        if (!value) return "-"
        return new Date(value).toLocaleString()
    }

    const loadJobs = async () => {
        const res = await apiFetch("/api/monitor/jobs?limit=200")
        if (!res.ok) throw new Error("Failed to load monitor jobs")
        const data = await res.json()
        setJobs(data)
    }

    const loadAlerts = async () => {
        const res = await apiFetch("/api/monitor/alerts?limit=100")
        if (!res.ok) throw new Error("Failed to load monitor alerts")
        const data = await res.json()
        setAlerts(data)
    }

    const loadRuns = async (jobId: string) => {
        setRunsLoading(true)
        try {
            const res = await apiFetch(`/api/monitor/jobs/${jobId}/runs?limit=20`)
            if (!res.ok) throw new Error("Failed to load runs")
            const data = await res.json()
            setRuns(data)
        } finally {
            setRunsLoading(false)
        }
    }

    const reloadAll = async () => {
        setLoading(true)
        try {
            await Promise.all([loadJobs(), loadAlerts()])
            if (selectedJobId) {
                await loadRuns(selectedJobId)
            }
        } catch (e) {
            console.error(e)
            alert("Failed to load monitoring data.")
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        reloadAll()
    }, [])

    useEffect(() => {
        listProjects()
            .then((items) => setProjects(items))
            .catch((err) => console.error("Failed to load projects", err))
    }, [])

    useEffect(() => {
        const loadAgentSessions = async () => {
            if (!isCreateOpen || !form.agent_delivery_enabled || !form.agent_project_id) {
                setSessions([])
                return
            }

            setSessionsLoading(true)
            try {
                const items = await listSessions(form.agent_project_id)
                setSessions(items)
                const lastSessionId = localStorage.getItem(`va_last_session_${form.agent_project_id}`)
                const keepCurrent = items.some((item) => item.id === form.agent_session_id)
                const useLast = lastSessionId && items.some((item) => item.id === lastSessionId)
                setForm((prev) => ({
                    ...prev,
                    agent_session_id: keepCurrent ? prev.agent_session_id : useLast ? lastSessionId || "" : "",
                }))
            } catch (err) {
                console.error("Failed to load monitor sessions", err)
                setSessions([])
            } finally {
                setSessionsLoading(false)
            }
        }

        loadAgentSessions().catch(console.error)
    }, [isCreateOpen, form.agent_delivery_enabled, form.agent_project_id])

    useEffect(() => {
        if (selectedJobId) loadRuns(selectedJobId).catch(console.error)
    }, [selectedJobId])

    const handlePauseResume = async (job: MonitorJob) => {
        const path = job.is_active ? "pause" : "resume"
        const res = await apiFetch(`/api/monitor/jobs/${job.id}/${path}`, {
            method: "POST",
        })
        if (!res.ok) throw new Error("Failed to toggle state")
        await reloadAll()
    }

    const handleTest = async (job: MonitorJob) => {
        const res = await apiFetch(`/api/monitor/jobs/${job.id}/test`, { method: "POST" })
        if (!res.ok) throw new Error("Test run failed")
        await reloadAll()
        setSelectedJobId(job.id)
    }

    const handleCreate = async () => {
        const scheduleCron = resolveCron(form.cron_mode, form.cron_custom)

        if (!form.name || !form.url || !scheduleCron) {
            alert("Name, URL and cron are required.")
            return
        }
        if (form.cron_mode === "custom" && !form.cron_custom.trim()) {
            alert("Custom cron expression is required.")
            return
        }
        if (form.agent_delivery_enabled && !form.agent_project_id.trim()) {
            alert("Project ID is required when agent notification is enabled.")
            return
        }

        const expectedStatus = Number(form.expected_status || "200")
        const maxLatency = form.max_latency_ms ? Number(form.max_latency_ms) : undefined
        const cooldown = Number(form.cooldown_seconds || "0")

        const detector_config: Record<string, any> = { expected_status: expectedStatus }
        if (maxLatency && maxLatency > 0) detector_config.max_latency_ms = maxLatency

        const payload = {
            name: form.name,
            source_type: "URL",
            source_config: {
                url: form.url,
                timeout_seconds: 10,
            },
            schedule_cron: scheduleCron,
            timezone: form.timezone || "UTC",
            detector_type: "RULE_BASED",
            detector_config,
            notification_config: {
                channel: "in_app",
                agent_delivery: {
                    enabled: form.agent_delivery_enabled,
                    project_id: form.agent_project_id || undefined,
                    session_id: form.agent_session_id || undefined,
                    min_severity: form.agent_min_severity || "warn",
                },
            },
            cooldown_seconds: cooldown,
            max_retries: 2,
            retry_backoff_seconds: 60,
            is_active: true,
        }

        const res = await apiFetch("/api/monitor/jobs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
        if (!res.ok) {
            const msg = await res.text()
            throw new Error(msg || "Create failed")
        }

        setIsCreateOpen(false)
        setSessions([])
        setShowCronHelp(false)
        setForm(createInitialForm())
        await reloadAll()
    }

    return (
        <div className="flex-1 overflow-y-auto px-10 py-8 bg-[#030712] custom-scrollbar">
            <div className="max-w-7xl mx-auto">
                <header className="mb-8 flex items-center justify-between gap-3">
                    <div>
                        <h1 className="text-3xl font-black text-white tracking-tight flex items-center gap-3">
                            <ShieldCheck className="text-emerald-400" size={30} />
                            Monitoring Jobs
                        </h1>
                        <p className="text-gray-500 text-xs uppercase tracking-widest mt-1 font-bold">
                            Collect / Detect / Notify Pipeline
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <button
                            onClick={() => setIsCreateOpen(true)}
                            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-xl font-bold text-sm"
                        >
                            <Plus size={16} /> New Monitor
                        </button>
                        <button
                            onClick={reloadAll}
                            className="p-2.5 bg-gray-900 border border-gray-800 rounded-xl text-gray-300 hover:text-white"
                            title="Refresh"
                        >
                            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
                        </button>
                    </div>
                </header>

                <div className="flex gap-1 mb-5 p-1 bg-gray-900/50 rounded-2xl w-fit border border-gray-800/50">
                    <button
                        onClick={() => setTab("jobs")}
                        className={`px-5 py-2 rounded-xl text-xs font-bold ${tab === "jobs" ? "bg-gray-800 text-emerald-300" : "text-gray-500"}`}
                    >
                        JOBS
                    </button>
                    <button
                        onClick={() => setTab("alerts")}
                        className={`px-5 py-2 rounded-xl text-xs font-bold ${tab === "alerts" ? "bg-gray-800 text-rose-300" : "text-gray-500"}`}
                    >
                        ALERTS
                    </button>
                </div>

                {tab === "jobs" ? (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                        <div className="lg:col-span-2 bg-gray-900/40 border border-gray-800 rounded-2xl overflow-hidden">
                            <table className="w-full text-left">
                                <thead className="bg-gray-800/50">
                                    <tr>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Job</th>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Schedule</th>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Status</th>
                                        <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-800/50">
                                    {jobs.map((job) => (
                                        <tr
                                            key={job.id}
                                            className={`hover:bg-gray-800/20 cursor-pointer ${selectedJobId === job.id ? "bg-gray-800/30" : ""}`}
                                            onClick={() => setSelectedJobId(job.id)}
                                        >
                                            <td className="px-4 py-3">
                                                <div className="text-sm text-white font-semibold">{job.name}</div>
                                                <div className="text-[11px] text-gray-500 font-mono truncate max-w-[260px]">
                                                    {job.source_config?.url || "-"}
                                                </div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="text-xs text-gray-300 font-mono">{job.schedule_cron}</div>
                                                <div className="text-[11px] text-gray-500">{job.timezone}</div>
                                                <div className="text-[11px] text-gray-500">Next: {formatDate(job.next_run_at)}</div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center gap-2">
                                                    <span className={`inline-flex w-2 h-2 rounded-full ${job.last_status === "critical" || job.last_status === "failed"
                                                            ? "bg-rose-500"
                                                            : job.last_status === "warn"
                                                                ? "bg-amber-400"
                                                                : "bg-emerald-400"
                                                        }`} />
                                                    <span className="text-xs text-gray-300 uppercase">{job.last_status || "new"}</span>
                                                </div>
                                                <div className="text-[11px] text-gray-500">{job.is_active ? "active" : "paused"}</div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="flex items-center justify-end gap-1">
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            handleTest(job).catch((err) => alert(String(err)))
                                                        }}
                                                        className="p-2 rounded-lg text-cyan-300 hover:bg-cyan-500/10"
                                                        title="Run test once"
                                                    >
                                                        <TestTube2 size={15} />
                                                    </button>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            handlePauseResume(job).catch((err) => alert(String(err)))
                                                        }}
                                                        className="p-2 rounded-lg text-gray-300 hover:bg-gray-700/50"
                                                        title={job.is_active ? "Pause" : "Resume"}
                                                    >
                                                        {job.is_active ? <PauseCircle size={16} /> : <PlayCircle size={16} />}
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                    {jobs.length === 0 && (
                                        <tr>
                                            <td colSpan={4} className="px-4 py-10 text-center text-sm text-gray-500">
                                                No monitor jobs found.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <div className="bg-gray-900/40 border border-gray-800 rounded-2xl p-4">
                            <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                                <Activity size={14} className="text-cyan-400" />
                                Latest Runs
                            </h3>
                            {!selectedJob && <p className="text-xs text-gray-500">Select a job to view run history.</p>}
                            {selectedJob && (
                                <>
                                    <div className="text-xs text-gray-400 mb-2">{selectedJob.name}</div>
                                    <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1 custom-scrollbar">
                                        {runsLoading ? (
                                            <div className="text-xs text-gray-500">Loading runs...</div>
                                        ) : runs.length === 0 ? (
                                            <div className="text-xs text-gray-500">No runs yet.</div>
                                        ) : (
                                            runs.map((run) => (
                                                <div key={run.id} className="rounded-xl border border-gray-800 bg-gray-900/70 p-3">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <span className="text-xs uppercase text-gray-300">{run.status}</span>
                                                        <span className="text-[11px] text-gray-500">{formatDate(run.started_at)}</span>
                                                    </div>
                                                    <div className="text-[11px] text-gray-500">Latency: {run.latency_ms ?? "-"} ms</div>
                                                    {run.error_log && (
                                                        <div className="text-[11px] text-rose-300 mt-1 break-all">{run.error_log}</div>
                                                    )}
                                                </div>
                                            ))
                                        )}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className="bg-gray-900/40 border border-gray-800 rounded-2xl overflow-hidden">
                        <table className="w-full text-left">
                            <thead className="bg-gray-800/50">
                                <tr>
                                    <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Severity</th>
                                    <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Reason</th>
                                    <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Triggered</th>
                                    <th className="px-4 py-3 text-[10px] text-gray-500 uppercase tracking-wider">Notify</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800/50">
                                {alerts.map((alert) => (
                                    <tr key={alert.id}>
                                        <td className="px-4 py-3">
                                            <span className={`text-xs uppercase font-bold ${alert.severity === "critical" ? "text-rose-400" : "text-amber-300"}`}>
                                                {alert.severity}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-300">{alert.reason}</td>
                                        <td className="px-4 py-3 text-xs text-gray-400">{formatDate(alert.triggered_at)}</td>
                                        <td className="px-4 py-3">
                                            <span className="text-xs text-gray-300">{alert.notification_status}</span>
                                        </td>
                                    </tr>
                                ))}
                                {alerts.length === 0 && (
                                    <tr>
                                        <td colSpan={4} className="px-4 py-10 text-center text-sm text-gray-500">
                                            No alerts found.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {isCreateOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
                    <div className="bg-[#0A0A0A] border border-gray-800 rounded-3xl w-full max-w-xl p-6 relative">
                        <button
                            onClick={() => setIsCreateOpen(false)}
                            className="absolute top-4 right-4 text-gray-500 hover:text-white"
                        >
                            <X size={18} />
                        </button>

                        <h2 className="text-xl font-bold text-white mb-5 flex items-center gap-2">
                            <Bell size={18} className="text-emerald-400" />
                            Create Monitor Job
                        </h2>

                        <div className="space-y-3">
                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Name</label>
                                <input
                                    value={form.name}
                                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    placeholder="Service uptime check"
                                />
                            </div>

                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">URL</label>
                                <input
                                    value={form.url}
                                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                                    className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    placeholder="https://example.com/health"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <div className="flex items-center gap-1">
                                        <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Cron</label>
                                        <button
                                            type="button"
                                            className="text-gray-500 hover:text-cyan-300"
                                            onClick={() => setShowCronHelp((prev) => !prev)}
                                            title="Cron help"
                                        >
                                            <CircleHelp size={13} />
                                        </button>
                                    </div>
                                    <select
                                        value={form.cron_mode}
                                        onChange={(e) =>
                                            setForm({ ...form, cron_mode: e.target.value as CronMode })
                                        }
                                        className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    >
                                        {CRON_MODE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                    {form.cron_mode === "custom" && (
                                        <input
                                            value={form.cron_custom}
                                            onChange={(e) => setForm({ ...form, cron_custom: e.target.value })}
                                            className="mt-2 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white font-mono"
                                            placeholder="*/5 * * * *"
                                        />
                                    )}
                                    {showCronHelp && (
                                        <div className="mt-2 rounded-lg border border-cyan-900/50 bg-cyan-950/20 px-2.5 py-2 text-[11px] text-cyan-100">
                                            Presets are recommended. Use Custom Cron for 5-field expressions like
                                            <span className="font-mono"> */10 * * * *</span>.
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Timezone</label>
                                    <select
                                        value={form.timezone}
                                        onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                                        className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    >
                                        {!COMMON_TIMEZONES.includes(form.timezone) && (
                                            <option value={form.timezone}>{form.timezone}</option>
                                        )}
                                        {COMMON_TIMEZONES.map((tz) => (
                                            <option key={tz} value={tz}>
                                                {tz}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div className="grid grid-cols-3 gap-3">
                                <div>
                                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Expected Status</label>
                                    <input
                                        value={form.expected_status}
                                        onChange={(e) => setForm({ ...form, expected_status: e.target.value })}
                                        className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Max Latency (ms)</label>
                                    <input
                                        value={form.max_latency_ms}
                                        onChange={(e) => setForm({ ...form, max_latency_ms: e.target.value })}
                                        className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                        placeholder="Optional"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">Cooldown (s)</label>
                                    <input
                                        value={form.cooldown_seconds}
                                        onChange={(e) => setForm({ ...form, cooldown_seconds: e.target.value })}
                                        className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                    />
                                </div>
                            </div>

                            <div className="pt-2 border-t border-gray-800">
                                <label className="flex items-center gap-2 text-sm text-gray-300">
                                    <input
                                        type="checkbox"
                                        checked={form.agent_delivery_enabled}
                                        onChange={(e) =>
                                            setForm({ ...form, agent_delivery_enabled: e.target.checked })
                                        }
                                    />
                                    Notify Agent (via AES POST_MESSAGE)
                                </label>

                                {form.agent_delivery_enabled && (
                                    <div className="grid grid-cols-3 gap-3 mt-3">
                                        <div>
                                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                                                Project ID
                                            </label>
                                            <select
                                                value={form.agent_project_id}
                                                onChange={(e) =>
                                                    setForm({
                                                        ...form,
                                                        agent_project_id: e.target.value,
                                                        agent_session_id: "",
                                                    })
                                                }
                                                className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                            >
                                                <option value="">Select project</option>
                                                {projects.map((project) => (
                                                    <option key={project.id} value={project.id}>
                                                        {project.display_name || project.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                                                Session ID
                                            </label>
                                            <select
                                                value={form.agent_session_id}
                                                onChange={(e) =>
                                                    setForm({ ...form, agent_session_id: e.target.value })
                                                }
                                                className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                                disabled={!form.agent_project_id || sessionsLoading}
                                            >
                                                <option value="">Auto select on dispatch</option>
                                                {sessions.map((session) => (
                                                    <option key={session.id} value={session.id}>
                                                        {session.title || "Untitled Chat"}
                                                    </option>
                                                ))}
                                            </select>
                                            {sessionsLoading && (
                                                <p className="text-[10px] text-gray-500 mt-1">Loading sessions...</p>
                                            )}
                                        </div>
                                        <div>
                                            <label className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                                                Min Severity
                                            </label>
                                            <select
                                                value={form.agent_min_severity}
                                                onChange={(e) =>
                                                    setForm({ ...form, agent_min_severity: e.target.value })
                                                }
                                                className="mt-1 w-full bg-gray-900 border border-gray-800 rounded-xl px-3 py-2 text-sm text-white"
                                            >
                                                <option value="warn">warn</option>
                                                <option value="critical">critical</option>
                                            </select>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="flex justify-end gap-2 mt-6">
                            <button
                                onClick={() => setIsCreateOpen(false)}
                                className="px-4 py-2 rounded-xl border border-gray-800 text-gray-400 hover:text-white"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={() => handleCreate().catch((e) => alert(String(e)))}
                                className="px-4 py-2 rounded-xl bg-emerald-600 text-white font-bold"
                            >
                                Create
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
