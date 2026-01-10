"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { apiFetch, getFileToken } from "@/lib/api";

interface SidebarProps {
    isCollapsed: boolean;
    onToggle: () => void;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
    const pathname = usePathname();
    const [spokes, setSpokes] = useState<{ name: string; path: string; display_name?: string }[]>([]);
    const [spokesExpanded, setSpokesExpanded] = useState(true);
    const [hoveredSpoke, setHoveredSpoke] = useState<string | null>(null);
    const [menuOpen, setMenuOpen] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        loadSpokes();
    }, []);

    // Close menu when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setMenuOpen(null);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const loadSpokes = async () => {
        try {
            const response = await apiFetch("/api/agents/spoke/list");
            const data = await response.json();

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
                setSpokes([]);
            }
        } catch (error) {
            console.error("Failed to load spokes:", error);
        }
    };

    const handleExportChat = async (spokeName: string) => {
        try {
            const token = await getFileToken();
            const exportUrl = `/api/export/chat/${spokeName}?token=${token}`;

            // Create a temporary link to trigger download
            const link = document.createElement('a');
            link.href = exportUrl;
            link.setAttribute('download', `${spokeName}_chat.md`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            setMenuOpen(null);
        } catch (error) {
            console.error("Export failed:", error);
            alert("Failed to export chat history.");
        }
    };

    const navItems = [
        { name: "Home", path: "/" },
        { name: "Dashboard", path: "/dashboard" },
        { name: "Tasks", path: "/tasks" },
        { name: "Hub", path: "/hub" },
    ];

    return (
        <div
            id="vision-ark-sidebar"
            className={`bg-gray-950 border-r border-gray-800/50 flex flex-col h-screen transition-all duration-200 relative ${isCollapsed ? "w-16" : "w-64"}`}
        >
            {/* Toggle Button */}
            <button
                onClick={onToggle}
                className="absolute -right-3 top-5 w-6 h-6 bg-gray-800 border border-gray-700 rounded-full flex items-center justify-center text-gray-500 hover:text-white hover:bg-gray-700 transition-all z-10"
            >
                <span className={`text-xs transition-transform duration-200 ${isCollapsed ? "rotate-180" : ""}`}>◀</span>
            </button>

            {/* Header */}
            <div className={`p-3 border-b border-gray-800/50 ${isCollapsed ? "px-2" : ""}`}>
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm flex-shrink-0">
                        V
                    </div>
                    {!isCollapsed && (
                        <span className="text-sm font-semibold text-white">Vision Ark</span>
                    )}
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-1 py-2 overflow-y-auto">
                {/* Main Nav */}
                <div className="px-2 space-y-0.5">
                    {navItems.map((item) => {
                        const isActive = pathname === item.path;
                        return (
                            <Link
                                key={item.path}
                                href={item.path}
                                className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${isCollapsed ? "justify-center" : ""} ${isActive
                                    ? "bg-gray-800 text-white"
                                    : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                                    }`}
                                title={isCollapsed ? item.name : ""}
                            >
                                {isCollapsed ? item.name.charAt(0) : item.name}
                            </Link>
                        );
                    })}
                </div>

                {/* Spokes Section */}
                <div className="mt-4 pt-4 border-t border-gray-800/50">
                    <button
                        onClick={() => setSpokesExpanded(!spokesExpanded)}
                        className={`flex items-center w-full px-4 py-1.5 text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors ${isCollapsed ? "justify-center px-2" : ""}`}
                    >
                        {isCollapsed ? (
                            <span>S</span>
                        ) : (
                            <>
                                <span className="flex-1 text-left uppercase tracking-wider">Spokes</span>
                                <span className={`transition-transform duration-200 ${spokesExpanded ? "" : "-rotate-90"}`}>▾</span>
                            </>
                        )}
                    </button>

                    {spokesExpanded && !isCollapsed && (
                        <div className="mt-1 px-2 space-y-0.5">
                            {spokes.length === 0 ? (
                                <div className="px-3 py-2 text-xs text-gray-600 italic">
                                    No spokes yet
                                </div>
                            ) : (
                                spokes.map((spoke) => {
                                    const isActive = pathname.startsWith(spoke.path);
                                    const isHovered = hoveredSpoke === spoke.name;
                                    return (
                                        <div
                                            key={spoke.name}
                                            className="relative"
                                            onMouseEnter={() => setHoveredSpoke(spoke.name)}
                                            onMouseLeave={() => {
                                                if (menuOpen !== spoke.name) setHoveredSpoke(null);
                                            }}
                                        >
                                            <Link
                                                href={spoke.path}
                                                className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${isActive
                                                    ? "bg-gray-800 text-white"
                                                    : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                                                    }`}
                                            >
                                                <span className="truncate flex-1">{spoke.display_name || spoke.name}</span>
                                            </Link>

                                            {/* Three-dot menu */}
                                            {(isHovered || menuOpen === spoke.name) && (
                                                <button
                                                    onClick={(e) => {
                                                        e.preventDefault();
                                                        e.stopPropagation();
                                                        setMenuOpen(menuOpen === spoke.name ? null : spoke.name);
                                                    }}
                                                    className="absolute right-1 top-1/2 -translate-y-1/2 p-1.5 text-gray-500 hover:text-white hover:bg-gray-700 rounded transition-colors"
                                                >
                                                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                                        <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                                                    </svg>
                                                </button>
                                            )}

                                            {/* Dropdown Menu */}
                                            {menuOpen === spoke.name && (
                                                <div
                                                    ref={menuRef}
                                                    className="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[140px] z-50"
                                                >
                                                    <Link
                                                        href={`/spokes/${spoke.name}/settings`}
                                                        className="flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                        onClick={() => setMenuOpen(null)}
                                                    >
                                                        Settings
                                                    </Link>
                                                    <button
                                                        onClick={() => handleExportChat(spoke.name)}
                                                        className="w-full flex items-center px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
                                                    >
                                                        Export Chat
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })
                            )}

                            {/* New Spoke Button */}
                            <Link
                                href="/spokes"
                                className="flex items-center px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-800/50 hover:text-gray-300 transition-colors"
                            >
                                <span className="mr-2">+</span>
                                <span>New Spoke</span>
                            </Link>
                        </div>
                    )}
                </div>
            </nav>

            {/* Footer */}
            <div className="p-2 border-t border-gray-800/50">
                <Link
                    href="/settings"
                    className={`flex items-center px-3 py-2 rounded-lg text-sm transition-colors ${isCollapsed ? "justify-center" : ""} ${pathname === "/settings"
                        ? "bg-gray-800 text-white"
                        : "text-gray-400 hover:bg-gray-800/50 hover:text-white"
                        }`}
                    title={isCollapsed ? "Settings" : ""}
                >
                    {isCollapsed ? "⚙" : "Settings"}
                </Link>
            </div>
        </div>
    );
}
