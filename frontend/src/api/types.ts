export type TaskStatus = 'open' | 'in_progress' | 'done' | 'cancelled'
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent'
export type TaskSource = 'manual' | 'ilias' | 'email' | 'claude'

export interface Area {
  id: number
  slug: string
  name: string
  color: string
  sort_order: number
  archived: boolean
}

export interface Task {
  id: number
  title: string
  notes: string | null
  area_id: number | null
  area: Area | null
  tags: string[]
  priority: TaskPriority
  status: TaskStatus
  due_date: string | null
  due_time: string | null
  scheduled_date: string | null
  completed_at: string | null
  recurrence: string | null
  source: TaskSource
  external_id: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

export type TaskUpdate = Partial<
  Pick<
    Task,
    | 'title'
    | 'notes'
    | 'area_id'
    | 'tags'
    | 'priority'
    | 'status'
    | 'due_date'
    | 'due_time'
    | 'scheduled_date'
    | 'recurrence'
  >
>

export interface TaskEvent {
  id: number
  type: string
  actor: string
  payload: Record<string, unknown>
  created_at: string
}

export interface QuickAddPreview {
  title: string
  due_date: string | null
  due_time: string | null
  scheduled_date: string | null
  priority: TaskPriority | null
  area: Area | null
  tags: string[]
  recurrence: string | null
}

export interface TodayOverview {
  today: string
  overdue: Task[]
  due_today: Task[]
  scheduled: Task[]
  upcoming: Task[]
  done_today: Task[]
  events: CalendarEvent[]
}

export interface CalendarEvent {
  id: number
  feed: string
  title: string
  location: string | null
  starts_at: string
  ends_at: string | null
  all_day: boolean
}

export interface IntegrationState {
  name: string
  last_run_at: string | null
  last_success_at: string | null
  last_error: string | null
  stats: Record<string, unknown>
}

export type Split = 'push' | 'pull' | 'legs' | 'other'

export interface SessionBrief {
  id: number
  started_at: string
  workout_name: string
  split: Split
  exercises: number
  sets: number
  volume_kg: number
  duration_minutes: number | null
}

export interface TrainingWeek {
  week_start: string
  sessions: number
  sets: number
  volume_kg: number
}

export interface TrainingSummary {
  since: string
  sessions: number
  sets: number
  volume_kg: number
  this_week_sessions: number
  last_session: SessionBrief | null
  weeks: TrainingWeek[]
  split: Record<Split, number>
}

export interface TrainingSet {
  set_index: number
  weight_kg: number | null
  reps: number | null
  e1rm: number | null
}

export interface SessionDetail extends SessionBrief {
  exercise_sets: { exercise_id: number; name: string; bodyweight: boolean; sets: TrainingSet[] }[]
}

export interface Exercise {
  id: number
  name: string
  muscle_group: string | null
  bodyweight: boolean
  aliases: string[]
  sessions: number
  sets: number
  last_at: string | null
  best_e1rm: number | null
  best_weight: number | null
  max_reps: number | null
}

export interface ProgressPoint {
  date: string
  session_id: number
  workout_name: string
  sets: number
  top_weight: number | null
  best_e1rm: number | null
  max_reps: number | null
  volume_kg: number
}

export interface ImportResult {
  rows: number
  sessions_created: number
  sets_created: number
  sets_updated: number
  sets_unchanged: number
  exercises_created: number
  first: string
  last: string
}
