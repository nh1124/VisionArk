"use client";

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api";

export interface ProjectInfo {
    name: string;
    node_id: string;
    display_name?: string;
    path: string;
}

/**
 * Custom hook to load and manage the list of available projects.
 */
export function useProjects() {
    const [projects, setProjects] = useState<ProjectInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadProjects = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await apiFetch("/api/agents/project/list");
            const data = await response.json();

            if (data && data.projects && Array.isArray(data.projects)) {
                // Sorting alphabetically
                const sortedProjects = data.projects.sort((a: any, b: any) =>
                    a.name.localeCompare(b.name)
                );

                setProjects(sortedProjects.map((p: any) => ({
                    name: p.name,
                    node_id: p.node_id,
                    display_name: p.display_name || p.name,
                    path: `/projects/${p.name}`
                })));
            } else {
                setProjects([]);
            }
        } catch (err) {
            console.error("Failed to load projects:", err);
            setError("Failed to load projects");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadProjects();
    }, [loadProjects]);

    return { projects, loading, error, refreshProjects: loadProjects };
}
