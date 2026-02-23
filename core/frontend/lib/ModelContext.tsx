"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

interface ModelContextType {
    selectedModel: string;
    setSelectedModel: (model: string) => void;
}

export const MODEL_OPTIONS = [
    { group: "Gemini 3 (Preview)", models: ["gemini-3-pro-preview", "gemini-3-flash-preview"] },
    { group: "Gemini 2.5", models: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-preview", "gemini-2.5-flash-lite", "gemini-2.5-flash-lite-preview"] },
];

export const getModelDisplayName = (model: string) => {
    const parts = model.split("-");
    if (parts.length >= 3) {
        return parts.slice(1).join(" ").replace(/\b\w/g, c => c.toUpperCase());
    }
    return model;
};

const ModelContext = createContext<ModelContextType | undefined>(undefined);

export function ModelProvider({ children }: { children: React.ReactNode }) {
    // Default model
    const [selectedModel, setSelectedModel] = useState("gemini-3-pro-preview");

    // Load from localStorage if available
    useEffect(() => {
        const savedModel = localStorage.getItem("vision-ark-selected-model");
        if (savedModel) {
            setSelectedModel(savedModel);
        }
    }, []);

    // Save to localStorage when changed
    const handleSetSelectedModel = (model: string) => {
        setSelectedModel(model);
        localStorage.setItem("vision-ark-selected-model", model);
    };

    return (
        <ModelContext.Provider value={{ selectedModel, setSelectedModel: handleSetSelectedModel }}>
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
