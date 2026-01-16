/**
 * Schedule API Client
 * 
 * API wrapper for the Dynamic Scheduler endpoint
 */

import { apiFetch, apiJson } from './api';

// ============================================================================
// Types
// ============================================================================

export interface ScheduledTask {
    task_id: string;
    task_name: string;
    context: string;
    status: string;
    load: number;
    start_time?: string;
    end_time?: string;
    scheduled_start_at?: string;
    scheduled_end_at?: string;
}

export interface ScheduledItem {
    task: ScheduledTask | null;
    start: string;  // ISO datetime
    end: string;    // ISO datetime
    is_buffer: boolean;
}

export interface ScheduleResult {
    schedule: ScheduledItem[];
    overflow: ScheduledTask[];
    generated_at: string;
    shutdown_time: string;
    fatigue_level: number;
}

export interface ScheduleSuggestRequest {
    fatigue?: number;
    current_time?: string;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Request a schedule suggestion
 */
export async function suggestSchedule(
    request: ScheduleSuggestRequest = {}
): Promise<ScheduleResult> {
    return apiJson<ScheduleResult>('/api/scheduler/suggest', {
        method: 'POST',
        body: JSON.stringify({
            fatigue: request.fatigue ?? 0,
            current_time: request.current_time,
        }),
    });
}

/**
 * Health check for scheduler service
 */
export async function schedulerHealth(): Promise<{ status: string }> {
    return apiJson('/api/scheduler/health');
}
