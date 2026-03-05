"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface ModelContextType {
    selectedModel: string;
    setSelectedModel: (model: string) => void;
    configuredProviders: string[];
    setConfiguredProviders: (providers: string[]) => void;
    modelGroups: ModelGroup[];
    defaultModel: string;
    isLoadingModels: boolean;
}

export interface ModelOption {
    id: string;
    name: string;
    status?: string;
    priority?: number;
}

export interface ModelGroup {
    group: string;
    provider: string;
    models: ModelOption[];
}

// Fallback used when API is unavailable
const FALLBACK_GROUPS: ModelGroup[] = [
    {
        group: "Gemini", provider: "gemini", models: [
            { id: "gemini-3.1-pro-preview", name: "Gemini 3.1 Pro Preview" },
        ]
    },
];
const FALLBACK_DEFAULT = "gemini-3.1-pro-preview";

export const getModelDisplayName = (modelId: string, groups: ModelGroup[] = FALLBACK_GROUPS): string => {
    for (const group of groups) {
        for (const m of group.models) {
            if (m.id === modelId) return m.name;
        }
    }
    // Fallback: format the model ID nicely
    const clean = modelId.includes(":") ? modelId.split(":")[1] : modelId;
    return clean.split("-").map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
};

export const getProviderForModel = (modelId: string, groups: ModelGroup[] = FALLBACK_GROUPS): string => {
    for (const group of groups) {
        for (const m of group.models) {
            if (m.id === modelId) return group.provider;
        }
    }
    if (modelId.startsWith("openai:") || modelId.startsWith("gpt-") || modelId.startsWith("o4-")) return "openai";
    if (modelId.startsWith("anthropic:") || modelId.startsWith("claude-")) return "anthropic";
    return "gemini";
};

export const getProviderDisplayName = (provider: string): string => {
    const map: Record<string, string> = {
        gemini: "Gemini",
        openai: "OpenAI",
        anthropic: "Claude",
    };
    return map[provider] || provider;
};

const ModelContext = createContext<ModelContextType | undefined>(undefined);

export function ModelProvider({ children }: { children: React.ReactNode }) {
    const [selectedModel, setSelectedModel] = useState(FALLBACK_DEFAULT);
    const [configuredProviders, setConfiguredProviders] = useState<string[]>([]);
    const [modelGroups, setModelGroups] = useState<ModelGroup[]>(FALLBACK_GROUPS);
    const [defaultModel, setDefaultModel] = useState(FALLBACK_DEFAULT);
    const [isLoadingModels, setIsLoadingModels] = useState(true);

    // Fetch model catalog from backend
    useEffect(() => {
        apiFetch("/api/llm/models")
            .then(r => r.json())
            .then((data: { groups: ModelGroup[]; default_model: string }) => {
                setModelGroups(data.groups);
                setDefaultModel(data.default_model);
            })
            .catch(() => { /* keep fallback */ })
            .finally(() => setIsLoadingModels(false));
    }, []);

    // Load saved model from localStorage
    useEffect(() => {
        const savedModel = localStorage.getItem("vision-ark-selected-model");
        if (savedModel) {
            setSelectedModel(savedModel);
        }
    }, []);

    const handleSetSelectedModel = (model: string) => {
        setSelectedModel(model);
        localStorage.setItem("vision-ark-selected-model", model);
    };

    return (
        <ModelContext.Provider value={{
            selectedModel,
            setSelectedModel: handleSetSelectedModel,
            configuredProviders,
            setConfiguredProviders,
            modelGroups,
            defaultModel,
            isLoadingModels,
        }}>
            {children}
        </ModelContext.Provider>
    );
}

export function useModel() {
    const context = useContext(ModelContext);
    if (context === undefined) {
        throw new Error("useModel must be used within a ModelProvider");
    }
    return context;
}
