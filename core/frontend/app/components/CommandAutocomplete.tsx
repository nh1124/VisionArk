"use client";

import { useState, useEffect, useRef } from "react";

// Debounce hook to prevent excessive re-renders during typing
const useDebounce = (value: string, delay: number) => {
    const [debouncedValue, setDebouncedValue] = useState(value);
    useEffect(() => {
        const handler = setTimeout(() => setDebouncedValue(value), delay);
        return () => clearTimeout(handler);
    }, [value, delay]);
    return debouncedValue;
};

interface Command {
    name: string;
    description: string;
    usage: string;
}

interface CommandAutocompleteProps {
    value: string;
    onChange: (value: string) => void;
    onSubmit: () => void;
    placeholder: string;
    context: "hub" | "spoke";
    disabled?: boolean;
}

export default function CommandAutocomplete({
    value,
    onChange,
    onSubmit,
    placeholder,
    context,
    disabled = false
}: CommandAutocompleteProps) {
    const [commands, setCommands] = useState<Command[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Debounce input value to reduce filtering frequency (150ms delay)
    const debouncedValue = useDebounce(value, 150);

    // Define available commands based on context
    const hubCommands: Command[] = [
        { name: "/create_spoke", description: "Create a new Spoke", usage: "/create_spoke <name>" },
        { name: "/create_task", description: "Create a new LBS task", usage: '/create_task name="Task" spoke="spoke" workload=5.0' },
        { name: "/check_inbox", description: "Check pending inbox messages", usage: "/check_inbox" },
        { name: "/send_message", description: "Send message to a Spoke", usage: "/send_message <spoke_name> <message>" },
        { name: "/kill", description: "Delete a Spoke permanently", usage: "/kill <spoke_name>" },
        { name: "/archive", description: "Archive Hub or Spoke conversation", usage: "/archive [spoke_name]" },
        { name: "/move", description: "Move to Hub or Spoke page", usage: "/move [node_name]" },
        { name: "/mv", description: "Move to Hub or Spoke page (alias)", usage: "/mv [node_name]" },
    ];

    const spokeCommands: Command[] = [
        { name: "/create_task", description: "Create a new LBS task", usage: '/create_task name="Task" spoke="spoke" workload=5.0' },
        { name: "/share", description: "Share update with Hub", usage: "/share [message]" },
        { name: "/complete", description: "Mark task as complete", usage: "/complete <task_id> [notes]" },
        { name: "/report", description: "Generate progress report", usage: "/report [summary]" },
        { name: "/kill", description: "Delete this Spoke (self-destruct)", usage: "/kill" },
        { name: "/archive", description: "Archive this conversation", usage: "/archive" },
        { name: "/move", description: "Move to Hub or Spoke page", usage: "/move [node_name]" },
        { name: "/mv", description: "Move to Hub or Spoke page (alias)", usage: "/mv [node_name]" },
    ];

    const availableCommands = context === "hub" ? hubCommands : spokeCommands;

    // Filter commands based on debounced input (reduces filtering on every keystroke)
    useEffect(() => {
        if (debouncedValue.startsWith("/") && debouncedValue.length > 1) {
            const query = debouncedValue.toLowerCase();
            const filtered = availableCommands.filter(cmd =>
                cmd.name.toLowerCase().startsWith(query) ||
                cmd.description.toLowerCase().includes(query.slice(1))
            );
            setCommands(filtered);
            setShowDropdown(filtered.length > 0);
            setSelectedIndex(0);
        } else if (debouncedValue === "/") {
            setCommands(availableCommands);
            setShowDropdown(true);
            setSelectedIndex(0);
        } else {
            setShowDropdown(false);
        }
    }, [debouncedValue, context]);

    // Handle keyboard navigation
    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (!showDropdown) {
            if (e.key === "Enter") {
                e.preventDefault();
                onSubmit();
            }
            return;
        }

        switch (e.key) {
            case "ArrowDown":
                e.preventDefault();
                setSelectedIndex(prev => (prev + 1) % commands.length);
                break;
            case "ArrowUp":
                e.preventDefault();
                setSelectedIndex(prev => (prev - 1 + commands.length) % commands.length);
                break;
            case "Enter":
                e.preventDefault();
                if (commands[selectedIndex]) {
                    onChange(commands[selectedIndex].name + " ");
                    setShowDropdown(false);
                    inputRef.current?.focus();
                } else {
                    onSubmit();
                }
                break;
            case "Escape":
                setShowDropdown(false);
                break;
        }
    };

    // Handle command selection
    const selectCommand = (command: Command) => {
        onChange(command.name + " ");
        setShowDropdown(false);
        inputRef.current?.focus();
    };

    return (
        <div className="relative flex-1">
            <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 transition-colors"
                disabled={disabled}
            />

            {/* Command Dropdown */}
            {showDropdown && (
                <div
                    ref={dropdownRef}
                    className="absolute bottom-full left-0 right-0 mb-2 bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-h-64 overflow-y-auto z-50"
                >
                    {commands.map((cmd, idx) => (
                        <div
                            key={cmd.name}
                            onClick={() => selectCommand(cmd)}
                            className={`px-4 py-3 cursor-pointer transition-colors ${idx === selectedIndex
                                ? "bg-purple-500/20 border-l-4 border-purple-500"
                                : "hover:bg-gray-700"
                                }`}
                        >
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="font-mono text-purple-400">{cmd.name}</div>
                                    <div className="text-xs text-gray-400 mt-1">{cmd.description}</div>
                                </div>
                                <div className="text-xs text-gray-500 font-mono">{cmd.usage}</div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
