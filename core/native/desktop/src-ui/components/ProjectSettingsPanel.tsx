import React, { useEffect, useState } from "react"
import { Bot, Save, Edit3, X } from "lucide-react"
import { apiFetch } from "../lib/api"
import MarkdownRenderer from "./MarkdownRenderer"

interface AgentRecord {
    id: string
    display_name: string
    description: string | null
    skill_ids: string[]
}

interface Props {
    projectId: string
}

export default function ProjectSettingsPanel({ projectId }: Props) {
    const [prompt, setPrompt] = useState("")
    const [initialPrompt, setInitialPrompt] = useState("")
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [saveStatus, setSaveStatus] = useState("")
    const [isEditing, setIsEditing] = useState(false)

    const [allAgents, setAllAgents] = useState<AgentRecord[]>([])
    const [enabledAgentIds, setEnabledAgentIds] = useState<Set<string>>(new Set())
    const [defaultAgentId, setDefaultAgentId] = useState("")
    const [agentSaving, setAgentSaving] = useState(false)
    const [agentSaveStatus, setAgentSaveStatus] = useState("")

    useEffect(() => {
        loadData()
    }, [projectId])

    const loadData = async () => {
        setLoading(true)
        try {
            const [promptRes, agentsRes, enabledRes] = await Promise.all([
                apiFetch(`/api/agents/project/${projectId}/prompt`),
                apiFetch("/api/agents/registry"),
                apiFetch(`/api/agents/project/${projectId}/enabled-agents`),
            ])
            const promptData = await promptRes.json()
            setPrompt(promptData.content || "")
            setInitialPrompt(promptData.content || "")

            const agentsData = await agentsRes.json()
            setAllAgents(agentsData.agents ?? [])

            const enabledData = await enabledRes.json()
            setEnabledAgentIds(new Set(enabledData.enabled_agent_ids ?? []))
            setDefaultAgentId(enabledData.default_agent_id ?? "")
        } catch (e) {
            console.error("Failed to load project settings:", e)
        } finally {
            setLoading(false)
        }
    }

    const savePrompt = async () => {
        setSaving(true)
        setSaveStatus("")
        try {
            const res = await apiFetch(`/api/agents/project/${projectId}/prompt`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ content: prompt }),
            })
            if (res.ok) {
                setSaveStatus("✅ Saved")
                setInitialPrompt(prompt)
                setIsEditing(false)
                setTimeout(() => setSaveStatus(""), 3000)
            } else {
                setSaveStatus("❌ Failed")
            }
        } catch {
            setSaveStatus("❌ Failed")
        } finally {
            setSaving(false)
        }
    }

    const toggleAgent = (agentId: string) => {
        setEnabledAgentIds((prev) => {
            const next = new Set(prev)
            if (next.has(agentId)) {
                next.delete(agentId)
                if (defaultAgentId === agentId) setDefaultAgentId("")
            } else {
                next.add(agentId)
            }
            return next
        })
    }

    const saveAgentSettings = async () => {
        setAgentSaving(true)
        setAgentSaveStatus("")
        try {
            const res = await apiFetch(`/api/agents/project/${projectId}/enabled-agents`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    enabled_agent_ids: Array.from(enabledAgentIds),
                    default_agent_id: defaultAgentId || null,
                }),
            })
            if (res.ok) {
                setAgentSaveStatus("✅ Saved")
                setTimeout(() => setAgentSaveStatus(""), 3000)
            } else {
                const err = await res.json()
                setAgentSaveStatus(`❌ ${err.detail || "Failed"}`)
            }
        } catch {
            setAgentSaveStatus("❌ Failed")
        } finally {
            setAgentSaving(false)
        }
    }

    const agentSaveBlocked = !!defaultAgentId && !enabledAgentIds.has(defaultAgentId)

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin" />
            </div>
        )
    }

    return (
        <div className="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar space-y-6 pr-1">
            {/* System Instructions */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                        System Instructions
                    </span>
                    <div className="flex items-center gap-1">
                        {saveStatus && (
                            <span className="text-[10px] text-gray-400">{saveStatus}</span>
                        )}
                        {isEditing ? (
                            <>
                                <button
                                    onClick={() => { setPrompt(initialPrompt); setIsEditing(false) }}
                                    className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
                                    title="Cancel"
                                >
                                    <X size={13} />
                                </button>
                                <button
                                    onClick={savePrompt}
                                    disabled={saving}
                                    className="p-1.5 rounded-lg text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 transition-colors"
                                    title="Save"
                                >
                                    <Save size={13} />
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
                                title="Edit"
                            >
                                <Edit3 size={13} />
                            </button>
                        )}
                    </div>
                </div>

                {isEditing ? (
                    <textarea
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        className="w-full min-h-[160px] bg-gray-900/50 border border-gray-700 rounded-xl p-3 text-gray-200 font-mono text-xs focus:outline-none focus:border-cyan-500 transition-all resize-y"
                        placeholder="Enter system instructions for this project..."
                    />
                ) : (
                    <div className="bg-gray-900/30 border border-gray-800/50 rounded-xl p-3 min-h-[80px]">
                        {initialPrompt ? (
                            <div className="text-xs text-gray-300 leading-relaxed">
                                <MarkdownRenderer content={initialPrompt} nodeType="project" nodeName={projectId} projectId={projectId} />
                            </div>
                        ) : (
                            <p className="text-xs text-gray-600 italic">No custom instructions yet. Click edit to add.</p>
                        )}
                    </div>
                )}
            </div>

            {/* Agent Settings */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <Bot size={12} className="text-cyan-500" />
                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                        Agent Settings
                    </span>
                </div>

                {allAgents.length === 0 ? (
                    <p className="text-xs text-gray-600 italic">No agents defined yet.</p>
                ) : (
                    <div className="space-y-4">
                        {/* Enabled agents */}
                        <div className="space-y-1.5">
                            <p className="text-[10px] text-gray-600 uppercase tracking-wider font-medium">Enabled</p>
                            {allAgents.map((agent) => {
                                const enabled = enabledAgentIds.has(agent.id)
                                return (
                                    <label
                                        key={agent.id}
                                        className={`flex items-start gap-2.5 p-2.5 rounded-xl cursor-pointer border transition-colors ${enabled ? "border-cyan-500/30 bg-cyan-500/5" : "border-gray-800 hover:border-gray-700"}`}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={enabled}
                                            onChange={() => toggleAgent(agent.id)}
                                            className="mt-0.5 accent-cyan-500"
                                        />
                                        <div className="min-w-0">
                                            <div className="text-xs font-medium text-white">{agent.display_name}</div>
                                            {agent.description && (
                                                <div className="text-[10px] text-gray-500 mt-0.5">{agent.description}</div>
                                            )}
                                            {agent.skill_ids.length > 0 && (
                                                <div className="flex flex-wrap gap-1 mt-1">
                                                    {agent.skill_ids.map((s) => (
                                                        <span key={s} className="px-1.5 py-0 bg-gray-800 text-gray-500 rounded text-[9px]">{s}</span>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    </label>
                                )
                            })}
                        </div>

                        {/* Default agent */}
                        <div className="space-y-1.5">
                            <p className="text-[10px] text-gray-600 uppercase tracking-wider font-medium">Default Agent</p>
                            <select
                                value={defaultAgentId}
                                onChange={(e) => setDefaultAgentId(e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 transition-colors"
                            >
                                <option value="">— None (use all skills) —</option>
                                {allAgents
                                    .filter((a) => enabledAgentIds.has(a.id))
                                    .map((a) => (
                                        <option key={a.id} value={a.id}>{a.display_name}</option>
                                    ))}
                            </select>
                            {agentSaveBlocked && (
                                <p className="text-[10px] text-amber-400">⚠ Default agent is not enabled.</p>
                            )}
                        </div>

                        {/* Save */}
                        <div className="flex items-center gap-3">
                            <button
                                onClick={saveAgentSettings}
                                disabled={agentSaving || agentSaveBlocked}
                                className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-lg text-xs font-semibold transition-colors"
                            >
                                <Save size={12} />
                                {agentSaving ? "Saving..." : "Save Agents"}
                            </button>
                            {agentSaveStatus && (
                                <span className="text-[10px] text-gray-400">{agentSaveStatus}</span>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
