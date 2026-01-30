"use client";

import React, { useState, useEffect, useRef } from "react";
import { Bell, Check, ExternalLink, X } from "lucide-react";
import { useNotification } from "@/lib/NotificationContext";
import { formatDistanceToNow } from "date-fns";

interface NotificationItem {
    id: string;
    type: "info" | "success" | "warning" | "error";
    title: string;
    content: string;
    link?: string;
    is_read: boolean;
    created_at: string;
}

export function NotificationBell() {
    const { unreadCount, refreshUnreadCount } = useNotification();
    const [isOpen, setIsOpen] = useState(false);
    const [notifications, setNotifications] = useState<NotificationItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    const fetchNotifications = async () => {
        setIsLoading(true);
        try {
            const token = localStorage.getItem("atmos_access_token");
            const res = await fetch("/api/notifications/", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setNotifications(data.notifications);
            }
        } catch (err) {
            console.error("Failed to fetch notifications:", err);
        } finally {
            setIsLoading(false);
        }
    };

    const markAsRead = async (id: string) => {
        try {
            const token = localStorage.getItem("atmos_access_token");
            await fetch(`/api/notifications/${id}/read`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
            setNotifications((prev) =>
                prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
            );
            refreshUnreadCount();
        } catch (err) {
            console.error("Failed to mark as read:", err);
        }
    };

    const markAllAsRead = async () => {
        try {
            const token = localStorage.getItem("atmos_access_token");
            await fetch("/api/notifications/read-all", {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
            setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
            refreshUnreadCount();
        } catch (err) {
            console.error("Failed to mark all as read:", err);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchNotifications();
        }
    }, [isOpen]);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const getIcon = (type: string) => {
        switch (type) {
            case "success": return <div className="w-2 h-2 rounded-full bg-emerald-500" />;
            case "error": return <div className="w-2 h-2 rounded-full bg-rose-500" />;
            case "warning": return <div className="w-2 h-2 rounded-full bg-amber-500" />;
            default: return <div className="w-2 h-2 rounded-full bg-blue-500" />;
        }
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors relative"
            >
                <Bell size={20} />
                {unreadCount > 0 && (
                    <span className="absolute top-1 right-1 w-4 h-4 bg-rose-500 text-white text-[10px] flex items-center justify-center rounded-full animate-pulse">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <div className="absolute right-0 mt-2 w-80 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden flex flex-col max-h-[480px]">
                    <div className="p-4 border-b border-slate-700 flex items-center justify-between bg-slate-900/50 backdrop-blur-sm sticky top-0">
                        <h3 className="text-sm font-semibold text-white">Notifications</h3>
                        {unreadCount > 0 && (
                            <button
                                onClick={markAllAsRead}
                                className="text-xs text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
                            >
                                <Check size={12} />
                                Mark all read
                            </button>
                        )}
                    </div>

                    <div className="overflow-y-auto flex-1">
                        {isLoading ? (
                            <div className="p-8 text-center text-slate-500 text-sm">
                                Loading notifications...
                            </div>
                        ) : notifications.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">
                                No notifications yet.
                            </div>
                        ) : (
                            <div className="divide-y divide-slate-800">
                                {notifications.map((notif) => (
                                    <div
                                        key={notif.id}
                                        className={`p-4 hover:bg-slate-800/50 transition-colors group relative ${!notif.is_read ? 'bg-blue-500/5' : ''}`}
                                    >
                                        <div className="flex gap-3">
                                            <div className="mt-1.5 flex-shrink-0">
                                                {getIcon(notif.type)}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between mb-0.5">
                                                    <span className="text-xs font-medium text-white block truncate pr-4">
                                                        {notif.title}
                                                    </span>
                                                    <span className="text-[10px] text-slate-500 whitespace-nowrap">
                                                        {formatDistanceToNow(new Date(notif.created_at), { addSuffix: true })}
                                                    </span>
                                                </div>
                                                <p className="text-xs text-slate-400 line-clamp-2 mb-2 leading-relaxed">
                                                    {notif.content}
                                                </p>
                                                {notif.link && (
                                                    <a
                                                        href={notif.link}
                                                        className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-1 inline-flex"
                                                    >
                                                        <ExternalLink size={10} />
                                                        View Details
                                                    </a>
                                                )}
                                            </div>
                                        </div>
                                        {!notif.is_read && (
                                            <button
                                                onClick={() => markAsRead(notif.id)}
                                                className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 p-1 bg-slate-700 rounded hover:bg-slate-600 transition-all"
                                                title="Mark as read"
                                            >
                                                <Check size={10} className="text-white" />
                                            </button>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="p-3 border-t border-slate-700 bg-slate-900/50 text-center sticky bottom-0">
                        <button className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors uppercase tracking-wider font-semibold">
                            See all history
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
