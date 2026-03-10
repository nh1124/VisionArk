import { type WsEvent } from "../shared/types"

// ─── Types ────────────────────────────────────────────────────────────────────

type EventHandler = (data: unknown) => void
export type ConnectionState = "disconnected" | "connecting" | "connected"

// ─── Internal state ───────────────────────────────────────────────────────────

const handlers = new Map<string, Set<EventHandler>>()
const stateHandlers = new Set<(state: ConnectionState) => void>()

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let _state: ConnectionState = "disconnected"
let _wsUrl = ""
let _token = ""

// ─── State helpers ────────────────────────────────────────────────────────────

function setState(next: ConnectionState) {
  if (_state === next) return
  _state = next
  stateHandlers.forEach((h) => h(next))
}

export function getState(): ConnectionState {
  return _state
}

/** Subscribe to connection state changes. Returns an unsubscribe function. */
export function onStateChange(handler: (state: ConnectionState) => void): () => void {
  stateHandlers.add(handler)
  return () => stateHandlers.delete(handler)
}

// ─── Connection lifecycle ─────────────────────────────────────────────────────

export function connect(wsUrl: string, token: string) {
  // Prevent duplicate connections
  if (_state !== "disconnected") return

  _wsUrl = wsUrl
  _token = token
  _openSocket()
}

function _openSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  setState("connecting")
  const url = `${_wsUrl}?token=${encodeURIComponent(_token)}`
  socket = new WebSocket(url)

  socket.onopen = () => {
    setState("connected")
  }

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WsEvent
      const set = handlers.get(msg.type)
      if (set) {
        set.forEach((h) => h(msg.data))
      }
    } catch (e) {
      const raw = typeof event.data === "string" ? event.data : String(event.data ?? "")
      const preview = raw.length > 500 ? `${raw.slice(0, 500)}...` : raw
      console.warn("[bridge/ws] malformed message", { error: String(e), length: raw.length, preview })
      try {
        localStorage.setItem(
          "va_last_ws_parse_error",
          JSON.stringify({
            ts: new Date().toISOString(),
            error: String(e),
            length: raw.length,
            preview,
          })
        )
      } catch {
        // ignore storage failures
      }
    }
  }

  socket.onclose = () => {
    socket = null
    if (_state !== "disconnected") {
      // Unexpected close — schedule reconnect
      setState("disconnected")
      reconnectTimer = setTimeout(() => _openSocket(), 5000)
    }
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function disconnect() {
  setState("disconnected")
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  socket?.close()
  socket = null
  _wsUrl = ""
  _token = ""
}

// ─── Event subscription ───────────────────────────────────────────────────────

/** Subscribe to a specific WS event type. Returns an unsubscribe function. */
export function on(eventType: string, handler: EventHandler): () => void {
  if (!handlers.has(eventType)) handlers.set(eventType, new Set())
  handlers.get(eventType)!.add(handler)
  return () => handlers.get(eventType)?.delete(handler)
}
