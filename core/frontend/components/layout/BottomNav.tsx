"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, ListTodo, MessageSquare, Settings } from "lucide-react";

export default function BottomNav() {
    const pathname = usePathname();

    const navItems = [
        { name: "Dashboard", path: "/dashboard", icon: <LayoutDashboard size={20} /> },
        { name: "Tasks", path: "/tasks", icon: <ListTodo size={20} /> },
        { name: "Projects", path: "/projects", icon: <MessageSquare size={20} /> },
        { name: "Settings", path: "/settings", icon: <Settings size={20} /> },
    ];

    return (
        <nav className="h-16 bg-gray-950/80 backdrop-blur-xl border-t border-gray-800 flex items-center justify-around px-2 pb-safe z-30 flex-shrink-0">
            {navItems.map((item) => {
                const isActive = pathname === item.path || (item.path !== "/" && pathname.startsWith(item.path));
                return (
                    <Link
                        key={item.path}
                        href={item.path}
                        className={`flex flex-col items-center justify-center gap-1 w-16 transition-all ${isActive ? "text-blue-400" : "text-gray-500 hover:text-gray-300"
                            }`}
                    >
                        <div className={`p-1 rounded-xl transition-all ${isActive ? "bg-blue-600/10" : ""}`}>
                            {item.icon}
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-widest leading-none">
                            {item.name}
                        </span>
                    </Link>
                );
            })}
        </nav>
    );
}
