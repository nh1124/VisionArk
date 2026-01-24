import { useState, useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import { apiFetch } from "@/lib/api";

// ... (useDebounce remains same)
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
    context: "global" | "project";
    disabled?: boolean;
    showInput?: boolean;
}

export interface CommandAutocompleteHandle {
    handleKeyDown: (e: React.KeyboardEvent) => boolean;
}

const CommandAutocomplete = forwardRef<CommandAutocompleteHandle, CommandAutocompleteProps>(({
    value,
    onChange,
    onSubmit,
    placeholder,
    context, // 'global' (dashboard) or 'project'
    disabled = false,
    showInput = true
}, ref) => {
    const [availableCommands, setAvailableCommands] = useState<Command[]>([]);
    const [filteredCommands, setFilteredCommands] = useState<Command[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Debounce input value to reduce filtering frequency (50ms delay)
    const debouncedValue = useDebounce(value, 50);

    // Fetch commands from API on mount
    useEffect(() => {
        const fetchCommands = async () => {
            try {
                // Scope map: global -> dashboard, project -> project
                const scope = context === "global" ? "dashboard" : "project";
                const response = await apiFetch(`/api/commands/list?scope=${scope}`);
                if (!response.ok) throw new Error(`Failed to fetch commands: ${response.status}`);
                const data = await response.json();

                // Map API response to frontend Command interface
                const cmds: Command[] = (data.commands || []).map((c: any) => ({
                    name: `/${c.name}`,
                    description: c.description,
                    usage: c.usage
                }));

                // Add aliases if they exist in the API
                (data.commands || []).forEach((c: any) => {
                    if (c.aliases && c.aliases.length > 0) {
                        c.aliases.forEach((alias: string) => {
                            cmds.push({
                                name: `/${alias}`,
                                description: `Alias for ${c.name}: ${c.description}`,
                                usage: c.usage.replace(`/${c.name}`, `/${alias}`)
                            });
                        });
                    }
                });

                setAvailableCommands(cmds);
            } catch (error) {
                console.error("Error fetching commands:", error);
            }
        };

        fetchCommands();
    }, [context]);

    useEffect(() => {
        if (debouncedValue.startsWith("/") && debouncedValue.length > 1) {
            const query = debouncedValue.toLowerCase();
            const filtered = availableCommands.filter(cmd =>
                cmd.name.toLowerCase().startsWith(query) ||
                cmd.description.toLowerCase().includes(query.slice(1))
            );
            setFilteredCommands(filtered);
            setShowDropdown(filtered.length > 0);
            setSelectedIndex(0);
        } else if (debouncedValue === "/") {
            setFilteredCommands(availableCommands);
            setShowDropdown(availableCommands.length > 0);
            setSelectedIndex(0);
        } else {
            setShowDropdown(false);
        }
    }, [debouncedValue, availableCommands]);

    const selectCommand = (command: Command) => {
        onChange(command.name + " ");
        setShowDropdown(false);
        if (showInput) {
            inputRef.current?.focus();
        }
    };

    const handleInternalKeyDown = (e: React.KeyboardEvent): boolean => {
        if (!showDropdown) return false;

        switch (e.key) {
            case "ArrowDown":
                e.preventDefault();
                setSelectedIndex(prev => (prev + 1) % filteredCommands.length);
                return true;
            case "ArrowUp":
                e.preventDefault();
                setSelectedIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
                return true;
            case "Enter":
                if (filteredCommands[selectedIndex]) {
                    e.preventDefault();
                    selectCommand(filteredCommands[selectedIndex]);
                    return true;
                }
                break;
            case "Escape":
                e.preventDefault();
                setShowDropdown(false);
                return true;
            case "Tab":
                if (filteredCommands[selectedIndex]) {
                    e.preventDefault();
                    selectCommand(filteredCommands[selectedIndex]);
                    return true;
                }
                break;
        }
        return false;
    };

    useImperativeHandle(ref, () => ({
        handleKeyDown: (e: React.KeyboardEvent) => {
            return handleInternalKeyDown(e);
        }
    }));

    return (
        <div className="relative flex-1">
            {showInput && (
                <input
                    ref={inputRef}
                    type="text"
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={(e) => handleInternalKeyDown(e)}
                    placeholder={placeholder}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 focus:outline-none focus:border-purple-500 transition-colors"
                    disabled={disabled}
                />
            )}

            {/* Command Dropdown */}
            {showDropdown && (
                <div
                    ref={dropdownRef}
                    className="absolute bottom-full left-0 right-0 mb-2 bg-gray-800/95 backdrop-blur-md border border-gray-700 rounded-xl shadow-[0_-12px_40px_-12px_rgba(0,0,0,0.7)] max-h-64 overflow-y-auto z-50 animate-in fade-in slide-in-from-bottom-4 duration-300"
                >
                    {filteredCommands.map((cmd, idx) => (
                        <div
                            key={cmd.name}
                            onClick={() => selectCommand(cmd)}
                            className={`px-4 py-3 cursor-pointer transition-all ${idx === selectedIndex
                                ? "bg-purple-600/20 border-l-4 border-purple-500 pl-6"
                                : "hover:bg-gray-700/50"
                                }`}
                        >
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className={`font-mono transition-colors ${idx === selectedIndex ? "text-purple-300" : "text-purple-400"}`}>
                                        {cmd.name}
                                    </div>
                                    <div className="text-[11px] text-gray-400 mt-1">{cmd.description}</div>
                                </div>
                                <div className="text-[10px] text-gray-500 font-mono bg-gray-900/50 px-2 py-1 rounded">
                                    {cmd.usage}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
});

CommandAutocomplete.displayName = "CommandAutocomplete";

export default CommandAutocomplete;
