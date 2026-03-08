import React, { useEffect, useMemo, useRef, useState } from "react"
import { Bell, Check, ExternalLink, Settings, StickyNote, AlarmClock, Files } from "lucide-react"
import { type ProjectSidebarMode } from "../App"
import { listNotifications, markAllNotificationsAsRead, markNotificationAsRead, type NotificationItem } from "../lib/api"

interface Props {
    projectName?: string
    username?: string
    sidebarMode?: ProjectSidebarMode
    setSidebarMode?: (mode: ProjectSidebarMode) => void
}

export default function TopBar({ projectName, username, sidebarMode, setSidebarMode }: Props) {
    const [isNotifOpen, setIsNotifOpen] = useState(false)
    const [notifications, setNotifications] = useState<NotificationItem[]>([])
    const [unreadCount, setUnreadCount] = useState(0)
    const [isLoadingNotif, setIsLoadingNotif] = useState(false)
    const notifRef = useRef<HTMLDivElement>(null)

    const refreshNotifications = async () => {
        setIsLoadingNotif(true)
        try {
            const data = await listNotifications(40, 0)
            setNotifications(data.notifications || [])
            setUnreadCount(data.unread_count || 0)
        } catch (e) {
            console.error("Failed to load notifications:", e)
        } finally {
            setIsLoadingNotif(false)
        }
    }

    const markAsRead = async (id: string) => {
        try {
            await markNotificationAsRead(id)
            setNotifications((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n))
            setUnreadCount((prev) => Math.max(0, prev - 1))
        } catch (e) {
            console.error("Failed to mark notification as read:", e)
        }
    }

    const markAllAsRead = async () => {
        try {
            await markAllNotificationsAsRead()
            setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
            setUnreadCount(0)
        } catch (e) {
            console.error("Failed to mark all notifications as read:", e)
        }
    }

    const relativeTime = (iso: string): string => {
        const date = new Date(iso)
        const diffMs = date.getTime() - Date.now()
        const sec = Math.round(diffMs / 1000)
        const absSec = Math.abs(sec)
        if (absSec < 60) return `${absSec}s ago`
        const min = Math.round(sec / 60)
        if (Math.abs(min) < 60) return `${Math.abs(min)}m ago`
        const hour = Math.round(min / 60)
        if (Math.abs(hour) < 24) return `${Math.abs(hour)}h ago`
        const day = Math.round(hour / 24)
        return `${Math.abs(day)}d ago`
    }

    const sortedNotifications = useMemo(
        () => [...notifications].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
        [notifications]
    )

    const openNotification = (n: NotificationItem) => {
        try {
            if (n.link && /^https?:\/\//i.test(n.link)) {
                window.open(n.link, "_blank", "noopener,noreferrer")
                return
            }

            const rawLink = n.link || ""
            if (rawLink) {
                const url = new URL(rawLink, window.location.origin)
                const path = url.pathname

                if (path.startsWith("/monitor/jobs/")) {
                    window.dispatchEvent(new CustomEvent("va-open-notification", {
                        detail: { view: "monitoring" },
                    }))
                    return
                }

                if (path.startsWith("/projects/")) {
                    const parts = path.split("/").filter(Boolean)
                    const projectId = parts.length >= 2 ? parts[1] : null
                    const sessionId = url.searchParams.get("session_id")
                    if (projectId) {
                        window.dispatchEvent(new CustomEvent("va-open-notification", {
                            detail: { view: "chat", project_id: projectId, session_id: sessionId },
                        }))
                        return
                    }
                }

                if (path.startsWith("/run-center") || path.startsWith("/runs")) {
                    window.dispatchEvent(new CustomEvent("va-open-notification", {
                        detail: { view: "run_center" },
                    }))
                    return
                }
            }

            if (n.project_id) {
                window.dispatchEvent(new CustomEvent("va-open-notification", {
                    detail: { view: "chat", project_id: n.project_id, session_id: null },
                }))
            }
        } finally {
            if (!n.is_read) {
                markAsRead(n.id)
            }
            setIsNotifOpen(false)
        }
    }

    useEffect(() => {
        refreshNotifications()
    }, [])

    useEffect(() => {
        if (!isNotifOpen) return
        refreshNotifications()
    }, [isNotifOpen])

    useEffect(() => {
        const onRealtime = (evt: Event) => {
            const detail = (evt as CustomEvent<any>).detail || {}
            const looksLikeNotification = typeof detail.id === "string" && typeof detail.title === "string" && typeof detail.content === "string"
            if (!looksLikeNotification) return
            setNotifications((prev) => [detail as NotificationItem, ...prev.filter((n) => n.id !== detail.id)])
            if (!detail.is_read) {
                setUnreadCount((prev) => prev + 1)
            }
        }
        window.addEventListener("va-realtime-job", onRealtime as EventListener)
        return () => window.removeEventListener("va-realtime-job", onRealtime as EventListener)
    }, [])

    useEffect(() => {
        const onClickOutside = (evt: MouseEvent) => {
            if (!notifRef.current || notifRef.current.contains(evt.target as Node)) return
            setIsNotifOpen(false)
        }
        document.addEventListener("mousedown", onClickOutside)
        return () => document.removeEventListener("mousedown", onClickOutside)
    }, [])

    return (
        <nav className="bg-gray-950 border-b border-gray-800 px-6 py-2.5 flex items-center justify-between flex-shrink-0">
            <div className="flex items-center space-x-4">
                {projectName ? (
                    <h1 className="text-lg font-semibold text-cyan-400 truncate">{projectName}</h1>
                ) : (
                    <div className="flex items-center space-x-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                        <span className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-500">
                            Vision Ark
                        </span>
                    </div>
                )}
            </div>

            <div className="flex items-center space-x-2">
                {/* Project-specific navigation - only show if projectName was passed (we are in ChatView) */}
                {projectName && setSidebarMode && (
                    <div className="flex items-center space-x-1 border-r border-gray-800 pr-4 mr-2">
                        <button
                            onClick={() => setSidebarMode(sidebarMode === "notes" ? null : "notes")}
                            className={`p-2 rounded-lg transition-colors ${sidebarMode === "notes" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                            title="Notes"
                        >
                            <StickyNote size={18} />
                        </button>
                        <button
                            onClick={() => setSidebarMode(sidebarMode === "automation" ? null : "automation")}
                            className={`p-2 rounded-lg transition-colors ${sidebarMode === "automation" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                            title="Automation"
                        >
                            <AlarmClock size={18} />
                        </button>
                        <button
                            onClick={() => setSidebarMode(sidebarMode === "files" ? null : "files")}
                            className={`p-2 rounded-lg transition-colors ${sidebarMode === "files" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                            title="Files"
                        >
                            <Files size={18} />
                        </button>
                    </div>
                )}

                <div className="relative" ref={notifRef}>
                    <button
                        onClick={() => setIsNotifOpen((prev) => !prev)}
                        className="p-2 rounded-lg hover:bg-gray-800 transition-colors text-gray-400 hover:text-white relative"
                        title="Notifications"
                    >
                        <Bell size={18} />
                        {unreadCount > 0 && (
                            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 bg-red-500 text-white text-[10px] leading-4 rounded-full text-center">
                                {unreadCount > 9 ? "9+" : unreadCount}
                            </span>
                        )}
                    </button>

                    {isNotifOpen && (
                        <div className="absolute right-0 top-full mt-2 w-96 max-w-[calc(100vw-1rem)] max-h-[420px] bg-gray-900 border border-gray-800 rounded-xl shadow-2xl overflow-hidden z-50 flex flex-col">
                            <div className="px-3 py-2 border-b border-gray-800 flex items-center justify-between">
                                <span className="text-sm font-semibold text-gray-100">Notifications</span>
                                {unreadCount > 0 && (
                                    <button
                                        onClick={markAllAsRead}
                                        className="text-[11px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                                    >
                                        <Check size={12} />
                                        Mark all read
                                    </button>
                                )}
                            </div>
                            <div className="overflow-y-auto custom-scrollbar">
                                {isLoadingNotif ? (
                                    <div className="px-4 py-6 text-xs text-gray-500">Loading...</div>
                                ) : sortedNotifications.length === 0 ? (
                                    <div className="px-4 py-6 text-xs text-gray-500">No notifications yet.</div>
                                ) : (
                                    sortedNotifications.map((n) => (
                                        <div key={n.id} className={`px-3 py-2.5 border-b border-gray-800/60 hover:bg-gray-800/40 ${n.is_read ? "" : "bg-cyan-500/5"}`}>
                                            <div className="flex items-start gap-2">
                                                <div className={`mt-1 h-2 w-2 rounded-full ${n.type === "error" ? "bg-red-500" : n.type === "warning" ? "bg-amber-500" : n.type === "success" ? "bg-green-500" : "bg-blue-500"}`} />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center justify-between gap-2">
                                                        <div className="text-xs font-semibold text-gray-100 truncate">{n.title}</div>
                                                        <div className="text-[10px] text-gray-500 whitespace-nowrap">{relativeTime(n.created_at)}</div>
                                                    </div>
                                                    <div className="text-xs text-gray-400 mt-0.5 whitespace-pre-wrap break-words">{n.content}</div>
                                                    <div className="mt-1.5 flex items-center gap-2">
                                                        {!n.is_read && (
                                                            <button
                                                                onClick={() => markAsRead(n.id)}
                                                                className="text-[10px] text-cyan-400 hover:text-cyan-300"
                                                            >
                                                                Mark read
                                                            </button>
                                                        )}
                                                        {n.link && (
                                                            <button
                                                                onClick={() => openNotification(n)}
                                                                className="text-[10px] text-gray-400 hover:text-gray-200 flex items-center gap-1"
                                                            >
                                                                <ExternalLink size={10} />
                                                                Open
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <button
                    onClick={() => setSidebarMode && setSidebarMode(sidebarMode === "settings" ? null : "settings")}
                    className={`p-2 rounded-lg transition-colors ${sidebarMode === "settings" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                    title="Project Settings"
                >
                    <Settings size={18} />
                </button>
            </div>
        </nav>
    )
}
