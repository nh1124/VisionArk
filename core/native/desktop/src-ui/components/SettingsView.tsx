import React, { useEffect, useState } from "react"
import { apiFetch, apiJson } from "../lib/api"
import { User, Cpu, Server, Globe } from "lucide-react"

type Tab = "general" | "ai" | "services" | "account"

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
  { id: "general",  label: "General",  icon: Globe  },
  { id: "ai",       label: "AI",       icon: Cpu    },
  { id: "services", label: "Services", icon: Server },
  { id: "account",  label: "Account",  icon: User   },
]

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
  const [lbsForm, setLbsForm] = useState({ base_url: "", api_key: "" })

  // Account
  const [profile, setProfile] = useState({ username: "", email: "" })
  const [passForm, setPassForm] = useState({ current: "", next: "", confirm: "" })

  // ── Load ──────────────────────────────────────────────────────────────────

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
        setServices(data.services || [])
        const lbs = (data.services || []).find((s: Service) => s.service_name === "lbs")
        if (lbs) setLbsForm((f) => ({ ...f, base_url: lbs.base_url }))
        if (data.profile) setProfile({ username: data.profile.username, email: data.profile.email || "" })
      })
      .catch(() => {})
  }, [])

  function showMsg(type: "success" | "error", text: string) {
    setMsg({ type, text })
    setTimeout(() => setMsg(null), 3500)
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

  async function saveLBS() {
    setSaving(true)
    try {
      await apiJson("/api/settings/services", {
        method: "POST",
        body: JSON.stringify({ service_name: "lbs", base_url: lbsForm.base_url, api_key: lbsForm.api_key || undefined }),
      })
      showMsg("success", "LBS service saved")
      const data = await apiJson<any>("/api/settings")
      setServices(data.services || [])
    } catch (e: any) {
      showMsg("error", e.message || "Failed to save")
    } finally {
      setSaving(false)
    }
  }

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
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all ${
              tab === id
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
          <div className={`mb-6 px-4 py-3 rounded-xl text-sm font-medium border ${
            msg.type === "success"
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
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      s.health_status === "healthy"
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

            {/* LBS form */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
              <p className="text-sm font-semibold text-gray-300">LBS Service</p>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  Base URL
                </label>
                <input
                  value={lbsForm.base_url}
                  onChange={(e) => setLbsForm({ ...lbsForm, base_url: e.target.value })}
                  placeholder="http://localhost:8100/api/lbs"
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-1.5">
                  API Key
                </label>
                <input
                  type="password"
                  value={lbsForm.api_key}
                  onChange={(e) => setLbsForm({ ...lbsForm, api_key: e.target.value })}
                  placeholder="Leave blank to keep existing"
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>
              <button
                onClick={saveLBS}
                disabled={saving || !lbsForm.base_url}
                className="px-6 py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                {saving ? "Saving…" : "Save LBS"}
              </button>
            </div>
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
                { label: "Current Password",  val: passForm.current,  key: "current"  as const },
                { label: "New Password",       val: passForm.next,     key: "next"     as const },
                { label: "Confirm Password",   val: passForm.confirm,  key: "confirm"  as const },
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
