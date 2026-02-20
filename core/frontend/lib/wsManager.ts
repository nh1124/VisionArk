/**
 * WebSocket Manager - Window-level singleton that survives HMR / React re-mounts.
 *
 * The Next.js dev server triggers Fast Refresh (HMR) which re-mounts React
 * components, killing any WebSocket connections initiated inside useEffect.
 * This module stores the active WebSocket connection on `window` so it persists
 * across component re-renders and HMR rebuilds.
 */

export interface WSEvent {
    type: "status" | "meta" | "done" | "error";
    data: any;
}

export type WSCallback = (event: WSEvent) => void;

interface WSConnection {
    taskId: string;
    socket: WebSocket;
    listeners: Set<WSCallback>;
}

// Augment the Window type
declare global {
    interface Window {
        __ws_connection?: WSConnection;
    }
}

/**
 * Start a WebSocket stream for the given task.
 * If a stream is already running for a different task, it is closed first.
 * If a stream is already running for the same task, this is a no-op.
 */
export function startWS(taskId: string, token: string | null): void {
    // Skip if already connected to this task
    if (window.__ws_connection?.taskId === taskId) {
        return;
    }

    // Close any existing connection
    stopWS();

    // Derive WebSocket URL from current browser location to pass through Next.js proxy
    const host = window.location.host; // e.g. localhost:3000 or my-ngrok-url.com
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${host}/api/agents/tasks/${taskId}/ws`;

    console.log("[WS-Manager] Starting stream:", taskId);

    // We cannot pass custom headers like Authorization to native WebSocket constructor directly in the browser.
    // Usually auth is handled via a ticket, cookie, or query param for WebSockets.
    // For now, if the backend doesn't stringently enforce the token on this specific endpoint or uses cookies, this will connect.
    const socket = new WebSocket(wsUrl);

    const connection: WSConnection = {
        taskId,
        socket,
        listeners: new Set(),
    };
    window.__ws_connection = connection;

    socket.onopen = () => {
        console.log("[WS-Manager] Connected to", wsUrl);
    };

    socket.onmessage = (event) => {
        try {
            const dataStr = event.data;
            const data = JSON.parse(dataStr);

            // Emit meta events (tool_start, tool_end, turn_text)
            if (data.meta && data.meta.type) {
                emit(connection, { type: "meta", data });
            }

            // Emit status updates
            if (data.phase || data.status) {
                emit(connection, { type: "status", data });
            }
        } catch (e) {
            // Ignore parse errors
        }
    };

    socket.onerror = (error) => {
        console.error("[WS-Manager] WebSocket error:", error);
        emit(connection, { type: "error", data: { message: "WebSocket error occurred." } });
    };

    socket.onclose = (event) => {
        console.log("[WS-Manager] WebSocket closed:", event.code, event.reason);
        if (event.code === 1000) {
            emit(connection, { type: "done", data: {} });
        }

        // Clean up window reference if this is still the active connection
        if (window.__ws_connection === connection) {
            window.__ws_connection = undefined;
        }
    };
}

/**
 * Stop the current WS connection if any.
 */
export function stopWS(): void {
    if (window.__ws_connection) {
        console.log("[WS-Manager] Stopping stream:", window.__ws_connection.taskId);
        window.__ws_connection.socket.close(1000, "Client stopped");
        window.__ws_connection.listeners.clear();
        window.__ws_connection = undefined;
    }
}

/**
 * Register a callback to receive WS events.
 * Returns an unsubscribe function.
 */
export function onWS(callback: WSCallback): () => void {
    if (window.__ws_connection) {
        window.__ws_connection.listeners.add(callback);
    }
    return () => {
        window.__ws_connection?.listeners.delete(callback);
    };
}

function emit(conn: WSConnection, event: WSEvent): void {
    for (const cb of conn.listeners) {
        try {
            cb(event);
        } catch (e) {
            console.error("[WS-Manager] Listener error:", e);
        }
    }
}
