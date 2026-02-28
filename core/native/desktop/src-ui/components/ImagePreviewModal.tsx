import React, { useEffect } from "react"
import { X } from "lucide-react"
import { BASE_URL } from "../lib/api"

interface ImagePreviewModalProps {
    url: string
    name: string
    onClose: () => void
}

export default function ImagePreviewModal({ url, name, onClose }: ImagePreviewModalProps) {
    // Resolve relative URLs to absolute with backend base
    const resolvedUrl = url.startsWith("http") ? url : `${BASE_URL}${url}`

    // Close on Escape
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose()
        }
        document.addEventListener("keydown", handler)
        return () => document.removeEventListener("keydown", handler)
    }, [onClose])

    return (
        <div
            className="fixed inset-0 bg-black/90 backdrop-blur-md z-[100] flex flex-col animate-in fade-in duration-300"
            onClick={onClose}
        >
            {/* Header */}
            <div className="flex justify-between items-center p-4 bg-gray-900/50 flex-shrink-0">
                <h3 className="text-sm font-bold text-gray-200 truncate">{name}</h3>
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-white/10 rounded-full text-white transition-colors"
                    title="Close (Esc)"
                >
                    <X size={24} />
                </button>
            </div>

            {/* Image */}
            <div className="flex-1 flex items-center justify-center p-4 md:p-12">
                <img
                    src={resolvedUrl}
                    alt={name}
                    className="max-w-full max-h-full object-contain shadow-2xl rounded-lg animate-in zoom-in duration-300"
                    onClick={(e) => e.stopPropagation()}
                />
            </div>
        </div>
    )
}
