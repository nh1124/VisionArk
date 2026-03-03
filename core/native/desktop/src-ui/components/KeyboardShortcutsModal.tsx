import React, { useEffect, useRef } from "react"
import { X, Keyboard } from "lucide-react"

interface Props {
    open: boolean
    onClose: () => void
}

const shortcuts: { category: string; items: { keys: string[]; description: string }[] }[] = [
    {
        category: "General",
        items: [
            { keys: ["Esc"], description: "Close / Cancel" },
        ],
    },
    {
        category: "Window",
        items: [
            { keys: ["Ctrl", "N"], description: "New Window" },
            { keys: ["Shift", "Click"], description: "New Window (Taskbar icon)" },
        ],
    },
    {
        category: "Notes",
        items: [
            { keys: ["Ctrl", "Z"], description: "Undo Delete" },
        ],
    },
    {
        category: "Chat",
        items: [
            { keys: ["Enter"], description: "Send Message" },
            { keys: ["Shift", "Enter"], description: "New Line" },
        ],
    },
    {
        category: "Quick Note",
        items: [
            { keys: ["Ctrl", "Enter"], description: "Save Quick Note" },
            { keys: ["Esc"], description: "Close Quick Note" },
        ],
    },
]

export default function KeyboardShortcutsModal({ open, onClose }: Props) {
    const overlayRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!open) return
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose()
        }
        window.addEventListener("keydown", handler)
        return () => window.removeEventListener("keydown", handler)
    }, [open, onClose])

    if (!open) return null

    return (
        <div
            ref={overlayRef}
            className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={(e) => { if (e.target === overlayRef.current) onClose() }}
        >
            <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800">
                    <div className="flex items-center gap-2.5">
                        <Keyboard size={18} className="text-cyan-400" />
                        <h2 className="text-base font-semibold text-white">Keyboard Shortcuts</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
                    >
                        <X size={16} />
                    </button>
                </div>

                {/* Body */}
                <div className="px-6 py-4 space-y-5 max-h-[60vh] overflow-y-auto custom-scrollbar">
                    {shortcuts.map(({ category, items }) => (
                        <div key={category}>
                            <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2.5">{category}</h3>
                            <div className="space-y-2">
                                {items.map(({ keys, description }, i) => (
                                    <div key={i} className="flex items-center justify-between">
                                        <span className="text-sm text-gray-300">{description}</span>
                                        <div className="flex items-center gap-1">
                                            {keys.map((k, j) => (
                                                <React.Fragment key={j}>
                                                    {j > 0 && <span className="text-[10px] text-gray-600 mx-0.5">+</span>}
                                                    <kbd className="px-2 py-1 text-[11px] font-medium text-gray-300 bg-gray-800 border border-gray-700 rounded-md shadow-sm min-w-[28px] text-center">
                                                        {k}
                                                    </kbd>
                                                </React.Fragment>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
