"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjects } from "@/hooks/useProjects";
import { useModel, MODEL_OPTIONS, getModelDisplayName } from "@/lib/ModelContext";
import { X, Home, LayoutDashboard, ListTodo, MessageSquare, Plus, Settings, ChevronDown, Check } from "lucide-react";

interface MobileSidebarProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
    const pathname = usePathname();
    const { projects } = useProjects();
    const { selectedModel, setSelectedModel } = useModel();
    const [showModelList, setShowModelList] = React.useState(false);

    const navItems = [
        { name: "Dashboard", path: "/dashboard", icon: <LayoutDashboard size={20} /> },
        { name: "Tasks", path: "/tasks", icon: <ListTodo size={20} /> },
        { name: "Projects", path: "/projects", icon: <MessageSquare size={20} /> },
    ];

    if (!isOpen) return null;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] animate-in fade-in duration-300"
                onClick={onClose}
            />

            {/* Sidebar Content */}
            <div className="fixed inset-y-0 left-0 w-[280px] bg-gray-950 border-r border-gray-800 z-[101] shadow-2xl flex flex-col animate-in slide-in-from-left duration-300 ease-out">
                {/* Header */}
                <div className="h-16 border-b border-gray-800 flex items-center justify-between px-6 flex-shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center font-bold text-white text-sm">
                            V
                        </div>
                        <span className="font-semibold text-white">Vision Ark</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-gray-400 hover:text-white rounded-lg transition-colors"
                    >
                        <X size={24} />
                    </button>
                </div>

                {/* Navigation */}
                <div className="flex-1 overflow-y-auto py-6 px-4 no-scrollbar">
                    <div className="space-y-1">
                        {navItems.map((item) => {
                            const isActive = pathname === item.path;
                            return (
                                <Link
                                    key={item.path}
                                    href={item.path}
                                    onClick={onClose}
                                    className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-all ${isActive
                                        ? "bg-blue-600/10 text-blue-400 font-medium"
                                        : "text-gray-400 hover:bg-gray-900 hover:text-gray-200"
                                        }`}
                                >
                                    {item.icon}
                                    <span>{item.name}</span>
                                </Link>
                            );
                        })}
                    </div>

                    <div className="mt-8">
                        <div className="px-4 mb-4 flex items-center justify-between">
                            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-gray-600">
                                Projects
                            </span>
                            <Link
                                href="/projects"
                                onClick={onClose}
                                className="p-1 text-gray-500 hover:text-cyan-400 transition-colors"
                            >
                                <Plus size={16} />
                            </Link>
                        </div>
                        <div className="space-y-1">
                            {projects.map((project) => {
                                const isActive = pathname === project.path || pathname.startsWith(project.path + "/");
                                return (
                                    <Link
                                        key={project.id}
                                        href={project.path}
                                        onClick={onClose}
                                        className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-all ${isActive
                                            ? "bg-cyan-600/10 text-cyan-400 font-medium"
                                            : "text-gray-400 hover:bg-gray-900 hover:text-gray-200"
                                            }`}
                                    >
                                        <div className="w-5 h-5 flex items-center justify-center">
                                            <span className="text-xs">💼</span>
                                        </div>
                                        <span className="truncate">{project.display_name || project.name}</span>
                                    </Link>
                                );
                            })}
                        </div>
                    </div>


                </div>

                {/* Footer */}
                <div className="p-4 border-t border-gray-800">
                    <Link
                        href="/settings"
                        onClick={onClose}
                        className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-all ${pathname === "/settings"
                            ? "bg-gray-800 text-white font-medium"
                            : "text-gray-400 hover:bg-gray-900 hover:text-gray-200"
                            }`}
                    >
                        <Settings size={20} />
                        <span>Settings</span>
                    </Link>
                </div>
            </div>
        </>
    );
}
