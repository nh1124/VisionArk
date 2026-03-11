import React, { useEffect, useState } from "react"
import { invoke, isTauri } from "@tauri-apps/api/core"
import { apiFetch, apiJson, getApiBase, setApiBase, initApiBase } from "../lib/api"
import { User, Cpu, Server, Globe, Link, Database, Key, FileText, ChevronDown, ChevronRight, Puzzle } from "lucide-react"

const IS_TAURI = isTauri()

type Tab = "general" | "ai" | "services" | "integrations" | "account"

interface GeneralSettings {
  language: string
  timezone: string
  location: string
}

interface AIConfig {
  gemini_api_key: string
  openai_api_key: string
  anthropic_api_key: string
  default_model: string
}

interface Service {
  id: number
  service_name: string
  base_url: string
  is_active: boolean
  health_status?: string
}

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "general", label: "General", icon: Globe },
  { id: "ai", label: "AI", icon: Cpu },
  { id: "services", label: "Services", icon: Server },
  { id: "integrations", label: "Integrations", icon: Puzzle },
  { id: "account", label: "Account", icon: User },
]

// Manifest shape returned by GET /api/settings/integrations/hub
interface ManifestItem {
  id: string
  name: string
  description: string
  icon: string
  color?: string
  category?: string
  authType?: string
  config_fields?: Array<{
    key: string
    label: string
    type: string
    description?: string
    default?: any
    options?: string[]
  }>
  setup_instructions?: Array<{ step: number; title: string; content: string }>
}

const IANA_TIMEZONES = typeof Intl !== "undefined"
  ? ["UTC", ...Intl.supportedValuesOf("timeZone")]
  : ["UTC"]

export default function SettingsView() {
  const [tab, setTab] = useState<Tab>("general")
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  // General
  const [general, setGeneral] = useState<GeneralSettings>({
    language: "en",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    location: "",
  })

  // AI
  const [ai, setAI] = useState<AIConfig>({
    gemini_api_key: "",
    openai_api_key: "",
    anthropic_api_key: "",
    default_model: "",
  })

  // Services
  const [services, setServices] = useState<Service[]>([])

  // Integrations hub (dynamic, manifest-driven)
  const [hubCatalog, setHubCatalog] = useState<ManifestItem[]>([])
  const [serviceMap, setServiceMap] = useState<Record<string, Service>>({})
  const [integrationExpanded, setIntegrationExpanded] = useState<Record<string, boolean>>({})
  const [integrationSaving, setIntegrationSaving] = useState<Record<string, boolean>>({})
  // formValues[service_id][field_key] = value
  const [formValues, setFormValues] = useState<Record<string, Record<string, any>>>({})
  // api key inputs kept separate (never pre-filled)
  const [apiKeyInputs, setApiKeyInputs] = useState<Record<string, string>>({})
  const [categoryFilter, setCategoryFilter] = useState<string>("all")

  // Connection (server URL)
  const [serverUrl, setServerUrl] = useState("")
  const [configFilePath, setConfigFilePath] = useState<string | null>(null)
  const [runInBackground, setRunInBackground] = useState(false)

  // Account
  const [profile, setProfile] = useState({ username: "", email: "" })
  const [passForm, setPassForm] = useState({ current: "", next: "", confirm: "" })

  // ── Load ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    // Ensure the latest persisted URL is reflected (Tauri reads config file)
    initApiBase().then((url) => setServerUrl(url))
    // Fetch the actual config file path for display
    if (IS_TAURI) {
      invoke<string>("get_config_file_path")
        .then(setConfigFilePath)
        .catch(() => setConfigFilePath(null))

      invoke<any>("read_app_config")
        .then((cfg) => {
          if (cfg && typeof cfg.run_daemon_in_background === "boolean") {
            setRunInBackground(cfg.run_daemon_in_background)
          }
        })
        .catch((e) => console.error(e))
    }
  }, [])

  useEffect(() => {
    apiJson<ManifestItem[]>("/api/settings/integrations/hub")
      .then((catalog) => setHubCatalog(catalog || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    apiJson<any>("/api/settings")
      .then((data) => {
        const g = data.general_settings || {}
        setGeneral({
          language: g.language || "en",
          timezone: g.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          location: g.location || "",
        })
        const a = data.ai_config || {}
        setAI({
          gemini_api_key: a.gemini_api_key ? "********" : "",
          openai_api_key: a.openai_api_key ? "********" : "",
          anthropic_api_key: a.anthropic_api_key ? "********" : "",
          default_model: a.default_model || "",
        })
        const svcList: Service[] = data.services || []
        setServices(svcList)
        if (data.profile) setProfile({ username: data.profile.username, email: data.profile.email || "" })

        // Build a map for quick lookup in the integrations tab
        const map: Record<string, Service> = {}
        for (const s of svcList) map[s.service_name] = s
        setServiceMap(map)

        // Pre-populate form values from existing service configs
        setFormValues((prev) => {
          const next = { ...prev }
          for (const s of svcList) {
            const cfg: Record<string, any> = (s as any).config || {}
            next[s.service_name] = { ...cfg }
          }
          return next
        })
      })
      .catch(() => { })
  }, [])

  function showMsg(type: "success" | "error", text: string) {
    setMsg({ type, text })
    setTimeout(() => setMsg(null), 3500)
  }

  // ── Save Server URL ──────────────────────────────────────────────────────

  async function saveServerUrl() {
    if (!serverUrl.trim()) return
    await setApiBase(serverUrl) // also auto-syncs bridge URL
    setServerUrl(getApiBase()) // reflect normalization

    if (IS_TAURI) {
      // Sync runInBackground correctly
      await invoke("write_app_config", { config: { api_url: getApiBase(), run_daemon_in_background: runInBackground } })
    }
    showMsg("success", `Server URL updated to ${getApiBase()}`)
  }

  async function toggleRunInBackground() {
    if (!IS_TAURI) return
    const nextVal = !runInBackground
    setRunInBackground(nextVal)
    try {
      await invoke("write_app_config", { config: { api_url: getApiBase(), run_daemon_in_background: nextVal } })
      showMsg("success", nextVal ? "Background execution enabled" : "Background execution disabled")
    } catch (e: any) {
      showMsg("error", "Failed to update background setting")
      setRunInBackground(!nextVal) // revert on error
    }
  }

  // ── Save General ─────────────────────────────────────────────────────────

  async function saveGeneral() {
    setSaving(true)
    try {
      await apiJson("/api/settings/general", {
        method: "PATCH",
        body: JSON.stringify(general),
      })
      showMsg("success", "General settings saved")
    } catch (e: any) {
      showMsg("error", e.message || "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  // ── Save AI ──────────────────────────────────────────────────────────────

  async function saveAI() {
    setSaving(true)
    try {
      const payload: Record<string, string> = {}
      if (ai.gemini_api_key && ai.gemini_api_key !== "********") payload.gemini_api_key = ai.gemini_api_key
      if (ai.openai_api_key && ai.openai_api_key !== "********") payload.openai_api_key = ai.openai_api_key
      if (ai.anthropic_api_key && ai.anthropic_api_key !== "********") payload.anthropic_api_key = ai.anthropic_api_key
      if (ai.default_model) payload.default_model = ai.default_model
      await apiJson("/api/settings/ai", { method: "PATCH", body: JSON.stringify(payload) })
      showMsg("success", "AI settings saved")
    } catch (e: any) {
      showMsg("error", e.message || "Failed to save")
    } finally {
      setSaving(false)
    }
  }

  // ── Save Service ─────────────────────────────────────────────────────────

  // ── Change Password ───────────────────────────────────────────────────────

  async function changePassword(e: React.FormEvent) {
    e.preventDefault()
    if (passForm.next !== passForm.confirm) { showMsg("error", "Passwords do not match"); return }
    if (passForm.next.length < 8) { showMsg("error", "Password must be at least 8 characters"); return }
    setSaving(true)
    try {
      await apiJson("/api/settings/account/password", {
        method: "POST",
        body: JSON.stringify({ current_password: passForm.current, new_password: passForm.next }),
      })
      showMsg("success", "Password changed")
      setPassForm({ current: "", next: "", confirm: "" })
    } catch (e: any) {
      showMsg("error", e.message || "Failed to change password")
    } finally {
      setSaving(false)
    }
  }

  // ── Integration helpers (manifest-driven) ────────────────────────────────

  function setFormField(id: string, key: string, value: any) {
    setFormValues((prev) => ({ ...prev, [id]: { ...prev[id], [key]: value } }))
  }

  async function toggleIntegrationActive(manifest: ManifestItem) {
    const current = serviceMap[manifest.id]
    const next_active = !(current?.is_active ?? false)
    // Optimistic update
    setServiceMap((prev) => ({
      ...prev,
      [manifest.id]: { ...(prev[manifest.id] ?? { id: 0, service_name: manifest.id, base_url: "local", is_active: false }), is_active: next_active },
    }))
    try {
      const updated = await apiJson<Service>("/api/settings/services", {
        method: "POST",
        body: JSON.stringify({ service_name: manifest.id, base_url: "local", is_active: next_active }),
      })
      setServiceMap((prev) => ({ ...prev, [manifest.id]: updated }))
    } catch (e: any) {
      // Revert
      setServiceMap((prev) => ({ ...prev, [manifest.id]: current }))
      showMsg("error", e.message || "Failed to update")
    }
  }

  async function saveIntegration(manifest: ManifestItem) {
    setIntegrationSaving((p) => ({ ...p, [manifest.id]: true }))
    try {
      const fields = formValues[manifest.id] || {}
      const config: Record<string, any> = {}
      for (const field of manifest.config_fields ?? []) {
        const val = fields[field.key]
        if (val !== undefined && val !== "") config[field.key] = val
      }
      const body: Record<string, any> = {
        service_name: manifest.id,
        base_url: fields._base_url || "local",
        config,
        is_active: serviceMap[manifest.id]?.is_active ?? false,
      }
      const apiKey = apiKeyInputs[manifest.id]
      if (apiKey) body.api_key = apiKey
      const updated = await apiJson<Service>("/api/settings/services", {
        method: "POST",
        body: JSON.stringify(body),
      })
      setServiceMap((prev) => ({ ...prev, [manifest.id]: updated }))
      setApiKeyInputs((p) => ({ ...p, [manifest.id]: "" }))
      showMsg("success", `${manifest.name} saved`)
    } catch (e: any) {
      showMsg("error", e.message || "Failed to save")
    } finally {
      setIntegrationSaving((p) => ({ ...p, [manifest.id]: false }))
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full bg-gray-950 text-white overflow-hidden">
      {/* Left tab nav */}
      <div className="w-44 flex-shrink-0 border-r border-gray-800/50 flex flex-col pt-6 px-3 gap-1">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-600 px-3 mb-2">Settings</p>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${tab === id
                ? "bg-cyan-500/15 text-cyan-400"
                : "text-gray-500 hover:bg-gray-800/50 hover:text-gray-300"
              }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-8">
        {/* Toast */}
        {msg && (
          <div className={`mb-6 px-4 py-3 rounded-xl text-sm font-medium border ${msg.type === "success"
              ? "bg-green-500/10 border-green-500/20 text-green-400"
              : "bg-red-500/10 border-red-500/20 text-red-400"
            }`}>
            {msg.text}
          </div>
        )}

        {/* ── General Tab ─────────────────────────────────────────────────── */}
        {tab === "general" && (
          <div className="space-y-6 max-w-md">
            <div>
              <h2 className="text-lg font-bold mb-1">General &amp; Localization</h2>
              <p className="text-xs text-gray-500">Language, timezone and location preferences.</p>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  Language
                </label>
                <select
                  value={general.language}
                  onChange={(e) => setGeneral({ ...general, language: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="en">English (US)</option>
                  <option value="ja">日本語</option>
                  <option value="es">Español</option>
                  <option value="fr">Français</option>
                  <option value="de">Deutsch</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  Timezone
                </label>
                <select
                  value={general.timezone}
                  onChange={(e) => setGeneral({ ...general, timezone: e.target.value })}
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                >
                  {IANA_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  Location
                </label>
                <input
                  value={general.location}
                  onChange={(e) => setGeneral({ ...general, location: e.target.value })}
                  placeholder="e.g. Tokyo, Japan"
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <button
              onClick={saveGeneral}
              disabled={saving}
              className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>

            {/* ── System Behavior ── */}
            {IS_TAURI && (
              <div className="border-t border-gray-800 pt-6">
                <div className="flex items-center gap-2 mb-1">
                  <Cpu size={15} className="text-gray-400" />
                  <h3 className="text-sm font-bold text-gray-200">System Behavior</h3>
                </div>
                <p className="text-xs text-gray-500 mb-4">
                  Configure how VisionArk runs on this device.
                </p>
                <div className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-4 py-3">
                  <div>
                    <p className="text-sm font-semibold text-gray-200">Run Daemon in Background</p>
                    <p className="text-[11px] text-gray-500 mt-0.5 max-w-[280px]">
                      Keep the agent's background services running in the system tray when the main window is closed.
                    </p>
                  </div>
                  <button
                    onClick={toggleRunInBackground}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${runInBackground ? "bg-cyan-500" : "bg-gray-700"
                      }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${runInBackground ? "translate-x-6" : "translate-x-1"
                        }`}
                    />
                  </button>
                </div>
              </div>
            )}

            {/* ── Connection ── */}
            <div className="border-t border-gray-800 pt-6">
              <div className="flex items-center gap-2 mb-1">
                <Link size={15} className="text-gray-400" />
                <h3 className="text-sm font-bold text-gray-200">Server Connection</h3>
              </div>
              <p className="text-xs text-gray-500 mb-4">
                VisionArk backend URL. Change this when connecting to a remote or staging server.
              </p>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  API Base URL
                </label>
                <div className="flex gap-2">
                  <input
                    type="url"
                    value={serverUrl}
                    onChange={(e) => setServerUrl(e.target.value)}
                    placeholder="http://localhost:8000"
                    className="flex-1 bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                  />
                  <button
                    onClick={saveServerUrl}
                    className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-semibold rounded-xl transition-colors"
                  >
                    Apply
                  </button>
                </div>
                <p className="text-[11px] text-gray-600 mt-1.5">
                  Active: <span className="font-mono text-gray-500">{getApiBase()}</span>
                </p>
              </div>
            </div>

            {/* ── Storage Info ── */}
            <div className="border-t border-gray-800 pt-6">
              <div className="flex items-center gap-2 mb-1">
                <Database size={15} className="text-gray-400" />
                <h3 className="text-sm font-bold text-gray-200">Storage Locations</h3>
              </div>
              <p className="text-xs text-gray-500 mb-4">Where each type of data is persisted on this device.</p>

              <div className="space-y-2.5">
                {/* Server URL */}
                <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 flex gap-3">
                  <FileText size={15} className="text-cyan-500 mt-0.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gray-300">Server URL</p>
                    <p className="text-[11px] text-gray-500 mt-0.5">
                      {IS_TAURI ? "Config file (shared with daemon)" : "Browser localStorage"}
                    </p>
                    {IS_TAURI && configFilePath && (
                      <p className="text-[10px] font-mono text-gray-600 mt-1 break-all">{configFilePath}</p>
                    )}
                    {!IS_TAURI && (
                      <p className="text-[10px] font-mono text-gray-600 mt-1">key: va_api_url</p>
                    )}
                  </div>
                </div>

                {/* Auth tokens */}
                {IS_TAURI && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 flex gap-3">
                    <Key size={15} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-gray-300">Auth Tokens</p>
                      <p className="text-[11px] text-gray-500 mt-0.5">Windows Credential Manager</p>
                      <p className="text-[10px] font-mono text-gray-600 mt-1">
                        visionark_app / atmos_access_token<br />
                        visionark_app / atmos_refresh_token
                      </p>
                    </div>
                  </div>
                )}
                {!IS_TAURI && (
                  <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 flex gap-3">
                    <Key size={15} className="text-yellow-500 mt-0.5 flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-gray-300">Auth Tokens</p>
                      <p className="text-[11px] text-gray-500 mt-0.5">Browser localStorage</p>
                      <p className="text-[10px] font-mono text-gray-600 mt-1">key: va_token</p>
                    </div>
                  </div>
                )}

                {/* User settings + AI keys */}
                <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 flex gap-3">
                  <Database size={15} className="text-purple-400 mt-0.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-gray-300">User Settings &amp; AI Keys</p>
                    <p className="text-[11px] text-gray-500 mt-0.5">Backend database (PostgreSQL)</p>
                    <p className="text-[10px] font-mono text-gray-600 mt-1">
                      language, timezone, location, AI API keys
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── AI Tab ──────────────────────────────────────────────────────── */}
        {tab === "ai" && (
          <div className="space-y-6 max-w-md">
            <div>
              <h2 className="text-lg font-bold mb-1">AI Providers</h2>
              <p className="text-xs text-gray-500">API keys for LLM providers.</p>
            </div>

            <div className="space-y-4">
              {[
                { key: "gemini_api_key" as const, label: "Gemini API Key" },
                { key: "openai_api_key" as const, label: "OpenAI API Key" },
                { key: "anthropic_api_key" as const, label: "Anthropic API Key" },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                    {label}
                  </label>
                  <input
                    type="password"
                    value={ai[key]}
                    onChange={(e) => setAI({ ...ai, [key]: e.target.value })}
                    placeholder="Enter to update…"
                    className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                  />
                </div>
              ))}

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  Default Model
                </label>
                <input
                  value={ai.default_model}
                  onChange={(e) => setAI({ ...ai, default_model: e.target.value })}
                  placeholder="e.g. claude-sonnet-4-6"
                  className="w-full bg-gray-900 border border-gray-800 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <button
              onClick={saveAI}
              disabled={saving}
              className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}

        {/* ── Services Tab ─────────────────────────────────────────────────── */}
        {tab === "services" && (
          <div className="space-y-6 max-w-md">
            <div>
              <h2 className="text-lg font-bold mb-1">Microservices</h2>
              <p className="text-xs text-gray-500">External service connections.</p>
            </div>

            {/* Registered services list */}
            {services.length > 0 && (
              <div className="space-y-2">
                {services.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between bg-gray-900 border border-gray-800 rounded-xl px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-semibold text-gray-200 uppercase">{s.service_name}</p>
                      <p className="text-[11px] text-gray-500 font-mono mt-0.5 truncate max-w-[220px]">{s.base_url}</p>
                    </div>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${s.health_status === "healthy"
                        ? "bg-green-500/10 text-green-400"
                        : s.health_status
                          ? "bg-red-500/10 text-red-400"
                          : "bg-gray-800 text-gray-500"
                      }`}>
                      {s.health_status || "unknown"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <p className="text-sm font-semibold text-gray-300">LBS Service</p>
              <p className="text-xs text-gray-500 mt-1">
                LBS is managed by the server administrator via environment variables and server-issued keys.
              </p>
            </div>
          </div>
        )}
        {tab === "integrations" && (
          <div className="space-y-4 max-w-lg">
            <div>
              <h2 className="text-lg font-bold mb-1">Integrations</h2>
              <p className="text-xs text-gray-500">
                Connect external tools and services. Toggle to enable, then expand to configure.
              </p>
            </div>

            {/* Category filter */}
            {hubCatalog.length > 0 && (
              <div className="flex gap-1.5 flex-wrap">
                {["all", ...Array.from(new Set(hubCatalog.map((h) => h.category).filter(Boolean)))].map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat as string)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold transition-colors ${
                      categoryFilter === cat
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                        : "bg-gray-800 text-gray-500 hover:text-gray-300 border border-transparent"
                    }`}
                  >
                    {String(cat).charAt(0).toUpperCase() + String(cat).slice(1)}
                  </button>
                ))}
              </div>
            )}

            {hubCatalog.length === 0 && (
              <p className="text-xs text-gray-600 italic">Loading integrations…</p>
            )}

            {hubCatalog
              .filter((item) => categoryFilter === "all" || item.category === categoryFilter)
              .map((manifest) => {
                const svc = serviceMap[manifest.id]
                const isActive = svc?.is_active ?? false
                const expanded = integrationExpanded[manifest.id] ?? false
                const isSaving = integrationSaving[manifest.id] ?? false
                const fields = formValues[manifest.id] || {}

                return (
                  <div
                    key={manifest.id}
                    className={`border rounded-2xl overflow-hidden transition-colors ${
                      isActive
                        ? "border-cyan-500/30 bg-cyan-500/5"
                        : "border-gray-800 bg-gray-900"
                    }`}
                  >
                    {/* Card header */}
                    <div className="flex items-center gap-3 px-5 py-4">
                      <span className="text-2xl select-none">{manifest.icon}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-bold text-gray-100">{manifest.name}</p>
                          {svc && (
                            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 uppercase tracking-wider">
                              {isActive ? "active" : "inactive"}
                            </span>
                          )}
                        </div>
                        <p className="text-[11px] text-gray-500 mt-0.5 line-clamp-1">{manifest.description}</p>
                      </div>

                      {/* Active toggle */}
                      <button
                        onClick={() => toggleIntegrationActive(manifest)}
                        title={isActive ? "Disable" : "Enable"}
                        className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors ${
                          isActive ? "bg-cyan-500" : "bg-gray-700"
                        }`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                            isActive ? "translate-x-6" : "translate-x-1"
                          }`}
                        />
                      </button>

                      {/* Expand / collapse */}
                      <button
                        onClick={() =>
                          setIntegrationExpanded((p) => ({ ...p, [manifest.id]: !p[manifest.id] }))
                        }
                        className="p-1.5 text-gray-500 hover:text-gray-300 transition-colors rounded-lg hover:bg-gray-800"
                      >
                        {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </button>
                    </div>

                    {/* Expanded config */}
                    {expanded && (
                      <div className="border-t border-gray-800/60 px-5 py-4 space-y-4">
                        {/* Setup instructions (collapsed by default) */}
                        {manifest.setup_instructions && manifest.setup_instructions.length > 0 && (
                          <details className="group">
                            <summary className="cursor-pointer text-[11px] font-semibold text-gray-500 hover:text-gray-300 uppercase tracking-wider select-none list-none flex items-center gap-1">
                              <ChevronRight size={12} className="group-open:rotate-90 transition-transform" />
                              Setup Instructions
                            </summary>
                            <ol className="mt-2 space-y-2 pl-4">
                              {manifest.setup_instructions.map((s) => (
                                <li key={s.step} className="text-[11px] text-gray-500">
                                  <span className="font-semibold text-gray-400">{s.step}. {s.title}</span>
                                  <p className="mt-0.5 text-gray-600">{s.content}</p>
                                </li>
                              ))}
                            </ol>
                          </details>
                        )}

                        {/* API Key field (when authType === "api_key") */}
                        {manifest.authType === "api_key" && (
                          <div>
                            <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                              API Key
                            </label>
                            <input
                              type="password"
                              value={apiKeyInputs[manifest.id] ?? ""}
                              onChange={(e) =>
                                setApiKeyInputs((p) => ({ ...p, [manifest.id]: e.target.value }))
                              }
                              placeholder={svc ? "Leave blank to keep existing key" : "Enter API key…"}
                              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                            />
                          </div>
                        )}

                        {/* Base URL field (when authType requires it) */}
                        {manifest.authType === "shared" && (
                          <div>
                            <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                              Base URL
                            </label>
                            <input
                              value={fields._base_url ?? svc?.base_url ?? ""}
                              onChange={(e) => setFormField(manifest.id, "_base_url", e.target.value)}
                              placeholder="https://…"
                              className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                            />
                          </div>
                        )}

                        {/* Dynamic config fields from manifest */}
                        {manifest.config_fields?.map((field) => (
                          <div key={field.key}>
                            <label className="block text-[11px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                              {field.label}
                            </label>

                            {field.type === "select" ? (
                              <select
                                value={fields[field.key] ?? field.default ?? ""}
                                onChange={(e) => setFormField(manifest.id, field.key, e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                              >
                                {field.options?.map((opt) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            ) : field.type === "checkbox" ? (
                              <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={!!(fields[field.key] ?? field.default ?? false)}
                                  onChange={(e) => setFormField(manifest.id, field.key, e.target.checked)}
                                  className="rounded border-gray-700 bg-gray-800 text-cyan-500"
                                />
                                <span className="text-sm text-gray-300">{field.description}</span>
                              </label>
                            ) : field.type === "number" ? (
                              <input
                                type="number"
                                value={fields[field.key] ?? field.default ?? ""}
                                onChange={(e) => setFormField(manifest.id, field.key, e.target.value)}
                                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                              />
                            ) : (
                              <input
                                type="text"
                                value={fields[field.key] ?? field.default ?? ""}
                                onChange={(e) => setFormField(manifest.id, field.key, e.target.value)}
                                placeholder={field.description}
                                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500"
                              />
                            )}

                            {field.type !== "checkbox" && field.description && (
                              <p className="text-[10px] text-gray-600 mt-1">{field.description}</p>
                            )}
                          </div>
                        ))}

                        <button
                          onClick={() => saveIntegration(manifest)}
                          disabled={isSaving}
                          className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors"
                        >
                          {isSaving ? "Saving…" : "Save"}
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        )}

        {/* ── Account Tab ──────────────────────────────────────────────────── */}
        {tab === "account" && (
          <div className="space-y-6 max-w-md">
            <div>
              <h2 className="text-lg font-bold mb-1">Account</h2>
              <p className="text-xs text-gray-500">Profile and security settings.</p>
            </div>

            {/* Profile */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
              <p className="text-sm font-semibold text-gray-300">Profile</p>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Username</label>
                <input
                  readOnly
                  value={profile.username}
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Email</label>
                <input
                  readOnly
                  value={profile.email || "(not set)"}
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-400 focus:outline-none"
                />
              </div>
            </div>

            {/* Change password */}
            <form onSubmit={changePassword} className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <p className="text-sm font-semibold text-gray-300">Change Password</p>
              {[
                { label: "Current Password", val: passForm.current, key: "current" as const },
                { label: "New Password", val: passForm.next, key: "next" as const },
                { label: "Confirm Password", val: passForm.confirm, key: "confirm" as const },
              ].map(({ label, val, key }) => (
                <div key={key}>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">{label}</label>
                  <input
                    type="password"
                    required
                    value={val}
                    onChange={(e) => setPassForm({ ...passForm, [key]: e.target.value })}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-cyan-500"
                  />
                </div>
              ))}
              <button
                type="submit"
                disabled={saving}
                className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                {saving ? "Saving…" : "Change Password"}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  )
}
