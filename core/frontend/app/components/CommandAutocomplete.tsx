import { useState, useEffect, useRef, forwardRef, useImperativeHandle } from "react";

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
    context: "hub" | "spoke";
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
    context,
    disabled = false,
    showInput = true
}, ref) => {
    const [commands, setCommands] = useState<Command[]>([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Debounce input value to reduce filtering frequency (150ms delay)
    const debouncedValue = useDebounce(value, 150);

    // ... (hubCommands and spokeCommands remain same)
    const hubCommands: Command[] = [
        { name: "/create_spoke", description: "Create a new Spoke", usage: "/create_spoke <name>" },
        { name: "/create_task", description: "Create a new LBS task", usage: '/create_task name="Task" spoke="spoke" workload=5.0' },
        { name: "/check_inbox", description: "Check pending inbox messages", usage: "/check_inbox" },
        { name: "/send_message", description: "Send message to a Spoke", usage: "/check_inbox name=<spoke_name> message=<message>" },
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
                setSelectedIndex(prev => (prev + 1) % commands.length);
                return true;
            case "ArrowUp":
                e.preventDefault();
                setSelectedIndex(prev => (prev - 1 + commands.length) % commands.length);
                return true;
            case "Enter":
                if (commands[selectedIndex]) {
                    e.preventDefault();
                    selectCommand(commands[selectedIndex]);
                    return true;
                }
                break;
            case "Escape":
                e.preventDefault();
                setShowDropdown(false);
                return true;
            case "Tab":
                if (commands[selectedIndex]) {
                    e.preventDefault();
                    selectCommand(commands[selectedIndex]);
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
                    {commands.map((cmd, idx) => (
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
