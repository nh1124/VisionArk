
"use client";

import { useState, useEffect } from "react";
import { apiJson } from "@/lib/api";
import Link from "next/link";

export default function SystemStatus() {
    const [status, setStatus] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        checkStatus();
    }, []);

    const checkStatus = async () => {
        try {
            const data = await apiJson<any>("/api/settings/status");
            setStatus(data);
        } catch (err) {
            console.error("Failed to check status", err);
        } finally {
            setLoading(false);
        }
    };

    if (loading || !status) return null;
    if (status.all_mandatory_met) {
        return (
            <div className="flex items-center space-x-1.5 px-3 py-1 bg-green-500/10 text-green-400 rounded-full border border-green-500/20 text-xs font-medium">
                <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span>
                <span>System Ready</span>
            </div>
        );
    }

    const missing = [];
    if (!status.details.llm?.configured) missing.push("LLM");
    if (!status.details.lbs?.configured) missing.push("LBS");
    if (!status.details.knowledge_core?.configured) missing.push("KC");

    return (
        <Link href="/settings" className="flex items-center space-x-2 px-3 py-1 bg-red-500/10 text-red-400 rounded-full border border-red-500/20 text-xs font-medium hover:bg-red-500/20 transition-all cursor-pointer">
            <span className="w-1.5 h-1.5 bg-red-500 rounded-full"></span>
            <span>Update Required: {missing.join(", ")}</span>
        </Link>
    );
}
