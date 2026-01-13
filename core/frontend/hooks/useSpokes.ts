"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";

export interface SpokeInfo {
    name: string;
    path: string;
    display_name?: string;
}

/**
 * Custom hook to load and manage the list of available spokes.
 */
export function useSpokes() {
    const [spokes, setSpokes] = useState<SpokeInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadSpokes = useCallback(async () => {
        setLoading(true);
        setError(null);
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
        } catch (err) {
            console.error("Failed to load spokes:", err);
            setError("Failed to load spokes");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadSpokes();
    }, [loadSpokes]);

    return { spokes, loading, error, refreshSpokes: loadSpokes };
}
