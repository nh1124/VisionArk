import React from "react"
import { Bell, Settings, LogOut, StickyNote, AlarmClock, Activity as ActivityIcon, Files } from "lucide-react"
import { type ProjectSidebarMode } from "../App"

interface Props {
    projectName?: string
    username?: string
    sidebarMode?: ProjectSidebarMode
    setSidebarMode?: (mode: ProjectSidebarMode) => void
}

export default function TopBar({ projectName, username, sidebarMode, setSidebarMode }: Props) {
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
                            onClick={() => setSidebarMode(sidebarMode === "activity" ? null : "activity")}
                            className={`p-2 rounded-lg transition-colors ${sidebarMode === "activity" ? "bg-cyan-500/20 text-cyan-400" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}
                            title="Activity"
                        >
                            <ActivityIcon size={18} />
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

                <button
                    className="p-2 rounded-lg hover:bg-gray-800 transition-colors text-gray-400 hover:text-white"
                    title="Notifications"
                >
                    <Bell size={18} />
                </button>

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
