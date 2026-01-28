export interface Subtask {
    id: string;
    text: string;
    done: boolean;
}

export interface TaskMeta {
    steps?: Subtask[];
    is_my_day?: boolean;
    tags?: string[];
    priority?: 'low' | 'medium' | 'high';
}

export interface Task {
    task_id: string;
    task_name: string;
    context: string;
    base_load_score: number;
    active: boolean;
    rule_type: string;
    due_date: string | null;
    notes: string | null;
    status: "planned" | "completed" | "skipped" | "todo" | string;
    meta_payload?: TaskMeta;

    // Schedule info
    start_time?: string | null;
    end_time?: string | null;
    mon?: boolean;
    tue?: boolean;
    wed?: boolean;
    thu?: boolean;
    fri?: boolean;
    sat?: boolean;
    sun?: boolean;
    interval_days?: number;
    anchor_date?: string | null;
    month_day?: number;
    nth_in_month?: number;
    weekday_mon1?: number;
    start_date?: string | null;
    end_date?: string | null;
}
