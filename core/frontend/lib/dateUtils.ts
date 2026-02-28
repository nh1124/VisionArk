/**
 * Returns the current local date as a YYYY-MM-DD string.
 * 
 * IMPORTANT: Do NOT use `new Date().toISOString().split('T')[0]` for this purpose.
 * `toISOString()` converts to UTC first, which gives the wrong date for users
 * in positive UTC offsets (e.g., JST +9:00) between midnight and the offset hour.
 */
export function getLocalDateString(date?: Date): string {
    const d = date ?? new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}
