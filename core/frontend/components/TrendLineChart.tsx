"use client";

import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine,
} from "recharts";

interface TrendDataPoint {
    date: string;
    average_load: number;
    max_load: number;
    min_load: number;
}

interface TrendLineChartProps {
    data: TrendDataPoint[];
    cap?: number;
    height?: number;
}

export default function TrendLineChart({
    data,
    cap = 8.0,
    height = 300,
}: TrendLineChartProps) {
    // Format data for recharts
    const chartData = data.map((point) => ({
        date: new Date(point.date).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
        }),
        avg: point.average_load,
        max: point.max_load,
        min: point.min_load,
    }));

    // Calculate stats
    const avgLoad = data.length > 0
        ? (data.reduce((sum, d) => sum + d.average_load, 0) / data.length).toFixed(1)
        : "0.0";
    const peakLoad = data.length > 0
        ? Math.max(...data.map((d) => d.max_load)).toFixed(1)
        : "0.0";
    const overCapDays = data.filter((d) => d.average_load > cap).length;

    return (
        <div className="w-full h-full flex flex-col">
            {/* Chart Area */}
            <div className="flex-1 min-h-[300px]">
                <ResponsiveContainer width="100%" height={height}>
                    <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#374151" vertical={false} />
                        <XAxis
                            dataKey="date"
                            stroke="#9ca3af"
                            style={{ fontSize: "12px" }}
                            tickMargin={10}
                        />
                        <YAxis
                            stroke="#9ca3af"
                            style={{ fontSize: "12px" }}
                            tickMargin={5}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: "#1f2937",
                                border: "1px solid #374151",
                                borderRadius: "8px",
                                boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
                            }}
                            itemStyle={{ fontSize: "12px" }}
                            labelStyle={{ color: "#f3f4f6", marginBottom: "4px" }}
                        />
                        <Legend
                            wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }}
                            iconType="circle"
                        />

                        <ReferenceLine
                            y={cap}
                            stroke="#ef4444"
                            strokeDasharray="5 5"
                            strokeWidth={2}
                            label={{
                                value: "CAP",
                                fill: "#ef4444",
                                fontSize: 10,
                                position: "right",
                                fontWeight: "bold",
                            }}
                        />

                        <Line
                            type="monotone"
                            dataKey="avg"
                            stroke="#3b82f6"
                            strokeWidth={3}
                            name="Average Load"
                            dot={{ r: 4, fill: "#3b82f6", strokeWidth: 2 }}
                            activeDot={{ r: 6, strokeWidth: 0 }}
                        />
                        <Line
                            type="monotone"
                            dataKey="max"
                            stroke="#ef4444"
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="Max Load"
                            dot={false}
                        />
                        <Line
                            type="monotone"
                            dataKey="min"
                            stroke="#10b981"
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            name="Min Load"
                            dot={false}
                        />
                    </LineChart>
                </ResponsiveContainer>
            </div>

            {/* Stats Row - Centered below chart */}
            <div className="flex items-center justify-center gap-8 mt-4 pt-4 border-t border-gray-800">
                <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-sm">Avg:</span>
                    <span className="font-bold text-blue-400 text-lg">{avgLoad}</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-sm">Peak:</span>
                    <span className="font-bold text-red-400 text-lg">{peakLoad}</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-sm">Over CAP:</span>
                    <span className="font-bold text-orange-400 text-lg">{overCapDays}</span>
                </div>
            </div>
        </div>
    );
}
