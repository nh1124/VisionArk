"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

interface ModelContextType {
    selectedModel: string;
    setSelectedModel: (model: string) => void;
    configuredProviders: string[];
    setConfiguredProviders: (providers: string[]) => void;
}

export interface ModelOption {
    id: string;
    name: string;
}

export interface ModelGroup {
    group: string;
    provider: string;
    models: ModelOption[];
}

export const MODEL_OPTIONS: ModelGroup[] = [
    {
        group: "Gemini", provider: "gemini", models: [
            { id: "gemini-3-pro-preview", name: "Gemini 3 Pro" },
            { id: "gemini-3-flash-preview", name: "Gemini 3 Flash" },
            { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro" },
            { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash" },
        ]
    },
    {
        group: "OpenAI", provider: "openai", models: [
            { id: "openai:gpt-4.1", name: "GPT-4.1" },
            { id: "openai:gpt-4.1-mini", name: "GPT-4.1 Mini" },
            { id: "openai:gpt-4.1-nano", name: "GPT-4.1 Nano" },
            { id: "openai:o4-mini", name: "o4 Mini" },
        ]
    },
    {
        group: "Claude", provider: "anthropic", models: [
            { id: "anthropic:claude-sonnet-4-20250514", name: "Claude Sonnet 4" },
            { id: "anthropic:claude-3-5-haiku-latest", name: "Claude 3.5 Haiku" },
        ]
    },
];

export const getModelDisplayName = (modelId: string): string => {
    for (const group of MODEL_OPTIONS) {
        for (const m of group.models) {
            if (m.id === modelId) return m.name;
        }
    }
    // Fallback: format the model ID nicely
    const clean = modelId.includes(":") ? modelId.split(":")[1] : modelId;
    return clean.split("-").map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
};

export const getProviderForModel = (modelId: string): string => {
    for (const group of MODEL_OPTIONS) {
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
    const [selectedModel, setSelectedModel] = useState("gemini-3-pro-preview");
    const [configuredProviders, setConfiguredProviders] = useState<string[]>([]);

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
