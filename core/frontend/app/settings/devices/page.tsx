"use client"

import { useEffect, useState } from "react"
import {
  Monitor, Smartphone, Server, HelpCircle, Wifi, WifiOff, Clock,
  Trash2, RefreshCw,
} from "lucide-react"
import { apiFetch } from "@/lib/api"
import type { NativeDevice, DeviceKind, DeviceStatus } from "@/types/native"

// ── helpers ──────────────────────────────────────────────────────────────────

function kindIcon(kind: DeviceKind) {
  const cls = "text-gray-400"
  if (kind === "desktop") return <Monitor size={18} className={cls} />
  if (kind === "mobile") return <Smartphone size={18} className={cls} />
  if (kind === "server") return <Server size={18} className={cls} />
  return <HelpCircle size={18} className={cls} />
}

function statusDot(status: DeviceStatus) {
  if (status === "online") return <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
  if (status === "stale") return <span className="w-2 h-2 rounded-full bg-yellow-400 inline-block" />
  return <span className="w-2 h-2 rounded-full bg-gray-600 inline-block" />
}

function statusLabel(status: DeviceStatus) {
  if (status === "online") return <span className="text-green-400 text-xs">Online</span>
  if (status === "stale") return <span className="text-yellow-400 text-xs">Stale</span>
  return <span className="text-gray-500 text-xs">Offline</span>
}

function platformBadge(platform: string) {
  const map: Record<string, string> = {
    windows: "bg-blue-900/40 text-blue-300",
    macos: "bg-gray-700/60 text-gray-300",
    linux: "bg-orange-900/40 text-orange-300",
    ios: "bg-indigo-900/40 text-indigo-300",
    android: "bg-green-900/40 text-green-300",
    other: "bg-gray-700/40 text-gray-400",
  }
  const cls = map[platform] ?? map.other
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {platform}
    </span>
  )
}

// ── component ────────────────────────────────────────────────────────────────

export default function DevicesPage() {
  const [devices, setDevices] = useState<NativeDevice[]>([])
  const [loading, setLoading] = useState(true)

  const fetchDevices = async () => {
    setLoading(true)
    try {
      const res = await apiFetch("/api/native/devices")
      const data = await res.json()
      setDevices(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDevices() }, [])

  const toggleEnabled = async (device: NativeDevice) => {
    try {
      await apiFetch(`/api/native/devices/${device.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_enabled: !device.is_enabled }),
      })
      setDevices(prev =>
        prev.map(d => d.id === device.id ? { ...d, is_enabled: !d.is_enabled } : d)
      )
    } catch {
      // ignore
    }
  }

  const deleteDevice = async (device: NativeDevice) => {
    if (!confirm(`Remove "${device.display_name}"?`)) return
    try {
      await apiFetch(`/api/native/devices/${device.id}`, { method: "DELETE" })
      setDevices(prev => prev.filter(d => d.id !== device.id))
    } catch {
      // ignore
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-950">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800/50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-purple-600/20 rounded-xl flex items-center justify-center">
            <Monitor size={16} className="text-purple-400" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white">Devices</h1>
            <p className="text-xs text-gray-500">{devices.length} registered device{devices.length !== 1 ? "s" : ""}</p>
          </div>
        </div>
        <button
          onClick={fetchDevices}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center py-20 text-gray-500 text-sm">Loading…</div>
        ) : devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-gray-500">
            <Monitor size={36} className="opacity-30" />
            <p className="text-sm">No devices registered yet.</p>
            <p className="text-xs text-gray-600">Start the Native daemon on a device to register it automatically.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {devices.map(device => (
              <div
                key={device.id}
                className={`flex items-center gap-4 px-4 py-3 rounded-xl border transition-colors ${
                  device.is_enabled
                    ? "bg-gray-900 border-gray-800"
                    : "bg-gray-900/50 border-gray-800/50 opacity-60"
                }`}
              >
                {/* Icon */}
                <div className="flex-shrink-0">{kindIcon(device.device_kind)}</div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-white truncate">{device.display_name}</span>
                    {platformBadge(device.platform)}
                    {device.client_version && (
                      <span className="text-xs text-gray-600">v{device.client_version}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500">
                    <span className="flex items-center gap-1">
                      {statusDot(device.status)}
                      {statusLabel(device.status)}
                    </span>
                    {device.last_seen_at && (
                      <span className="flex items-center gap-1">
                        <Clock size={10} />
                        {new Date(device.last_seen_at).toLocaleString()}
                      </span>
                    )}
                    {device.capabilities.length > 0 && (
                      <span className="hidden sm:flex items-center gap-1 flex-wrap">
                        {device.capabilities.slice(0, 4).map(cap => (
                          <span key={cap} className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400 text-xs">
                            {cap}
                          </span>
                        ))}
                        {device.capabilities.length > 4 && (
                          <span className="text-gray-600">+{device.capabilities.length - 4}</span>
                        )}
                      </span>
                    )}
                  </div>
                </div>

                {/* Enable toggle */}
                <button
                  onClick={() => toggleEnabled(device)}
                  title={device.is_enabled ? "Disable device" : "Enable device"}
                  className={`flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                    device.is_enabled
                      ? "bg-green-900/30 text-green-400 hover:bg-green-900/50"
                      : "bg-gray-800 text-gray-500 hover:bg-gray-700"
                  }`}
                >
                  {device.is_enabled ? (
                    <><Wifi size={12} /> Enabled</>
                  ) : (
                    <><WifiOff size={12} /> Disabled</>
                  )}
                </button>

                {/* Delete */}
                <button
                  onClick={() => deleteDevice(device)}
                  className="flex-shrink-0 p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-950/30 transition-colors"
                  title="Remove device"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
