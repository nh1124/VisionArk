"use client";

import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";
import { useRouter } from "next/navigation";

interface HubSuggestion {
    id: string;
    type: string;
    severity: string;
    title: string;
    description: string;
    action_label: string;
    action_type: string;
    action_data: Record<string, any>;
}

interface HubSuggestionBannerProps {
    onRefresh?: () => void;
}

export default function HubSuggestionBanner({ onRefresh }: HubSuggestionBannerProps) {
    const [suggestions, setSuggestions] = useState<HubSuggestion[]>([]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [dismissed, setDismissed] = useState<Set<string>>(new Set());
    const [loading, setLoading] = useState(true);
    const router = useRouter();

    useEffect(() => {
        fetchSuggestions();
    }, []);

    const fetchSuggestions = async () => {
        try {
            setLoading(true);
            const response = await apiFetch("/api/hub/suggestions");
            if (response.ok) {
                const data = await response.json();
                setSuggestions(data.suggestions || []);
            }
        } catch (error) {
            console.error("Failed to fetch suggestions:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleAction = (suggestion: HubSuggestion) => {
        switch (suggestion.action_type) {
            case "navigate":
                const route = suggestion.action_data.route;
                if (suggestion.action_data.view) {
                    // For hub inbox, navigate to hub with view param
                    router.push(`${route}?view=${suggestion.action_data.view}`);
                } else {
                    router.push(route);
                }
                break;
            case "reschedule":
            case "archive":
                // These would trigger specific modals - for now just navigate
                router.push(suggestion.action_data.route || "/tasks");
                break;
            case "dismiss":
                handleDismiss(suggestion.id);
                break;
        }
    };

    const handleDismiss = (id: string) => {
        setDismissed(prev => new Set([...prev, id]));
        // Move to next suggestion if available
        const remaining = suggestions.filter(s => !dismissed.has(s.id) && s.id !== id);
        if (remaining.length > 0 && currentIndex >= remaining.length) {
            setCurrentIndex(Math.max(0, remaining.length - 1));
        }
    };

    const getSeverityStyles = (severity: string) => {
        switch (severity) {
            case "critical":
                return {
                    bg: "bg-gradient-to-r from-red-900/30 to-red-800/20",
                    border: "border-red-500/40",
                    icon: "🚨",
                    iconBg: "bg-red-500/20",
                    iconColor: "text-red-400"
                };
            case "warning":
                return {
                    bg: "bg-gradient-to-r from-amber-900/30 to-amber-800/20",
                    border: "border-amber-500/40",
                    icon: "⚠️",
                    iconBg: "bg-amber-500/20",
                    iconColor: "text-amber-400"
                };
            default:
                return {
                    bg: "bg-gradient-to-r from-purple-900/20 to-blue-900/20",
                    border: "border-purple-500/30",
                    icon: "💡",
                    iconBg: "bg-purple-500/20",
                    iconColor: "text-purple-400"
                };
        }
    };

    const getTypeIcon = (type: string) => {
        switch (type) {
            case "overdue_tasks": return "📅";
            case "inactive_spoke": return "🗂️";
            case "high_load": return "📊";
            case "pending_inbox": return "📥";
            default: return "💬";
        }
    };

    // Filter out dismissed suggestions
    const visibleSuggestions = suggestions.filter(s => !dismissed.has(s.id));

    if (loading) {
        return null; // Don't show loading state, just hide
    }

    if (visibleSuggestions.length === 0) {
        return null;
    }

    const currentSuggestion = visibleSuggestions[currentIndex] || visibleSuggestions[0];
    if (!currentSuggestion) return null;

    const styles = getSeverityStyles(currentSuggestion.severity);

    return (
        <div className="mb-6 animate-in slide-in-from-top-4 duration-300">
            <div className={`${styles.bg} ${styles.border} border-2 rounded-2xl p-5 backdrop-blur-sm relative overflow-hidden`}>
                {/* Background glow effect */}
                <div className={`absolute -right-10 -top-10 w-40 h-40 rounded-full blur-[80px] opacity-20 ${currentSuggestion.severity === 'critical' ? 'bg-red-500' :
                        currentSuggestion.severity === 'warning' ? 'bg-amber-500' :
                            'bg-purple-500'
                    }`} />

                <div className="relative flex items-center gap-5">
                    {/* Icon */}
                    <div className={`flex-shrink-0 w-12 h-12 ${styles.iconBg} rounded-xl flex items-center justify-center`}>
                        <span className="text-2xl">{getTypeIcon(currentSuggestion.type)}</span>
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                            <h3 className="font-bold text-white tracking-tight">
                                {currentSuggestion.title}
                            </h3>
                            {visibleSuggestions.length > 1 && (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-gray-800/50 text-gray-400">
                                    {currentIndex + 1}/{visibleSuggestions.length}
                                </span>
                            )}
                        </div>
                        <p className="text-sm text-gray-400 line-clamp-2">
                            {currentSuggestion.description}
                        </p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                        {/* Navigation arrows for multiple suggestions */}
                        {visibleSuggestions.length > 1 && (
                            <div className="flex items-center gap-1 mr-2">
                                <button
                                    onClick={() => setCurrentIndex(i => Math.max(0, i - 1))}
                                    disabled={currentIndex === 0}
                                    className="p-1.5 rounded-lg bg-gray-800/50 hover:bg-gray-700/50 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                    </svg>
                                </button>
                                <button
                                    onClick={() => setCurrentIndex(i => Math.min(visibleSuggestions.length - 1, i + 1))}
                                    disabled={currentIndex >= visibleSuggestions.length - 1}
                                    className="p-1.5 rounded-lg bg-gray-800/50 hover:bg-gray-700/50 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
                                >
                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                </button>
                            </div>
                        )}

                        {/* Action Button */}
                        <button
                            onClick={() => handleAction(currentSuggestion)}
                            className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${currentSuggestion.severity === 'critical'
                                    ? 'bg-red-600 hover:bg-red-500 text-white'
                                    : currentSuggestion.severity === 'warning'
                                        ? 'bg-amber-600 hover:bg-amber-500 text-white'
                                        : 'bg-purple-600 hover:bg-purple-500 text-white'
                                }`}
                        >
                            {currentSuggestion.action_label}
                        </button>

                        {/* Dismiss Button */}
                        <button
                            onClick={() => handleDismiss(currentSuggestion.id)}
                            className="p-2 rounded-lg bg-gray-800/30 hover:bg-gray-700/50 text-gray-500 hover:text-gray-300 transition-all"
                            title="Dismiss"
                        >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
