// Spoke color scheme for task visualization
export const SPOKE_COLORS: { [key: string]: string } = {
    // Predefined colors for common spokes
    research: "#3B82F6",    // blue
    development: "#10B981", // green
    writing: "#F59E0B",     // amber
    testing: "#EF4444",     // red
    planning: "#8B5CF6",    // purple
    review: "#EC4899",      // pink
    deployment: "#14B8A6",  // teal
    documentation: "#F97316", // orange
};

// Default color for unknown spokes
// v2.0-fix-applied
const DEFAULT_SPOKE_COLOR = "#6B7280"; // gray

export function getSpokeColor(spokeName: string | undefined | null): string {
    if (!spokeName) return DEFAULT_SPOKE_COLOR;
    return SPOKE_COLORS[spokeName.toLowerCase()] || DEFAULT_SPOKE_COLOR;
}

// Generate color for new spoke (cycle through colors)
export function assignSpokeColor(spokeName: string, existingSpokes: string[]): string {
    const colorValues = Object.values(SPOKE_COLORS);
    const index = existingSpokes.length % colorValues.length;
    return colorValues[index];
}
