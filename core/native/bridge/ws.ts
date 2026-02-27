type EventHandler = (data: unknown) => void

const handlers = new Map<string, Set<EventHandler>>()
let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

export function connect(wsUrl: string, token: string) {
  const url = `${wsUrl}?token=${encodeURIComponent(token)}`
  socket = new WebSocket(url)

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as { type: string; data: unknown }
      const set = handlers.get(msg.type)
      if (set) {
        set.forEach((h) => h(msg.data))
      }
    } catch {
      // ignore malformed messages
    }
  }

  socket.onclose = () => {
    reconnectTimer = setTimeout(() => connect(wsUrl, token), 5000)
  }

  socket.onerror = () => {
    socket?.close()
  }
}

export function disconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  socket?.close()
  socket = null
}

export function on(eventType: string, handler: EventHandler): () => void {
  if (!handlers.has(eventType)) handlers.set(eventType, new Set())
  handlers.get(eventType)!.add(handler)
  return () => handlers.get(eventType)?.delete(handler)
}
