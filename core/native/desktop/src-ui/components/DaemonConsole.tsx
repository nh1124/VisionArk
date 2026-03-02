import React, { useEffect, useState, useRef } from "react"
import { listen } from "@tauri-apps/api/event"
import { getCurrentWindow } from "@tauri-apps/api/window"
import { Trash2 } from "lucide-react"

export default function DaemonConsole() {
    const [logs, setLogs] = useState<string[]>([])
    const endRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const cleanups: Array<Promise<() => void>> = []
        const appWindow = getCurrentWindow()

        cleanups.push(
            appWindow.onCloseRequested((event) => {
                event.preventDefault()
                appWindow.hide()
            }).catch(e => {
                console.warn("Could not attach onCloseRequested:", e)
                return () => { }
            })
        )

        cleanups.push(
            listen<string>("daemon-log", (e) => {
                setLogs(prev => {
                    const newLogs = [...prev, e.payload]
                    if (newLogs.length > 2000) newLogs.shift() // Keep last 2000
                    return newLogs
                })
            }).catch(e => {
                console.warn("Could not listen to daemon-log", e)
                return () => { }
            })
        )

        return () => {
            cleanups.forEach(c => c.then(unlisten => unlisten()))
        }
    }, [])

    useEffect(() => {
        endRef.current?.scrollIntoView()
    }, [logs])

    return (
        <div className="flex flex-col h-screen w-screen bg-gray-950 text-white overflow-hidden select-none">
            <div className="titlebar flex justify-between items-center px-4 py-2.5 bg-gray-900 border-b border-gray-800" data-tauri-drag-region>
                <span className="text-sm font-semibold text-gray-300 tracking-wide flex items-center gap-2 pointer-events-none">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    Daemon Console
                </span>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setLogs([])}
                        className="p-1 text-gray-500 hover:text-red-400 hover:bg-gray-800 rounded transition"
                        title="Clear Logs"
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed text-gray-300 bg-black/60 select-text whitespace-pre-wrap">
                {logs.length === 0 ? (
                    <span className="text-gray-600 italic">Waiting for logs...</span>
                ) : (
                    logs.map((log, i) => (
                        <div key={i} className="mb-0.5 break-all">
                            <span className="text-gray-600 mr-2 opacity-50 select-none">
                                {String(i + 1).padStart(4, "0")}
                            </span>
                            <span className={log.includes("ERROR") || log.toLowerCase().includes("error") ? "text-red-400 font-medium" : log.includes("WARN") ? "text-yellow-400" : "text-gray-300"}>
                                {log}
                            </span>
                        </div>
                    ))
                )}
                <div ref={endRef} />
            </div>
        </div>
    )
}
