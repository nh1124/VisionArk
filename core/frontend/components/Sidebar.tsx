"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface SidebarProps {
    isCollapsed: boolean;
    onToggle: () => void;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
    const pathname = usePathname();
    const [spokes, setSpokes] = useState<{ name: string; path: string; display_name?: string }[]>([]);
    const [spokesExpanded, setSpokesExpanded] = useState(true);

    useEffect(() => {
        loadSpokes();
    }, []);

    const loadSpokes = async () => {
        try {
            const response = await apiFetch("/api/agents/spoke/list");
            const data = await response.json();
            console.log("Loaded spokes data:", data);

            // Sort spokes alphabetically if they exist
            if (data && data.spokes && Array.isArray(data.spokes)) {
                const sortedSpokes = data.spokes.sort((a: any, b: any) =>
                    a.name.localeCompare(b.name)
                );

                setSpokes(sortedSpokes.map((s: any) => ({
                    name: s.name,
                    display_name: s.display_name,
                    path: `/spokes/${s.name}`
                })));
            } else {
                console.warn("No spokes found in response:", data);
                setSpokes([]);
            }
        } catch (error) {
            console.error("Failed to load spokes:", error);
        }
    };

    const navItems = [
        { name: "Home", path: "/", icon: "🏠" },
        { name: "Dashboard", path: "/dashboard", icon: "📊" },
        { name: "Tasks", path: "/tasks", icon: "✅" },
        { name: "Hub", path: "/hub", icon: "⌘" },
    ];

    return (
        <div id="vision-ark-sidebar" className={`bg-gray-900 border-r border-gray-800 flex flex-col h-screen transition-all duration-300 ease-in-out relative ${isCollapsed ? "w-20" : "w-72"}`}>
            {/* Toggle Button */}
            <button
                onClick={onToggle}
                className="absolute -right-3 top-6 w-6 h-6 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center text-gray-400 hover:text-white transition-all z-10 shadow-lg"
            >
                <span className={`text-xs transition-transform duration-300 ${isCollapsed ? "rotate-180" : ""}`}>◀</span>
            </button>

            {/* Sidebar header */}
            <div className={`p-4 border-b border-gray-800 overflow-hidden whitespace-nowrap transition-all duration-300 ${isCollapsed ? "items-center px-2" : ""}`}>
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-blue-600 rounded flex items-center justify-center font-bold text-white flex-shrink-0">V</div>
                    {!isCollapsed && (
                        <div className="transition-opacity duration-300">
                            <h1 className="text-xl font-bold">Vision Ark</h1>
                            <p className="text-[10px] text-gray-500 uppercase tracking-tighter">AI Task Management</p>
                        </div>
                    )}
                </div>
            </div>

            <nav className="flex-1 p-4 overflow-y-auto">
                <ul className="space-y-2">
                    {navItems.map((item) => {
                        const isActive = pathname === item.path;
                        return (
                            <li key={item.path}>
                                <Link
                                    href={item.path}
                                    className={`flex items-center px-4 py-2.5 rounded-xl transition-all group relative ${isCollapsed ? "justify-center px-0" : "gap-3"} ${isActive
                                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                                        : "hover:bg-gray-800/50 text-gray-400"
                                        }`}
                                    title={isCollapsed ? item.name : ""}
                                >
                                    <span className={`text-xl transition-transform group-hover:scale-110 ${isActive ? "scale-110" : ""}`}>{item.icon}</span>
                                    {!isCollapsed && <span className="font-medium">{item.name}</span>}
                                    {isCollapsed && isActive && (
                                        <div className="absolute left-0 w-1 h-6 bg-blue-500 rounded-r-full" />
                                    )}
                                </Link>
                            </li>
                        );
                    })}

                    {/* Spokes Section */}
                    <li className={`pt-3 border-t border-gray-800 mt-3 ${isCollapsed ? "px-2" : ""}`}>
                        <button
                            onClick={() => {
                                setSpokesExpanded(!spokesExpanded);
                            }}
                            className={`flex items-center rounded-xl transition-all hover:bg-gray-800/50 text-gray-400 group ${isCollapsed ? "justify-center px-0 py-2.5" : "gap-3 px-4 py-2 w-full"}`}
                            title={isCollapsed ? "Spokes" : ""}
                        >
                            <span className="text-xl text-cyan-400 group-hover:drop-shadow-[0_0_8px_rgba(34,211,238,0.5)] transition-all">{"_>"}</span>
                            {!isCollapsed && (
                                <>
                                    <span className="flex-1 text-left font-medium">Spokes</span>
                                    <span className="text-xs opacity-50">{spokesExpanded ? "▼" : "▶"}</span>
                                </>
                            )}
                        </button>
                    </li>

                    {spokesExpanded && !isCollapsed && (
                        <>
                            {spokes.length === 0 ? (
                                <li className="px-8 py-2 text-[10px] text-gray-600 italic uppercase">
                                    No spokes yet
                                </li>
                            ) : (
                                spokes.map((spoke) => {
                                    const isActive = pathname.startsWith(spoke.path);
                                    return (
                                        <li key={spoke.name} className="pl-4">
                                            <Link
                                                href={spoke.path}
                                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all border ${isActive
                                                    ? "bg-cyan-500/5 text-cyan-400 border-cyan-500/20"
                                                    : "hover:bg-gray-800/30 text-gray-500 border-transparent"
                                                    }`}
                                            >
                                                <span className="opacity-50">•</span>
                                                <span className="truncate" title={spoke.display_name || spoke.name}>
                                                    {spoke.display_name || spoke.name}
                                                </span>
                                            </Link>
                                        </li>
                                    );
                                })
                            )}
                            <li className="pl-4 mt-2">
                                <Link
                                    href="/spokes"
                                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs transition-all hover:bg-cyan-500/10 text-gray-500 hover:text-cyan-400 font-bold uppercase tracking-wider"
                                >
                                    <span className="text-xl">+</span>
                                    <span>Manage Spokes</span>
                                </Link>
                            </li>
                        </>
                    )}
                </ul>
            </nav>

            <div className="p-4 border-t border-gray-800 mt-auto bg-gray-950/20">
                <Link
                    href="/settings"
                    className={`flex items-center rounded-xl transition-all mb-4 group ${isCollapsed ? "justify-center p-2.5" : "gap-3 px-4 py-2.5"} ${pathname === "/settings"
                        ? "bg-white/5 text-white border border-white/10 shadow-xl"
                        : "hover:bg-gray-800/50 text-gray-400"
                        }`}
                    title={isCollapsed ? "Settings" : ""}
                >
                    <span className={`text-xl transition-transform group-hover:rotate-45`}>⚙️</span>
                    {!isCollapsed && <span className="font-medium">Settings</span>}
                </Link>

                {!isCollapsed && (
                    <div className="text-[9px] text-gray-700 uppercase tracking-[0.2em] font-black pl-2">
                        <p className="flex items-center gap-2">
                            <span className="w-1 h-1 rounded-full bg-green-500 animate-pulse" />
                            Vision Ark OS v1.0
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
