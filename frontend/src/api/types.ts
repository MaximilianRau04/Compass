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
}
