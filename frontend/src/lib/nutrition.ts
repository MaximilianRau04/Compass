import type { MfpImportResult } from '../api/types'
import type { Translate } from '../i18n/context'

export function mfpImportMessage(result: MfpImportResult, t: Translate): string {
  if (result.meals_created + result.meals_updated + result.weights_created === 0) return t('nutrition.importNothing')
  return t('nutrition.imported', {
    meals: result.meals_created,
    updated: result.meals_updated,
    days: result.days,
    weights: result.weights_created,
  })
}

/** Whether a shared or picked file is a MyFitnessPal export rather than a workout export: the
 * zip MFP mails, or a CSV with its German or English nutrition or weight header. */
export async function isMfpExport(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 400).arrayBuffer())
  if (head[0] === 0x50 && head[1] === 0x4b) return true // "PK", a zip
  const firstLine = new TextDecoder().decode(head).replace(/^﻿/, '').split(/\r?\n/)[0]
  return /^(Datum|Date),(Mahlzeit|Meal|Gewicht|Weight)\b/.test(firstLine)
}

export const kcal = (value: number, locale: string) => `${Math.round(value).toLocaleString(locale)} kcal`
export const grams = (value: number) => `${Math.round(value)} g`
