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
  source: 'gymday' | 'healthconnect'
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

export type SleepStage = 'deep' | 'light' | 'rem' | 'awake' | 'awake_in_bed' | 'out_of_bed' | 'sleeping' | 'unknown'

export interface SleepNight {
  id: number
  local_date: string
  start_at: string
  end_at: string
  in_bed_minutes: number
  asleep_minutes: number
  deep_minutes: number | null
  light_minutes: number | null
  rem_minutes: number | null
  awake_minutes: number | null
  source_app: string
}

export interface SleepNightDetail extends SleepNight {
  stages: { start: string; end: string; stage: SleepStage }[]
  heart_rate: { time: string; bpm: number }[]
}

export interface DailyMetrics {
  date: string
  steps: number | null
  kcal_burned: number | null
  resting_hr: number | null
  hr_min: number | null
  hr_avg: number | null
  hr_max: number | null
  sleep_minutes: number | null
}

export interface Workout {
  id: string
  source_app: string
  start_at: string
  end_at: string
  duration_minutes: number
  title: string | null
  exercise: string | null
  gymday_duplicate: boolean
}

export interface HealthSummary {
  since: string
  until: string
  last_night: SleepNightDetail | null
  nights: SleepNight[]
  days: DailyMetrics[]
  averages: {
    sleep_minutes: number | null
    deep_minutes: number | null
    light_minutes: number | null
    rem_minutes: number | null
    awake_minutes: number | null
    resting_hr: number | null
    steps: number | null
  }
  workouts: Workout[]
  sync: { last_run_at: string | null; last_success_at: string | null; last_error: string | null; device: string | null } | null
}

export type MealName = 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'unknown'
export type GoalMetric = 'kcal' | 'protein_g' | 'carbs_g' | 'fat_g'

export interface NutritionDay {
  date: string
  source: 'healthconnect' | 'mfp_export'
  kcal: number
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  meals: { meal: MealName; kcal: number; protein_g: number | null; carbs_g: number | null; fat_g: number | null }[]
}

export interface WeightPoint {
  date: string
  kg: number
  source: string
}

export interface NutritionSummary {
  since: string
  until: string
  days: NutritionDay[]
  goals: Partial<Record<GoalMetric, number>>
  averages: { kcal: number | null; protein_g: number | null; carbs_g: number | null; fat_g: number | null; fiber_g: number | null; sugar_g: number | null }
  weeks: { week_start: string; days_tracked: number; kcal: number; protein_g: number | null }[]
  protein_goal_days: number | null
  weight: WeightPoint | null
  weight_change: number | null
}

export interface MfpImportResult {
  meals_created: number
  meals_updated: number
  meals_unchanged: number
  days: number
  weights: number
  weights_created: number
  first: string
  last: string
  ignored_files: string[]
}

export type MailAccountName = 'uni' | 'gmail' | 'domain'

/** Sender, subject and summary come from outside the app. Render as text, never as HTML. */
export interface Mail {
  id: number
  account: MailAccountName
  from_name: string | null
  from_addr: string
  subject: string
  received_at: string
  seen: boolean
  bulk: boolean
  priority: 'high' | 'normal' | 'low'
  needs_action: boolean | null
  category: string | null
  summary: string | null
  task_title: string | null
  triage: 'rules' | 'claude' | 'local' | 'pending'
  task_id: number | null
  dismissed: boolean
}

export interface MailOverview {
  accounts: { account: MailAccountName; triage: string; last_success_at: string | null; last_error: string | null; pending: number }[]
  important: number
  unread_important: number
  top: Mail[]
}
