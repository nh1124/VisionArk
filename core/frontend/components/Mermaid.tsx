"use client";

import React, { useEffect, useRef, useState } from "react";

interface MermaidProps {
    chart: string;
}

/**
 * Pre-process a mermaid chart string to work around known lexer limitations.
 *
 * Root cause (confirmed by inspecting the Jison lexer rules in the bundled
 * quadrantDiagram chunk):  In the INITIAL lexer state the only text rule is
 * rule 35: /^(?:[A-Za-z]+)/i  (ASCII letters only).  Japanese / CJK /
 * hiragana / katakana characters match NO rule in INITIAL state, causing
 * "Lexical error: Unrecognized text".
 *
 * The grammar DOES accept  text → STR  where STR is produced from the
 * `string` lexer state (/^(?:[^"]*)/i — matches any non-quote chars including
 * multi-byte Unicode).  Entering the string state requires a leading `"`.
 *
 * Fixes applied to quadrantChart:
 *   1. Strip leading whitespace (dedent) so keywords start at column 0.
 *   2. Wrap non-ASCII label text in double-quotes ("...") for:
 *      - x-axis / y-axis  (both the low and high parts of  A --> B)
 *      - quadrant-1/2/3/4 labels
 *   (title and quoted point labels already handle multi-byte chars correctly.)
 */
function preprocessChart(chart: string): string {
    const lines = chart.split("\n");
    const diagramType = lines[0]?.trim().toLowerCase() ?? "";

    // Normalize indentation for all diagram types
    const dedented = lines.map((l) => l.replace(/^\s+/, "")).join("\n");

    if (diagramType === "quadrantchart") {
        // Wrap a string in double-quotes only when it contains non-ASCII chars.
        // Strip any existing double-quotes from the content to avoid nesting.
        const q = (s: string) =>
            /[^\x00-\x7F]/.test(s) ? `"${s.replace(/"/g, "")}"` : s;

        return dedented
            .split("\n")
            .map((line) => {
                // x-axis / y-axis  LOW --> HIGH
                const rangeMatch = line.match(/^(x-axis|y-axis)\s+(.*?)\s+-->\s+(.*?)\s*$/i);
                if (rangeMatch) {
                    const [, kw, low, high] = rangeMatch;
                    return `${kw} ${q(low)} --> ${q(high)}`;
                }
                // x-axis / y-axis  LABEL  (no range)
                const axisSimple = line.match(/^(x-axis|y-axis)\s+(.*?)\s*$/i);
                if (axisSimple && /[^\x00-\x7F]/.test(axisSimple[2])) {
                    const [, kw, label] = axisSimple;
                    return `${kw} ${q(label)}`;
                }
                // quadrant-1/2/3/4  LABEL
                const quadMatch = line.match(/^(quadrant-[1-4])\s+(.*?)\s*$/i);
                if (quadMatch && /[^\x00-\x7F]/.test(quadMatch[2])) {
                    const [, kw, label] = quadMatch;
                    return `${kw} ${q(label)}`;
                }
                return line;
            })
            .join("\n");
    }

    return dedented;
}

const Mermaid: React.FC<MermaidProps> = React.memo(({ chart }) => {
    const ref = useRef<HTMLDivElement>(null);
    const lastChart = useRef<string>("");
    const [libLoaded, setLibLoaded] = useState(false);

    useEffect(() => {
        const loadAndRender = async () => {
            if (!ref.current || !chart) return;

            // Skip if the chart hasn't changed to avoid flickering
            if (chart === lastChart.current) return;
            lastChart.current = chart;

            try {
                let mermaid: any;

                // 1. Check if already in window (from script tag)
                if (typeof window !== "undefined" && (window as any).mermaid) {
                    mermaid = (window as any).mermaid;
                } else {
                    try {
                        // 2. Try to load from CDN first to be safe in Docker envs where bundling fails
                        await new Promise((resolve) => {
                            const script = document.createElement("script");
                            script.src = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js";
                            script.async = true;
                            script.onload = resolve;
                            script.onerror = () => {
                                console.warn("CDN load failed, will try local import as last resort");
                                resolve(null);
                            };
                            document.head.appendChild(script);
                        });

                        if ((window as any).mermaid) {
                            mermaid = (window as any).mermaid;
                        }
                    } catch (e) {
                        console.error("CDN attempt failed:", e);
                    }
                }

                // 3. Last resort: Try to find it in window if CDN onload was skipped
                if (!mermaid && typeof window !== "undefined") {
                    mermaid = (window as any).mermaid;
                }

                if (!mermaid) {
                    throw new Error("Mermaid library could not be loaded via CDN.");
                }

                mermaid.initialize({
                    startOnLoad: false,
                    theme: "dark",
                    securityLevel: "loose",
                    fontFamily: "Inter, sans-serif",
                    suppressErrorRendering: true,
                });

                const id = `mermaid-${Math.floor(Math.random() * 1000000)}`;

                // First attempt: try with pre-processed chart
                let svg: string | undefined;
                try {
                    const result = await mermaid.render(id, preprocessChart(chart));
                    svg = result.svg;
                } catch {
                    // Second attempt: try with original chart as-is
                    const id2 = `mermaid-${Math.floor(Math.random() * 1000000)}`;
                    const result = await mermaid.render(id2, chart);
                    svg = result.svg;
                }

                if (ref.current && svg) {
                    ref.current.innerHTML = svg;
                    ref.current.removeAttribute("data-processed");
                    setLibLoaded(true);
                }
            } catch (err: any) {
                console.error("Mermaid error:", err);
                // Fallback: show the chart source as a readable code block instead of a red error
                if (ref.current) {
                    ref.current.innerHTML = `
                        <div style="width:100%">
                            <div style="font-size:10px;color:#6b7280;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;">
                                diagram (render failed)
                            </div>
                            <pre style="background:#0a0a0a;border:1px solid #1f2937;border-radius:8px;padding:12px;font-size:11px;color:#9ca3af;white-space:pre-wrap;word-break:break-word;margin:0;font-family:monospace;">${chart.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
                        </div>
                    `;
                }
            }
        };

        loadAndRender();
    }, [chart]);

    return (
        <div className="mermaid-container flex justify-center my-6 bg-gray-900/10 p-4 rounded-xl border border-gray-800/30 shadow-inner overflow-x-auto min-h-[60px]">
            <div ref={ref} className="mermaid transition-all duration-300 min-w-[200px] flex justify-center" />
        </div>
    );
});

export default Mermaid;
