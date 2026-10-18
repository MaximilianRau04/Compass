import type { SleepStage } from '../api/types'

const APPS: Record<string, string> = {
  'com.huami.watch.hmwatchmanager': 'Zepp',
  'com.anthonyng.workoutapp': 'Gym Day',
  'com.myfitnesspal.android': 'MyFitnessPal',
  'com.sec.android.app.shealth': 'Samsung Health',
  'com.google.android.apps.fitness': 'Google Fit',
}

/** Display name for a Health Connect source package. */
export function appName(pkg: string): string {
  return APPS[pkg] ?? pkg.split('.').pop() ?? pkg
}

/** 450 -> "7:30 h" */
export function hours(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(Math.round(minutes % 60)).padStart(2, '0')} h`
}

/** Lane of a stage in the hypnogram; generic "sleeping" goes with light sleep. */
export type Lane = 'awake' | 'rem' | 'light' | 'deep'
export const LANES: Lane[] = ['awake', 'rem', 'light', 'deep']

export function laneOf(stage: SleepStage): Lane {
  if (stage === 'awake' || stage === 'awake_in_bed' || stage === 'out_of_bed') return 'awake'
  if (stage === 'rem' || stage === 'deep') return stage
  return 'light'
}
