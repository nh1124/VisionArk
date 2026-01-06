"use client";

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from "recharts";

interface ContextLoad {
    context: string;
    load: number;
    color: string;
}

interface DayData {
    date: string;
    total_load: number;
    contexts: ContextLoad[];
}

interface StackedBarChartProps {
    data: DayData[];
    height?: number;
}

export default function StackedBarChart({
    data,
    height = 300,
}: StackedBarChartProps) {
    // Transform data for recharts stacked bar format
    const chartData = data.map((day) => {
        const dayData: any = {
            date: new Date(day.date).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
            }),
            totalLoad: day.total_load,
        };

        // Add each context as a separate field
        day.contexts.forEach((ctx) => {
            dayData[ctx.context] = ctx.load;
        });

        return dayData;
    });

    // Get unique contexts for bars
    const allContexts = new Set<string>();
    data.forEach((day) => {
        day.contexts.forEach((ctx) => {
            allContexts.add(ctx.context);
        });
    });

    // Predefined color palette
    const contextColors: { [key: string]: string } = {
        research: "#3b82f6", // blue
        development: "#10b981", // green
        thesis: "#f59e0b", // amber
        life_admin: "#8b5cf6", // purple
        default: "#6b7280", // gray
    };

    const getContextColor = (context: string) => {
        return contextColors[context] || contextColors.default;
    };

    return (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <div className="mb-4">
                <h3 className="text-lg font-semibold">Context Load Distribution</h3>
                <p className="text-sm text-gray-400">Weekly load breakdown by project</p>
            </div>

            <ResponsiveContainer width="100%" height={height}>
                <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="date" stroke="#9ca3af" style={{ fontSize: "12px" }} />
                    <YAxis stroke="#9ca3af" style={{ fontSize: "12px" }} />
                    <Tooltip
                        contentStyle={{
                            backgroundColor: "#1f2937",
                            border: "1px solid #374151",
                            borderRadius: "8px",
                        }}
                        labelStyle={{ color: "#f3f4f6" }}
                    />
                    <Legend
                        wrapperStyle={{ fontSize: "12px" }}
                        iconType="square"
                    />

                    {Array.from(allContexts).map((context) => (
                        <Bar
                            key={context}
                            dataKey={context}
                            stackId="a"
                            fill={getContextColor(context)}
                            radius={[0, 0, 0, 0]}
                        />
                    ))}
                </BarChart>
            </ResponsiveContainer>

            {/* Context legend with colors */}
            <div className="mt-4 flex flex-wrap gap-3">
                {Array.from(allContexts).map((context) => (
                    <div key={context} className="flex items-center gap-2">
                        <div
                            className="w-3 h-3 rounded"
                            style={{ backgroundColor: getContextColor(context) }}
                        ></div>
                        <span className="text-sm text-gray-400">
                            {context.replace(/_/g, " ")}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
