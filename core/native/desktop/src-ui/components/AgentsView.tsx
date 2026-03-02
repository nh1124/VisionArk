import React, { useState, useEffect, useRef } from "react"
import { apiFetch } from "../lib/api"
import {
    Bot, Plus, Pencil, Trash2, X, GitBranch, Check, Loader2,
    Package, Upload, RefreshCw, ChevronDown, ChevronRight,
    ToggleLeft, ToggleRight, AlertCircle, FolderOpen,
} from "lucide-react"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Skill {
    name: string
    description: string
    tools: string[]
    is_active?: boolean
}

interface AgentRecord {
    id: string
    display_name: string
    description: string | null
    skill_ids: string[]
    graph_id: string | null
    status: string
    created_at: string | null
    updated_at: string | null
}

interface ModuleTool {
    name: string
    description: string
    is_active: boolean
}

interface ModuleSkill {
    name: string
    description: string
    tools: string[]
    is_active: boolean
}

interface ModuleRecord {
    module_name: string
    tools: ModuleTool[]
    skills: ModuleSkill[]
    updated_at: string | null
    files?: Record<string, string>
}

// ---------------------------------------------------------------------------
// Agent Modal
// ---------------------------------------------------------------------------

function AgentModal({
    agent, skills, onClose, onSave,
}: {
    agent: AgentRecord | null
    skills: Skill[]
    onClose: () => void
    onSave: (data: { display_name: string; description: string; skill_ids: string[]; graph_id: null }) => Promise<void>
}) {
    const [displayName, setDisplayName] = useState(agent?.display_name ?? "")
    const [description, setDescription] = useState(agent?.description ?? "")
    const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set(agent?.skill_ids ?? []))
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState("")

    const toggleSkill = (name: string) => {
        setSelectedSkills(prev => {
            const next = new Set(prev)
            next.has(name) ? next.delete(name) : next.add(name)
            return next
        })
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!displayName.trim()) { setError("Display name is required."); return }
        setSaving(true); setError("")
        try {
            await onSave({ display_name: displayName.trim(), description: description.trim(), skill_ids: Array.from(selectedSkills), graph_id: null })
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Save failed")
        } finally {
            setSaving(false)
        }
    }

    return (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg mx-4 shadow-2xl max-h-[90vh] flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-gray-800 flex-shrink-0">
                    <h2 className="text-lg font-bold text-white">{agent ? "Edit Agent" : "New Agent"}</h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors"><X size={20} /></button>
                </div>
                <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto custom-scrollbar">
                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1">Display Name <span className="text-red-400">*</span></label>
                        <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors"
                            placeholder="e.g. Research Agent" />
                    </div>
                    <div>
                        <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
                        <textarea value={description} onChange={e => setDescription(e.target.value)} rows={2}
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-500 transition-colors resize-none"
                            placeholder="Short description" />
                    </div>
                    <div>
                        <div className="flex items-center gap-1.5 mb-1">
                            <GitBranch size={11} className="text-gray-500" />
                            <span className="text-xs font-medium text-gray-400">Graph</span>
                            <span className="text-[10px] text-amber-500/60 border border-amber-500/20 rounded px-1 ml-0.5">coming soon</span>
                        </div>
                        <div className="w-full bg-gray-800/50 border border-gray-700/50 rounded-lg px-3 py-2 text-sm text-gray-500 flex items-center justify-between cursor-not-allowed select-none">
                            <span>direct_assistant (Default)</span>
                            <span className="text-[10px] text-gray-600">locked</span>
                        </div>
                    </div>
                    <div>
                        <span className="text-xs font-medium text-gray-400 block mb-2">Skills</span>
                        <div className="space-y-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
                            {skills.map(skill => {
                                const checked = selectedSkills.has(skill.name)
                                return (
                                    <button key={skill.name} type="button" onClick={() => toggleSkill(skill.name)}
                                        className={`w-full flex items-start gap-3 p-2.5 rounded-lg text-left border transition-colors ${checked ? "border-cyan-500/50 bg-cyan-500/5" : "border-gray-700 hover:border-gray-600"}`}>
                                        <div className={`mt-0.5 w-4 h-4 flex-shrink-0 rounded border flex items-center justify-center transition-colors ${checked ? "bg-cyan-500 border-cyan-500" : "border-gray-600 bg-transparent"}`}>
                                            {checked && <Check size={10} className="text-white" />}
                                        </div>
                                        <div className="min-w-0">
                                            <span className="text-sm font-medium text-white">{skill.name}</span>
                                            {skill.description && <p className="text-xs text-gray-500 mt-0.5">{skill.description}</p>}
                                            {skill.tools?.length > 0 && <p className="text-[10px] text-gray-600 mt-0.5 truncate">{skill.tools.join(", ")}</p>}
                                        </div>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                    {error && <p className="text-sm text-red-400">{error}</p>}
                    <div className="flex justify-end gap-2 pt-2">
                        <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">Cancel</button>
                        <button type="submit" disabled={saving} className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 text-white rounded-lg text-sm font-semibold transition-colors">
                            {saving ? "Saving..." : "Save"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Module Modal
// ---------------------------------------------------------------------------

const DEFAULT_INIT = `from va_sdk import BaseTool, IntegrationContext, ToolResult
from domains.orchestration2.engine.models.skill import SkillDef

# Optional: import from sibling files
# from .tools import MyTool
# from .skills import SKILL_DEFS

def get_tools(user_id: str, db):
    return []  # list of BaseTool instances

def get_skill_defs():
    return []  # list of SkillDef instances
`

function ModuleModal({
    existing, onClose, onSave,
}: {
    existing: ModuleRecord | null
    onClose: () => void
    onSave: (moduleName: string, files: Record<string, string>) => Promise<void>
}) {
    const isCreate = existing === null
    // "pick" = drop zone (create only); "edit" = file editor
    const [phase, setPhase] = useState<"pick" | "edit">(isCreate ? "pick" : "edit")
    const [moduleName, setModuleName] = useState(existing?.module_name ?? "")
    const [files, setFiles] = useState<Record<string, string>>(existing?.files ?? {})
    const [activeFile, setActiveFile] = useState("__init__.py")
    const [dragOver, setDragOver] = useState(false)
    const [newFileName, setNewFileName] = useState("")
    const [addingFile, setAddingFile] = useState(false)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState("")
    const folderInputRef = useRef<HTMLInputElement>(null)

    useEffect(() => {
        if (existing?.files) { setFiles(existing.files); setActiveFile("__init__.py") }
    }, [existing])

    const applyFolder = (folderName: string, loaded: Record<string, string>) => {
        if (!loaded["__init__.py"]) { setError("Folder must contain __init__.py"); return }
        setFiles(loaded)
        setActiveFile("__init__.py")
        if (isCreate) setModuleName(folderName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""))
        setError("")
        setPhase("edit")
    }

    const handleFolderInput = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const fileList = e.target.files
        if (!fileList || fileList.length === 0) return
        const result: Record<string, string> = {}
        let dirName = ""
        for (const file of Array.from(fileList)) {
            const relPath = (file as File & { webkitRelativePath: string }).webkitRelativePath
            const parts = relPath.split("/")
            if (!dirName && parts[0]) dirName = parts[0]
            if (parts.length !== 2 || !parts[1].endsWith(".py")) continue
            result[parts[1]] = await file.text()
        }
        e.target.value = ""
        applyFolder(dirName, result)
    }

    const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragOver(true) }
    const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setDragOver(false) }
    const handleDrop = async (e: React.DragEvent) => {
        e.preventDefault()
        setDragOver(false)
        const items = Array.from(e.dataTransfer.items)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const dirItem = items.find(i => i.kind === "file" && (i as any).webkitGetAsEntry?.()?.isDirectory)
        if (!dirItem) { setError("Please drop a folder (not individual files)"); return }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const entry = (dirItem as any).webkitGetAsEntry() as FileSystemDirectoryEntry
        try {
            const result = await new Promise<Record<string, string>>((resolve, reject) => {
                const loaded: Record<string, string> = {}
                entry.createReader().readEntries(entries => {
                    const pyEntries = entries.filter(
                        en => en.isFile && en.name.endsWith(".py")
                    ) as FileSystemFileEntry[]
                    if (!pyEntries.length) { resolve(loaded); return }
                    let remaining = pyEntries.length
                    pyEntries.forEach(fe => fe.file(async f => {
                        loaded[fe.name] = await f.text()
                        if (--remaining === 0) resolve(loaded)
                    }, reject))
                }, reject)
            })
            applyFolder(entry.name, result)
        } catch {
            setError("Failed to read folder contents")
        }
    }

    const fileList = ["__init__.py", ...Object.keys(files).filter(f => f !== "__init__.py").sort()]

    const handleAddFile = () => {
        const name = newFileName.trim()
        if (!name.endsWith(".py")) { setError("Filename must end with .py"); return }
        if (name === "__init__.py") { setError("__init__.py already exists"); return }
        if (!/^[a-zA-Z0-9_][a-zA-Z0-9_.]*\.py$/.test(name)) { setError("Invalid filename"); return }
        setFiles(prev => ({ ...prev, [name]: `# ${name}\n` }))
        setActiveFile(name); setNewFileName(""); setAddingFile(false); setError("")
    }

    const handleDeleteFile = (name: string) => {
        if (name === "__init__.py") return
        const next = { ...files }; delete next[name]
        setFiles(next); setActiveFile("__init__.py")
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        if (!moduleName.trim()) { setError("Module name is required."); return }
        setSaving(true); setError("")
        try { await onSave(moduleName.trim(), files) }
        catch (err: unknown) { setError(err instanceof Error ? err.message : "Save failed") }
        finally { setSaving(false) }
    }

    return (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl mx-4 shadow-2xl max-h-[92vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-gray-800 flex-shrink-0">
                    <div className="flex items-center gap-2">
                        <Package size={18} className="text-cyan-400" />
                        <h2 className="text-lg font-bold text-white">
                            {isCreate ? "Upload Module" : `Edit: ${existing.module_name}`}
                        </h2>
                    </div>
                    <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors"><X size={20} /></button>
                </div>

                {/* ---- Pick phase (create only) ---- */}
                {phase === "pick" && (
                    <div className="p-6 flex flex-col gap-4">
                        <div
                            onDragOver={handleDragOver}
                            onDragLeave={handleDragLeave}
                            onDrop={handleDrop}
                            onClick={() => folderInputRef.current?.click()}
                            className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors select-none ${
                                dragOver
                                    ? "border-cyan-500 bg-cyan-500/5"
                                    : "border-gray-700 hover:border-gray-600 hover:bg-gray-800/30"
                            }`}
                        >
                            <FolderOpen size={40} className={`mx-auto mb-3 ${dragOver ? "text-cyan-400" : "text-gray-600"}`} />
                            <p className="text-gray-300 font-medium">Drop your module folder here</p>
                            <p className="text-gray-500 text-sm mt-1">or click to browse</p>
                            <p className="text-gray-600 text-xs mt-3">Must contain __init__.py · Only .py files are imported</p>
                        </div>
                        <p className="text-center text-xs text-gray-600">
                            or{" "}
                            <button
                                type="button"
                                onClick={() => { setFiles({ "__init__.py": DEFAULT_INIT }); setPhase("edit") }}
                                className="text-gray-400 hover:text-cyan-400 underline transition-colors"
                            >
                                create from scratch
                            </button>
                        </p>
                        {error && (
                            <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                                <AlertCircle size={14} />{error}
                            </div>
                        )}
                        <div className="flex justify-end">
                            <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">Cancel</button>
                        </div>
                    </div>
                )}

                {/* ---- Edit phase: file editor ---- */}
                {phase === "edit" && (
                    <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0 overflow-hidden">
                        <div className="p-5 space-y-4 flex-1 min-h-0 overflow-y-auto custom-scrollbar">
                            {isCreate && (
                                <div>
                                    <label className="block text-xs font-medium text-gray-400 mb-1">Module Name <span className="text-red-400">*</span></label>
                                    <input type="text" value={moduleName} onChange={e => setModuleName(e.target.value)}
                                        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                                        placeholder="e.g. my_tools" />
                                </div>
                            )}
                            {/* File tabs */}
                            <div>
                                <div className="flex items-center gap-1 flex-wrap">
                                    {fileList.map(name => (
                                        <div key={name} className="flex items-center">
                                            <button type="button" onClick={() => setActiveFile(name)}
                                                className={`px-3 py-1 text-xs rounded-t-lg font-mono transition-colors ${activeFile === name ? "bg-gray-800 text-cyan-400 border border-b-0 border-gray-700" : "text-gray-500 hover:text-gray-300"}`}>
                                                {name}
                                            </button>
                                            {name !== "__init__.py" && (
                                                <button type="button" onClick={() => handleDeleteFile(name)} className="p-0.5 text-gray-600 hover:text-red-400 transition-colors">
                                                    <X size={10} />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                    {addingFile ? (
                                        <div className="flex items-center gap-1">
                                            <input autoFocus value={newFileName} onChange={e => setNewFileName(e.target.value)}
                                                onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); handleAddFile() } if (e.key === "Escape") setAddingFile(false) }}
                                                className="px-2 py-1 text-xs bg-gray-800 border border-cyan-500/50 rounded text-white font-mono w-32 outline-none" placeholder="utils.py" />
                                            <button type="button" onClick={handleAddFile} className="text-cyan-400 text-xs">Add</button>
                                            <button type="button" onClick={() => { setAddingFile(false); setNewFileName("") }} className="text-gray-500 text-xs">Cancel</button>
                                        </div>
                                    ) : (
                                        <button type="button" onClick={() => setAddingFile(true)} className="px-2 py-1 text-xs text-gray-500 hover:text-cyan-400 flex items-center gap-1">
                                            <Plus size={11} /> Add File
                                        </button>
                                    )}
                                    {/* Replace / Change folder */}
                                    <button type="button" onClick={() => folderInputRef.current?.click()}
                                        className="ml-auto flex items-center gap-1 px-2 py-1 text-xs text-gray-500 hover:text-cyan-400 transition-colors">
                                        <FolderOpen size={11} />
                                        {isCreate ? "Change folder" : "Replace folder"}
                                    </button>
                                </div>
                                <textarea
                                    value={files[activeFile] ?? ""}
                                    onChange={e => setFiles(prev => ({ ...prev, [activeFile]: e.target.value }))}
                                    className="w-full h-64 bg-gray-800 border border-gray-700 rounded-b-lg rounded-tr-lg px-3 py-3 text-white text-xs font-mono focus:outline-none focus:border-cyan-500/50 resize-none custom-scrollbar"
                                    spellCheck={false}
                                />
                            </div>
                        </div>

                        <div className="px-5 pb-5 flex-shrink-0 space-y-3">
                            {error && (
                                <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                                    <AlertCircle size={14} />{error}
                                </div>
                            )}
                            <div className="flex justify-end gap-2">
                                <button type="button" onClick={onClose} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors">Cancel</button>
                                <button type="submit" disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 text-white rounded-lg text-sm font-semibold transition-colors">
                                    <Upload size={14} />
                                    {saving ? "Uploading..." : isCreate ? "Upload" : "Update"}
                                </button>
                            </div>
                        </div>
                    </form>
                )}

                {/* Hidden folder input */}
                <input
                    ref={folderInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={handleFolderInput}
                    {...({ webkitdirectory: "" } as Record<string, unknown>)}
                />
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Module Card
// ---------------------------------------------------------------------------

function ModuleCard({
    module, onEdit, onDelete, onToggleTool, onToggleSkill,
}: {
    module: ModuleRecord
    onEdit: (m: ModuleRecord) => void
    onDelete: (name: string) => void
    onToggleTool: (toolName: string, active: boolean) => void
    onToggleSkill: (skillName: string, active: boolean) => void
}) {
    const [expanded, setExpanded] = useState(false)

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden hover:border-gray-700 transition-colors">
            <div className="flex items-center justify-between p-4">
                <button className="flex items-center gap-2 min-w-0 flex-1 text-left" onClick={() => setExpanded(e => !e)}>
                    {expanded ? <ChevronDown size={14} className="text-gray-500 flex-shrink-0" /> : <ChevronRight size={14} className="text-gray-500 flex-shrink-0" />}
                    <Package size={16} className="text-cyan-400 flex-shrink-0" />
                    <span className="font-mono font-semibold text-white truncate">{module.module_name}</span>
                </button>
                <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                    <span className="text-[10px] text-gray-600 mr-2">{module.tools.length}T · {module.skills.length}S</span>
                    <button onClick={() => onEdit(module)} className="p-1.5 text-gray-500 hover:text-cyan-400 hover:bg-gray-800 rounded-lg transition-colors"><Pencil size={13} /></button>
                    <button onClick={() => onDelete(module.module_name)} className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors"><Trash2 size={13} /></button>
                </div>
            </div>

            {expanded && (
                <div className="border-t border-gray-800 px-4 pb-4 pt-3 space-y-3">
                    {module.tools.length > 0 && (
                        <div>
                            <p className="text-[10px] uppercase tracking-widest text-gray-600 font-semibold mb-1.5">Tools</p>
                            <div className="space-y-1">
                                {module.tools.map(tool => (
                                    <div key={tool.name} className="flex items-center justify-between gap-2">
                                        <div className="min-w-0">
                                            <span className="text-xs font-mono text-gray-300">{tool.name}</span>
                                            {tool.description && <span className="text-xs text-gray-600 ml-2">{tool.description}</span>}
                                        </div>
                                        <button onClick={() => onToggleTool(tool.name, !tool.is_active)} className="flex-shrink-0">
                                            {tool.is_active ? <ToggleRight size={18} className="text-cyan-400" /> : <ToggleLeft size={18} className="text-gray-600" />}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    {module.skills.length > 0 && (
                        <div>
                            <p className="text-[10px] uppercase tracking-widest text-gray-600 font-semibold mb-1.5">Skills</p>
                            <div className="space-y-1">
                                {module.skills.map(skill => (
                                    <div key={skill.name} className="flex items-center justify-between gap-2">
                                        <div className="min-w-0">
                                            <span className="text-xs font-mono text-gray-300">{skill.name}</span>
                                            {skill.tools.length > 0 && <span className="text-[10px] text-gray-600 ml-2">[{skill.tools.join(", ")}]</span>}
                                        </div>
                                        <button onClick={() => onToggleSkill(skill.name, !skill.is_active)} className="flex-shrink-0">
                                            {skill.is_active ? <ToggleRight size={18} className="text-cyan-400" /> : <ToggleLeft size={18} className="text-gray-600" />}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    {module.updated_at && (
                        <p className="text-[10px] text-gray-700">Updated: {new Date(module.updated_at).toLocaleString()}</p>
                    )}
                </div>
            )}
        </div>
    )
}

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

type Tab = "agents" | "modules"

export default function AgentsView() {
    const [tab, setTab] = useState<Tab>("agents")

    // Agent state
    const [agents, setAgents] = useState<AgentRecord[]>([])
    const [skills, setSkills] = useState<Skill[]>([])
    const [agentsLoading, setAgentsLoading] = useState(true)
    const [agentModalOpen, setAgentModalOpen] = useState(false)
    const [editingAgent, setEditingAgent] = useState<AgentRecord | null>(null)
    const [deletingAgentId, setDeletingAgentId] = useState<string | null>(null)
    const [deleteConfirmAgent, setDeleteConfirmAgent] = useState<AgentRecord | null>(null)

    // Module state
    const [modules, setModules] = useState<ModuleRecord[]>([])
    const [modulesLoading, setModulesLoading] = useState(false)
    const [moduleModalOpen, setModuleModalOpen] = useState(false)
    const [editingModule, setEditingModule] = useState<ModuleRecord | null>(null)
    const [deleteConfirmModule, setDeleteConfirmModule] = useState<string | null>(null)

    useEffect(() => { loadAgents() }, [])
    useEffect(() => { if (tab === "modules") loadModules() }, [tab])

    // ---- Agent ----

    const loadAgents = async () => {
        setAgentsLoading(true)
        try {
            const [agentsRes, skillsRes] = await Promise.all([
                apiFetch("/api/agents/registry"),
                apiFetch("/api/agents/skills"),
            ])
            const agentsData = await agentsRes.json()
            const skillsData = await skillsRes.json()
            setAgents(agentsData.agents ?? [])
            setSkills(skillsData.skills ?? [])
        } catch (err) { console.error("Failed to load agents:", err) }
        finally { setAgentsLoading(false) }
    }

    const handleSaveAgent = async (data: { display_name: string; description: string; skill_ids: string[]; graph_id: null }) => {
        if (editingAgent) {
            const res = await apiFetch(`/api/agents/registry/${editingAgent.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
            if (!res.ok) throw new Error("Failed to update agent")
        } else {
            const res = await apiFetch("/api/agents/registry", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
            if (!res.ok) throw new Error("Failed to create agent")
        }
        setAgentModalOpen(false); setEditingAgent(null)
        await loadAgents()
    }

    const handleDeleteAgent = async (agent: AgentRecord) => {
        setDeletingAgentId(agent.id)
        try {
            await apiFetch(`/api/agents/registry/${agent.id}`, { method: "DELETE" })
            await loadAgents()
        } catch (err) { console.error("Failed to delete agent:", err) }
        finally { setDeletingAgentId(null); setDeleteConfirmAgent(null) }
    }

    // ---- Module ----

    const loadModules = async () => {
        setModulesLoading(true)
        try {
            const res = await apiFetch("/api/definitions/modules")
            const data = await res.json()
            setModules(data)
        } catch (err) { console.error("Failed to load modules:", err) }
        finally { setModulesLoading(false) }
    }

    const openEditModule = async (m: ModuleRecord) => {
        try {
            const res = await apiFetch(`/api/definitions/modules/${m.module_name}`)
            const detail = await res.json()
            setEditingModule(detail)
        } catch { setEditingModule(m) }
        setModuleModalOpen(true)
    }

    const handleSaveModule = async (moduleName: string, files: Record<string, string>) => {
        if (editingModule) {
            const res = await apiFetch(`/api/definitions/modules/${editingModule.module_name}`, {
                method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ files }),
            })
            if (!res.ok) { const e = await res.json(); throw new Error(e.detail ?? "Update failed") }
        } else {
            const res = await apiFetch("/api/definitions/modules", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ module_name: moduleName, files }),
            })
            if (!res.ok) { const e = await res.json(); throw new Error(e.detail ?? "Upload failed") }
        }
        setModuleModalOpen(false); setEditingModule(null)
        await loadModules()
        await loadAgents()
    }

    const handleDeleteModule = async (name: string) => {
        try {
            await apiFetch(`/api/definitions/modules/${name}`, { method: "DELETE" })
            await loadModules(); await loadAgents()
        } catch (err) { console.error("Failed to delete module:", err) }
        finally { setDeleteConfirmModule(null) }
    }

    const handleToggleTool = async (moduleName: string, toolName: string, active: boolean) => {
        await apiFetch(`/api/definitions/tools/${toolName}`, {
            method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: active }),
        })
        setModules(prev => prev.map(m =>
            m.module_name === moduleName ? { ...m, tools: m.tools.map(t => t.name === toolName ? { ...t, is_active: active } : t) } : m
        ))
    }

    const handleToggleSkill = async (moduleName: string, skillName: string, active: boolean) => {
        await apiFetch(`/api/definitions/skills/${skillName}`, {
            method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: active }),
        })
        setModules(prev => prev.map(m =>
            m.module_name === moduleName ? { ...m, skills: m.skills.map(s => s.name === skillName ? { ...s, is_active: active } : s) } : m
        ))
    }

    const graphName = (id: string | null) => id ?? "direct_assistant"

    return (
        <div className="flex flex-col h-full bg-[#030712] text-white">
            {/* Header */}
            <div className="bg-gray-900/50 border-b border-gray-800 px-8 py-5 flex-shrink-0">
                <div className="flex items-center justify-between max-w-7xl mx-auto">
                    <div className="flex items-center gap-3">
                        <Bot size={24} className="text-cyan-400" />
                        <div>
                            <h1 className="text-2xl font-bold text-white">Agents</h1>
                            <p className="text-gray-400 text-sm mt-0.5">Manage agents and custom tool modules</p>
                        </div>
                    </div>
                    {tab === "agents" ? (
                        <button onClick={() => { setEditingAgent(null); setAgentModalOpen(true) }}
                            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors">
                            <Plus size={16} /> New Agent
                        </button>
                    ) : (
                        <button onClick={() => { setEditingModule(null); setModuleModalOpen(true) }}
                            className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors">
                            <Upload size={16} /> Upload Module
                        </button>
                    )}
                </div>

                {/* Tab switcher */}
                <div className="flex gap-1 mt-4 border-b border-gray-800 -mb-5 max-w-7xl mx-auto">
                    {(["agents", "modules"] as Tab[]).map(t => (
                        <button key={t} onClick={() => setTab(t)}
                            className={`px-4 py-2 text-sm font-semibold capitalize transition-colors border-b-2 ${tab === t ? "border-cyan-500 text-cyan-400" : "border-transparent text-gray-500 hover:text-gray-300"}`}>
                            {t === "agents" ? "Agents" : "Modules"}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
                <div className="max-w-7xl mx-auto p-8">

                    {/* ---- Agents ---- */}
                    {tab === "agents" && (
                        agentsLoading ? (
                            <div className="flex items-center justify-center h-48 gap-3">
                                <Loader2 size={32} className="text-cyan-500 animate-spin" />
                                <p className="text-gray-400">Loading agents...</p>
                            </div>
                        ) : agents.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
                                <Bot size={48} className="text-gray-700" />
                                <p className="text-gray-500 text-lg">No agents yet</p>
                                <p className="text-gray-600 text-sm max-w-xs">Create your first agent to assign skills and reuse it across projects.</p>
                                <button onClick={() => { setEditingAgent(null); setAgentModalOpen(true) }}
                                    className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors mt-2">
                                    <Plus size={16} /> New Agent
                                </button>
                            </div>
                        ) : (
                            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                                {agents.map(agent => (
                                    <div key={agent.id} className="bg-gray-900 border border-gray-800 rounded-2xl p-5 flex flex-col gap-3 hover:border-gray-700 transition-colors">
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="flex items-center gap-2 min-w-0">
                                                <Bot size={18} className="text-cyan-400 flex-shrink-0" />
                                                <span className="font-semibold text-white truncate">{agent.display_name}</span>
                                            </div>
                                            <div className="flex items-center gap-1 flex-shrink-0">
                                                <button onClick={() => { setEditingAgent(agent); setAgentModalOpen(true) }} className="p-1.5 text-gray-500 hover:text-cyan-400 hover:bg-gray-800 rounded-lg transition-colors"><Pencil size={14} /></button>
                                                <button onClick={() => setDeleteConfirmAgent(agent)} disabled={deletingAgentId === agent.id} className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded-lg transition-colors">
                                                    {deletingAgentId === agent.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                                                </button>
                                            </div>
                                        </div>
                                        {agent.description && <p className="text-sm text-gray-400 leading-snug">{agent.description}</p>}
                                        <div className="flex items-center gap-1.5">
                                            <GitBranch size={11} className="text-gray-600" />
                                            <span className="text-[11px] text-gray-500">{graphName(agent.graph_id)}</span>
                                        </div>
                                        {agent.skill_ids.length > 0 ? (
                                            <div className="flex flex-wrap gap-1.5">
                                                {agent.skill_ids.map(s => <span key={s} className="px-2 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-full text-xs font-medium">{s}</span>)}
                                            </div>
                                        ) : (
                                            <p className="text-xs text-gray-600 italic">No skills assigned — all skills active</p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )
                    )}

                    {/* ---- Modules ---- */}
                    {tab === "modules" && (
                        modulesLoading ? (
                            <div className="flex items-center justify-center h-48 gap-3">
                                <Loader2 size={32} className="text-cyan-500 animate-spin" />
                                <p className="text-gray-400">Loading modules...</p>
                            </div>
                        ) : modules.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
                                <Package size={48} className="text-gray-700" />
                                <p className="text-gray-500 text-lg">No modules yet</p>
                                <p className="text-gray-600 text-sm max-w-sm">Upload a Python module to add custom tools and skills. See the SDK README for how to write one.</p>
                                <button onClick={() => { setEditingModule(null); setModuleModalOpen(true) }}
                                    className="flex items-center gap-2 px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded-lg text-sm font-semibold transition-colors mt-2">
                                    <Upload size={16} /> Upload Module
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-3 max-w-3xl">
                                <div className="flex items-center justify-between mb-4">
                                    <p className="text-sm text-gray-500">{modules.length} module{modules.length !== 1 ? "s" : ""}</p>
                                    <button onClick={loadModules} className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors">
                                        <RefreshCw size={12} /> Refresh
                                    </button>
                                </div>
                                {modules.map(m => (
                                    <ModuleCard key={m.module_name} module={m}
                                        onEdit={openEditModule}
                                        onDelete={name => setDeleteConfirmModule(name)}
                                        onToggleTool={(toolName, active) => handleToggleTool(m.module_name, toolName, active)}
                                        onToggleSkill={(skillName, active) => handleToggleSkill(m.module_name, skillName, active)}
                                    />
                                ))}
                            </div>
                        )
                    )}
                </div>
            </div>

            {/* Agent Modal */}
            {agentModalOpen && (
                <AgentModal agent={editingAgent} skills={skills}
                    onClose={() => { setAgentModalOpen(false); setEditingAgent(null) }}
                    onSave={handleSaveAgent} />
            )}

            {/* Module Modal */}
            {moduleModalOpen && (
                <ModuleModal existing={editingModule}
                    onClose={() => { setModuleModalOpen(false); setEditingModule(null) }}
                    onSave={handleSaveModule} />
            )}

            {/* Delete Agent Confirm */}
            {deleteConfirmAgent && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6">
                        <h3 className="text-base font-bold text-white mb-1.5">Delete agent?</h3>
                        <p className="text-gray-400 text-sm mb-5 font-mono">{deleteConfirmAgent.display_name}</p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirmAgent(null)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={() => handleDeleteAgent(deleteConfirmAgent)} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Delete Module Confirm */}
            {deleteConfirmModule && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-gray-900 border border-red-900/40 w-full max-w-sm rounded-2xl shadow-2xl p-6">
                        <h3 className="text-base font-bold text-white mb-1.5">Delete module?</h3>
                        <p className="text-gray-400 text-sm mb-1">All tools and skills from this module will be removed.</p>
                        <p className="text-gray-300 text-sm font-mono mb-5">{deleteConfirmModule}</p>
                        <div className="flex gap-3 justify-end">
                            <button onClick={() => setDeleteConfirmModule(null)} className="px-4 py-1.5 rounded-lg text-sm text-gray-400 hover:text-white">Cancel</button>
                            <button onClick={() => handleDeleteModule(deleteConfirmModule)} className="px-5 py-1.5 rounded-lg text-sm bg-red-500 hover:bg-red-400 text-white font-bold">Delete</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
