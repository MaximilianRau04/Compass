import type { NutritionImportResult } from '../api/types'
import type { Translate } from '../i18n/context'

export function nutritionImportMessage(result: NutritionImportResult, t: Translate): string {
  if (result.meals_created + result.meals_updated + result.weights_created === 0) return t('nutrition.importNothing')
  return t('nutrition.imported', {
    meals: result.meals_created,
    updated: result.meals_updated,
    days: result.days,
    weights: result.weights_created,
  })
}

/** Whether a shared or picked file is a nutrition export rather than a workout export: a zip, or a
 * CSV with the header of MyFitnessPal, Lose It! or Cronometer. */
export async function isNutritionExport(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 400).arrayBuffer())
  if (head[0] === 0x50 && head[1] === 0x4b) return true // "PK", a zip
  const firstLine = new TextDecoder().decode(head).replace(/^﻿/, '').split(/\r?\n/)[0].replaceAll('"', '')
  return /^(Datum|Date),(Mahlzeit|Meal|Gewicht|Weight|Name)\b|^Day,.*\b(Food Name|Metric)\b/.test(firstLine)
}

export const kcal = (value: number, locale: string) => `${Math.round(value).toLocaleString(locale)} kcal`
export const grams = (value: number) => `${Math.round(value)} g`
