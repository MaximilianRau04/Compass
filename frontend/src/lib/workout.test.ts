import { describe, expect, it } from 'vitest'

import type { TemplateExercise } from '../api/types'
import { grams, isNutritionExport, kcal, nutritionImportMessage } from './nutrition'
import { importMessage } from './training'
import { clock, type Draft, exerciseFrom, restLabel, toPayload } from './workout'

const t = ((key: string, vars?: Record<string, string | number>) =>
  `${key}:${JSON.stringify(vars ?? {})}`) as Parameters<typeof importMessage>[1]

describe('training helpers', () => {
  it('formats importMessage for empty and populated imports', () => {
    const base = {
      rows: 12,
      sessions_created: 0,
      sets_created: 0,
      sets_updated: 0,
      sets_unchanged: 12,
      exercises_created: 0,
      first: '2026-11-01',
      last: '2026-11-10',
    }
    expect(importMessage(base, t)).toContain('training.importNothing')
    expect(importMessage({ ...base, sessions_created: 2, sets_created: 8, sets_updated: 1, exercises_created: 1 }, t))
      .toContain('training.imported')
  })
})

describe('nutrition helpers', () => {
  it('detects zip files and known nutrition CSV headers', async () => {
    const zip = new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])])
    const mfp = new Blob(['Datum,Mahlzeit,Kalorien\n2026-11-01,Frühstück,500\n'])
    const cronometer = new Blob(['Day,Group,Food Name,Energy (kcal)\n'])
    const gymDay = new Blob(['Date,Workout name,Exercise,Set,Weight,Reps\n'])

    expect(await isNutritionExport(zip)).toBe(true)
    expect(await isNutritionExport(mfp)).toBe(true)
    expect(await isNutritionExport(cronometer)).toBe(true)
    expect(await isNutritionExport(gymDay)).toBe(false)
  })

  it('formats kcal, grams and importMessage', () => {
    const base = {
      meals_created: 0,
      meals_updated: 0,
      meals_unchanged: 5,
      days: 0,
      weights: 0,
      weights_created: 0,
      first: '2026-11-01',
      last: '2026-11-10',
      ignored_files: [],
    }
    expect(kcal(2499.6, 'en-GB')).toBe('2,500 kcal')
    expect(grams(174.4)).toBe('174 g')
    expect(nutritionImportMessage(base, t)).toContain('nutrition.importNothing')
    expect(
      nutritionImportMessage({ ...base, meals_created: 3, meals_updated: 1, weights_created: 1, days: 2 }, t),
    ).toContain('nutrition.imported')
  })
})

describe('workout helpers', () => {
  it('formats clock and rest labels', () => {
    expect(clock(-5)).toBe('0:00')
    expect(clock(75)).toBe('1:15')
    expect(clock(3725)).toBe('1:02:05')
    expect(restLabel(0, 'None')).toBe('None')
    expect(restLabel(90, 'None')).toBe('1:30')
  })

  it('builds exercises from templates and sends only completed sets in kg', () => {
    const template: TemplateExercise = {
      exercise_id: 7,
      name: 'Bench Press',
      bodyweight: false,
      sets: 2,
      rest_seconds: 120,
      suggestion: {
        exercise_id: 7,
        name: 'Bench Press',
        bodyweight: false,
        last_date: '2026-11-01',
        last_sets: [
          { weight_kg: 80, reps: 7, rir: 2 },
          { weight_kg: 80, reps: 7, rir: 1 },
        ],
        last_set_count: 2,
        rep_min: 6,
        rep_max: 10,
        weight_step: 2.5,
        action: 'reps',
        weight_kg: 80,
        reps: 8,
        rir_known: true,
        same_sessions: 1,
        stagnant: false,
      },
    }
    const exercise = exerciseFrom(template, 'kg')
    expect(exercise.sets).toHaveLength(2)
    expect(exercise.sets[0]).toMatchObject({ weight: '80', reps: '8', done: false })

    const draft: Draft = {
      client_id: 'abc',
      workout_name: 'Push A',
      started_at: '2026-11-10T16:00:00Z',
      ended_at: null,
      changed_at: '2026-11-10T16:10:00Z',
      synced_at: null,
      unit: 'kg',
      exercises: [
        {
          ...exercise,
          sets: [
            { weight: '82,5', reps: '8', rir: '2', done: true },
            { weight: '82,5', reps: '8', rir: '', done: false },
          ],
        },
      ],
    }
    const payload = toPayload(draft)
    expect(payload.exercises[0].sets).toEqual([{ weight_kg: 82.5, reps: 8, rir: 2 }])
  })
})
