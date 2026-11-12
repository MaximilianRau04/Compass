export type TaskStatus = 'open' | 'in_progress' | 'done' | 'cancelled'
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent'
export type TaskSource = 'manual' | 'ilias' | 'feed' | 'email' | 'claude'

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
  /** Area slug of its calendar, if one is set. */
  area: string | null
}

export interface IntegrationState {
  name: string
  last_run_at: string | null
  last_success_at: string | null
  last_error: string | null
  stats: Record<string, unknown>
}

export type Split = 'push' | 'pull' | 'legs' | 'other' | 'sport'

export interface SessionBrief {
  id: number
  started_at: string
  workout_name: string
  split: Split
  exercises: number
  sets: number
  volume_kg: number
  duration_minutes: number | null
  source: 'gymday' | 'strong' | 'hevy' | 'healthconnect' | 'watch' | 'compass'
  activity: string | null
  hr_avg: number | null
  hr_max: number | null
  zone2_minutes?: number | null
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
  rep_min: number
  rep_max: number
  weight_step: number
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
  extras: ExtraDay[]
  sync: { last_run_at: string | null; last_success_at: string | null; last_error: string | null; device: string | null } | null
}

export type MealName = 'breakfast' | 'lunch' | 'dinner' | 'snack' | 'unknown'
export type GoalMetric = 'kcal' | 'protein_g' | 'carbs_g' | 'fat_g' | 'steps' | 'hr_max' | 'weight_loss_min' | 'weight_loss_max'

export interface NutritionDay {
  date: string
  source: 'healthconnect' | 'mfp_export' | 'cronometer_export' | 'loseit_export'
  kcal: number
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  saturated_fat_g: number | null
  potassium_mg: number | null
  calcium_mg: number | null
  iron_mg: number | null
  meals: { meal: MealName; kcal: number; protein_g: number | null; carbs_g: number | null; fat_g: number | null }[]
  /** incomplete (under 1500 kcal), same_as_previous_day: left out of the averages */
  flags: ('incomplete' | 'same_as_previous_day')[]
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
  averages: NutritionAverages
  averages_all: NutritionAverages
  quality: { incomplete: string[]; same_as_previous_day: string[]; gaps: string[]; valid_days: number }
  weeks: { week_start: string; days_tracked: number; kcal: number; protein_g: number | null }[]
  protein_goal_days: number | null
  weight: WeightPoint | null
  weight_change: number | null
}

export interface NutritionImportResult {
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


/** Sender, subject and summary come from outside the app. Render as text, never as HTML. */
export interface Mail {
  id: number
  account: string
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

export interface MailAccount {
  account: string
  triage: string
  last_success_at: string | null
  last_error: string | null
  pending: number
  /** password, or microsoft for an OAuth sign-in */
  auth: string
  /** Only for accounts with a sign-in. */
  signed_in: boolean | null
  signed_in_as: string | null
  signin_error: string | null
}

export interface SignInStart {
  user_code: string
  verification_uri: string
  expires_at: string
  interval: number
}

export interface SignInPoll {
  status: 'pending' | 'done' | 'failed'
  message: string | null
  signed_in_as: string | null
}

export interface MailOverview {
  accounts: MailAccount[]
  important: number
  unread_important: number
  top: Mail[]
}

/** Title and summary come from RSS feeds. Render as text, never as HTML. */
export interface NewsItem {
  id: number
  feed: string
  stream: 'general' | 'personal'
  url: string
  title: string
  summary: string | null
  published_at: string
  feedback: 1 | -1 | null
  score: number
  topics: string[]
  trending: string[]
}

export interface Trend {
  term: string
  feeds: string[]
  count: number
}

/** Written by an assistant (partly from web content). Rendered by the Markdown component as text. */
export interface Brief {
  id: number
  kind: string
  local_date: string
  title: string | null
  body: string
  actor: string
  updated_at: string
}

export interface NewsOverview {
  feeds: { feed: string; stream: string | null; last_success_at: string | null; last_error: string | null; items: number | null }[]
  trends: Trend[]
  top: NewsItem[]
  report: Brief | null
}

export interface Interest {
  term: string
  weight: number
}

export interface Interests {
  topics: Interest[]
  likes: Interest[]
  dislikes: Interest[]
}

export interface Note {
  id: number
  title: string
  body: string
  area_id: number | null
  area: Area | null
  tags: string[]
  pinned: boolean
  archived: boolean
  source: 'manual' | 'claude' | 'share'
  task_id: number | null
  created_at: string
  updated_at: string
}

export interface NoteListItem {
  id: number
  title: string
  snippet: string
  area: Area | null
  tags: string[]
  pinned: boolean
  archived: boolean
  source: Note['source']
  task_id: number | null
  updated_at: string
}

export interface NoteDraft {
  title?: string
  body?: string
  area_id?: number | null
  tags?: string[]
  pinned?: boolean
  archived?: boolean
  task_id?: number | null
  source?: 'manual' | 'share'
}

export interface DayHeartRate {
  date: string
  points: { time: string; bpm: number }[]
  min: number | null
  max: number | null
  avg: number | null
  resting: number | null
  last: { time: string; bpm: number } | null
  sleep_start: string | null
  sleep_end: string | null
}

/** Values only some watches write; null when there is none. */
export interface ExtraDay {
  date: string
  oxygen_saturation: number | null
  heart_rate_variability: number | null
  heart_rate_variability_sdnn: number | null
  respiratory_rate: number | null
  distance: number | null
  active_calories: number | null
}

export interface Suggestion {
  exercise_id: number
  name: string
  bodyweight: boolean
  last_date: string
  last_sets: { weight_kg: number | null; reps: number | null; rir: number | null }[]
  last_set_count: number
  rep_min: number
  rep_max: number
  weight_step: number
  /** increase: more weight at rep_min; reps: same weight, one more rep */
  action: 'increase' | 'reps'
  weight_kg: number | null
  reps: number
  rir_known: boolean
  same_sessions: number
  stagnant: boolean
}

export interface Progression {
  suggestions: Suggestion[]
  stagnant: Suggestion[]
}

export interface TemplateExercise {
  /** null for an exercise in a saved template that was never trained */
  exercise_id: number | null
  name: string
  bodyweight: boolean
  suggestion: Suggestion | null
  /** Planned sets and rest, only from a saved template */
  sets?: number | null
  rest_seconds?: number | null
}

export interface WorkoutTemplateItem {
  exercise_id: number | null
  name: string
  sets: number
  rest_seconds: number
}

export interface WorkoutTemplate {
  id: number
  name: string
  exercises: WorkoutTemplateItem[]
  last_at: string | null
}

export interface BodyTrend {
  today: string
  days: { date: string; kg: number | null; source: string | null; mean7: number | null }[]
  mean7: number | null
  mean7_before: number | null
  change_kg: number | null
  change_pct: number | null
  loss_per_week: number | null
  loss_min: number
  loss_max: number
  status: 'on_target' | 'too_slow' | 'too_fast' | 'gaining' | null
  waist: { date: string; cm: number }[]
  waist_change: number | null
  weeks: { week_start: string; kg: number | null; waist_cm: number | null }[]
}

export interface NutritionAverages {
  kcal: number | null
  protein_g: number | null
  carbs_g: number | null
  fat_g: number | null
  fiber_g: number | null
  sugar_g: number | null
  sodium_mg: number | null
  saturated_fat_g: number | null
  potassium_mg: number | null
  calcium_mg: number | null
  iron_mg: number | null
}

export interface HealthAnalysis {
  consistency: {
    nights: number
    median_bedtime: string | null
    median_wake_time: string | null
    bedtime_sd_minutes: number | null
    wake_time_sd_minutes: number | null
    short_nights: string[]
    early_nights: { date: string; first_event: string; title: string; asleep_minutes: number }[]
    avg_asleep_early: number | null
    avg_asleep_other: number | null
  }
  resting: { days: { date: string; bpm: number | null; mean7: number | null }[]; median: number | null; latest_mean7: number | null; alert: boolean }
  hr_max: number
  zone2_low: number
  zone2_high: number
  zone2_weeks: { week_start: string; minutes: number; in_training: number }[]
}
