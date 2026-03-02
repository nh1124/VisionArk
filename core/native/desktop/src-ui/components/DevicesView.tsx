import React, { useEffect, useState } from "react"
import { Monitor, Smartphone, Server, HelpCircle, RefreshCw, Trash2, Wifi, WifiOff, Clock } from "lucide-react"
import type { NativeDevice, DeviceKind, DeviceStatus } from "../../../shared/types"
import { listDevices, patchDevice, deleteDevice } from "../../../bridge/api"
import { invoke, isTauri } from "@tauri-apps/api/core"

// ── helpers ───────────────────────────────────────────────────────────────────

function KindIcon({ kind }: { kind: DeviceKind }) {
  const cls = "text-gray-500"
  if (kind === "desktop") return <Monitor size={16} className={cls} />
  if (kind === "mobile") return <Smartphone size={16} className={cls} />
  if (kind === "server") return <Server size={16} className={cls} />
  return <HelpCircle size={16} className={cls} />
}

function StatusDot({ status }: { status: DeviceStatus }) {
  if (status === "online") return <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
  if (status === "stale") return <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 inline-block" />
  return <span className="w-1.5 h-1.5 rounded-full bg-gray-600 inline-block" />
}

const PLATFORM_CLS: Record<string, string> = {
  windows: "bg-blue-900/40 text-blue-300",
  macos: "bg-gray-700/60 text-gray-300",
  linux: "bg-orange-900/40 text-orange-300",
  ios: "bg-indigo-900/40 text-indigo-300",
  android: "bg-green-900/40 text-green-300",
  other: "bg-gray-700/40 text-gray-400",
}

// ── component ─────────────────────────────────────────────────────────────────

export default function DevicesView() {
  const [devices, setDevices] = useState<NativeDevice[]>([])
  const [loading, setLoading] = useState(false)
  const [currentDeviceId, setCurrentDeviceId] = useState<string | null>(null)

  const currentDevice = devices.find(d => d.id === currentDeviceId)
  const otherDevices = devices.filter(d => d.id !== currentDeviceId)

  const loadDeviceId = async () => {
    try {
      if (isTauri()) {
        const id = await invoke<string>("get_secure_token", { key: "va_device_id" })
        return id || null
      }
    } catch { /* ignore */ }
    return localStorage.getItem("va_device_id")
  }

  const load = async () => {
    setLoading(true)
    try {
      const data = await listDevices()
      setDevices(data)
      const currentId = await loadDeviceId()
      if (currentId) setCurrentDeviceId(currentId)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleEnabled = async (device: NativeDevice) => {
    try {
      const updated = await patchDevice(device.id, { is_enabled: !device.is_enabled })
      setDevices(prev => prev.map(d => d.id === device.id ? updated : d))
    } catch {
      // ignore
    }
  }

  const handleDelete = async (device: NativeDevice) => {
    if (!window.confirm(`Remove "${device.display_name}"?`)) return
    try {
      await deleteDevice(device.id)
      setDevices(prev => prev.filter(d => d.id !== device.id))
    } catch {
      // ignore
    }
  }

  const renderDeviceCard = (device: NativeDevice, isCurrent: boolean) => (
    <div
      key={device.id}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-colors ${isCurrent ? "bg-cyan-950/20 border-cyan-800/40" :
        device.is_enabled
          ? "bg-gray-900 border-gray-800"
          : "bg-gray-900/40 border-gray-800/40 opacity-60"
        }`}
    >
      {/* Kind icon */}
      <KindIcon kind={device.device_kind} />

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
          <span className={`text-xs font-bold truncate ${isCurrent ? "text-cyan-400" : "text-white"}`}>
            {device.display_name} {isCurrent && "(This Device)"}
          </span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PLATFORM_CLS[device.platform] ?? PLATFORM_CLS.other}`}>
            {device.platform}
          </span>
          {device.client_version && (
            <span className="text-[10px] text-gray-700">v{device.client_version}</span>
          )}
        </div>
        <div className="flex items-center gap-2.5 text-[10px] text-gray-500">
          <span className="flex items-center gap-1">
            <StatusDot status={device.status} />
            <span className={
              device.status === "online" ? "text-green-400" :
                device.status === "stale" ? "text-yellow-400" : ""
            }>
              {device.status}
            </span>
          </span>
          {device.last_seen_at && (
            <span className="flex items-center gap-1">
              <Clock size={9} />
              {new Date(device.last_seen_at).toLocaleString("ja-JP", {
                month: "numeric", day: "numeric",
                hour: "2-digit", minute: "2-digit",
              })}
            </span>
          )}
        </div>
        {device.capabilities.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {device.capabilities.slice(0, 5).map(cap => (
              <span key={cap} className="px-1 py-px bg-gray-800 text-gray-500 rounded text-[9px]">
                {cap}
              </span>
            ))}
            {device.capabilities.length > 5 && (
              <span className="text-[9px] text-gray-700">+{device.capabilities.length - 5}</span>
            )}
          </div>
        )}
      </div>

      {/* Enable/disable toggle */}
      <button
        onClick={() => toggleEnabled(device)}
        title={device.is_enabled ? "Disable" : "Enable"}
        className={`flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium transition-colors ${device.is_enabled
          ? "bg-green-900/30 text-green-400 hover:bg-green-900/50"
          : "bg-gray-800 text-gray-600 hover:bg-gray-700"
          }`}
      >
        {device.is_enabled
          ? <><Wifi size={10} /> On</>
          : <><WifiOff size={10} /> Off</>
        }
      </button>

      {/* Delete */}
      {!isCurrent && (
        <button
          onClick={() => handleDelete(device)}
          className="flex-shrink-0 p-1 rounded-lg text-gray-700 hover:text-red-400 hover:bg-red-950/30 transition-colors"
          title="Remove device"
        >
          <Trash2 size={12} />
        </button>
      )}
    </div>
  )

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-gray-800 flex-shrink-0">
        <Monitor size={15} className="text-purple-400" />
        <span className="text-sm font-semibold text-white flex-1">Devices</span>
        <span className="text-xs text-gray-600">{devices.length} registered</span>
        <button
          onClick={load}
          disabled={loading}
          className="p-1.5 rounded-lg hover:bg-gray-800 text-gray-500 hover:text-gray-300 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {loading && devices.length === 0 ? (
          <div className="flex justify-center pt-16">
            <RefreshCw size={18} className="animate-spin text-gray-700" />
          </div>
        ) : devices.length === 0 ? (
          <div className="flex flex-col items-center justify-center pt-16 gap-3 text-gray-600">
            <Monitor size={32} className="opacity-20" />
            <p className="text-xs">No devices registered yet.</p>
            <p className="text-[11px] text-gray-700">Start the Native daemon to auto-register this machine.</p>
          </div>
        ) : (
          <>
            {/* Current Device Section */}
            {currentDevice && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider pl-1">Current Device</h3>
                {renderDeviceCard(currentDevice, true)}
              </div>
            )}

            {/* Other Devices Section */}
            {otherDevices.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider pl-1 mt-4">Other Devices</h3>
                <div className="space-y-2">
                  {otherDevices.map(d => renderDeviceCard(d, false))}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-gray-800/50 flex-shrink-0">
        <p className="text-[10px] text-gray-700">
          Devices are auto-registered when the daemon starts. Toggle to enable/disable job routing.
        </p>
      </div>
    </div>
  )
}
