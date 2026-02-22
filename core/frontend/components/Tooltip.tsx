"use client";

import { useState } from "react";
import { HelpCircle } from "lucide-react";

interface TooltipProps {
    /** Tooltip の説明文 */
    text: string;
    /** 表示位置。デフォルト "top" */
    position?: "top" | "right" | "bottom" | "left";
    /** アイコンの大きさ（px）。デフォルト 13 */
    size?: number;
}

/**
 * `?` アイコンにホバーすると説明テキストを表示する汎用 Tooltip。
 * `<label>` の中で使用する場合は type="button" で form submit を防いでいます。
 *
 * 使い方:
 *   <Tooltip text="ここに説明" />
 *   <Tooltip text="右側に表示" position="right" />
 */
export function Tooltip({ text, position = "top", size = 13 }: TooltipProps) {
    const [visible, setVisible] = useState(false);

    const positionClasses: Record<string, string> = {
        top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
        bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
        right: "left-full top-1/2 -translate-y-1/2 ml-2",
        left: "right-full top-1/2 -translate-y-1/2 mr-2",
    };

    const arrowClasses: Record<string, string> = {
        top: "top-full left-1/2 -translate-x-1/2 border-t-gray-700 border-x-transparent border-b-transparent border-[5px]",
        bottom: "bottom-full left-1/2 -translate-x-1/2 border-b-gray-700 border-x-transparent border-t-transparent border-[5px]",
        right: "right-full top-1/2 -translate-y-1/2 border-r-gray-700 border-y-transparent border-l-transparent border-[5px]",
        left: "left-full top-1/2 -translate-y-1/2 border-l-gray-700 border-y-transparent border-r-transparent border-[5px]",
    };

    return (
        <span className="relative inline-flex items-center">
            <button
                type="button"
                onMouseEnter={() => setVisible(true)}
                onMouseLeave={() => setVisible(false)}
                onFocus={() => setVisible(true)}
                onBlur={() => setVisible(false)}
                className="text-gray-600 hover:text-gray-400 transition-colors focus:outline-none"
                aria-label="Help"
            >
                <HelpCircle size={size} />
            </button>

            {visible && (
                <span className={`absolute z-50 pointer-events-none ${positionClasses[position]}`}>
                    <span className="relative block bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300 shadow-xl max-w-[220px] leading-relaxed whitespace-normal">
                        {text}
                        {/* 矢印 */}
                        <span className={`absolute w-0 h-0 ${arrowClasses[position]}`} />
                    </span>
                </span>
            )}
        </span>
    );
}
