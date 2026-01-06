"use client";

import { useState, useEffect, useRef, KeyboardEvent } from "react";
import { apiFetch } from "@/lib/api";

interface CommandSuggestion {
    name: string;
    description: string;
    contexts: string[];
}

interface CommandInputProps {
    context: "hub" | "spoke";
    spokeName?: string;
    onCommandExecuted?: (result: any) => void;
    placeholder?: string;
}

export default function CommandInput({
    context,
    spokeName,
    onCommandExecuted,
    placeholder = "Type / for commands or chat normally...",
}: CommandInputProps) {
    const [input, setInput] = useState("");
    const [suggestions, setSuggestions] = useState<CommandSuggestion[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [allCommands, setAllCommands] = useState<CommandSuggestion[]>([]);
    const inputRef = useRef<HTMLInputElement>(null);

    // Load available commands
    useEffect(() => {
        apiFetch(`/api/commands/list?context=${context}`)
            .then((res) => res.json())
            .then((data) => {
                setAllCommands(data.commands);
            })
            .catch(console.error);
    }, [context]);

    //Filter suggestions as user types
    useEffect(() => {
        if (input.startsWith("/")) {
            const command = input.slice(1).toLowerCase();
            const filtered = allCommands.filter((cmd) =>
                cmd.name.toLowerCase().startsWith(command)
            );
            setSuggestions(filtered);
            setShowSuggestions(filtered.length > 0);
            setSelectedIndex(0);
        } else {
            setShowSuggestions(false);
        }
    }, [input, allCommands]);

    const executeCommand = async (commandText: string) => {
        try {
            const response = await apiFetch("/api/commands/execute", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: commandText,
                    context,
                    spoke_name: spokeName,
                }),
            });

            const result = await response.json();

            if (onCommandExecuted) {
                onCommandExecuted(result);
            }

            setInput("");
            setShowSuggestions(false);
        } catch (error) {
            console.error("Command execution failed:", error);
            if (onCommandExecuted) {
                onCommandExecuted({
                    success: false,
                    message: "Failed to execute command",
                });
            }
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (!showSuggestions) {
            if (e.key === "Enter" && input.trim()) {
                if (input.startsWith("/")) {
                    executeCommand(input);
                } else {
                    // Regular chat message - pass to parent
                    if (onCommandExecuted) {
                        onCommandExecuted({ isMessage: true, text: input });
                    }
                    setInput("");
                }
            }
            return;
        }

        // Handle autocomplete navigation
        switch (e.key) {
            case "ArrowDown":
                e.preventDefault();
                setSelectedIndex((prev) =>
                    prev < suggestions.length - 1 ? prev + 1 : 0
                );
                break;
            case "ArrowUp":
                e.preventDefault();
                setSelectedIndex((prev) =>
                    prev > 0 ? prev - 1 : suggestions.length - 1
                );
                break;
            case "Enter":
                e.preventDefault();
                if (suggestions[selectedIndex]) {
                    const selected = "/" + suggestions[selectedIndex].name;
                    setInput(selected + " ");
                    setShowSuggestions(false);
                    inputRef.current?.focus();
                }
                break;
            case "Escape":
                setShowSuggestions(false);
                break;
        }
    };

    return (
        <div className="relative">
            {/* Command suggestions dropdown */}
            {showSuggestions && (
                <div className="absolute bottom-full left-0 right-0 mb-2 bg-gray-800 border border-gray-700 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                    {suggestions.map((cmd, idx) => (
                        <div
                            key={cmd.name}
                            className={`px-4 py-3 cursor-pointer transition-colors ${idx === selectedIndex
                                ? "bg-blue-500/20 border-l-4 border-blue-500"
                                : "hover:bg-gray-700"
                                }`}
                            onClick={() => {
                                setInput("/" + cmd.name + " ");
                                setShowSuggestions(false);
                                inputRef.current?.focus();
                            }}
                        >
                            <div className="flex items-center justify-between">
                                <span className="font-mono text-blue-400">/{cmd.name}</span>
                                <span className="text-xs text-gray-500">
                                    {cmd.contexts.join(", ")}
                                </span>
                            </div>
                            <p className="text-sm text-gray-400 mt-1">{cmd.description}</p>
                        </div>
                    ))}
                </div>
            )}

            {/* Input field */}
            <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500 transition-colors font-mono"
            />

            {/* Hint */}
            {input.startsWith("/") && !showSuggestions && (
                <p className="text-xs text-gray-500 mt-2">
                    ⌨️ Press Enter to execute command
                </p>
            )}
        </div>
    );
}
