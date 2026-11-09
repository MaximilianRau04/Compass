import { useMemo } from 'react'

import { useI18n } from '../i18n/context'
import { compact, decimal } from './format'
import { type Units, usePreferences } from './preferences'

/*
 * Units for showing and entering measures. The API, the database and the MCP tools stay metric
 * (kg, cm, km); only what is shown and typed here is converted.
 */

export type WeightUnit = 'kg' | 'lb'

const KG_PER_LB = 0.45359237
const CM_PER_IN = 2.54
const KM_PER_MI = 1.609344

export const weightUnitOf = (units: Units): WeightUnit => (units === 'imperial' ? 'lb' : 'kg')

export const fromKg = (kg: number, unit: WeightUnit) => (unit === 'lb' ? kg / KG_PER_LB : kg)

/** A typed weight in kg, to 10 g as the database keeps it. */
export const toKg = (value: number, unit: WeightUnit) => (unit === 'lb' ? Math.round(value * KG_PER_LB * 100) / 100 : value)

/** A weight for an input field in the unit, rounded to 0.1 lb so it reads like typed. */
export const weightField = (kg: number, unit: WeightUnit) => String(unit === 'lb' ? Math.round(fromKg(kg, unit) * 10) / 10 : kg)

export interface UnitFormat {
  weightUnit: WeightUnit
  lengthUnit: 'cm' | 'in'
  distanceUnit: 'km' | 'mi'
  /** kg → number in the weight unit, e.g. for chart values */
  weight: (kg: number) => number
  /** number typed in the weight unit → kg */
  toKg: (value: number) => number
  length: (cm: number) => number
  toCm: (value: number) => number
  distance: (km: number) => number
  /** "82,5 kg" / "181.9 lb" from kg */
  formatWeight: (kg: number) => string
  /** A large weight in short form: "12,3K kg" */
  formatVolume: (kg: number) => string
  formatLength: (cm: number) => string
  formatDistance: (km: number) => string
}

export function useUnits(): UnitFormat {
  const { locale } = useI18n()
  const { units } = usePreferences()
  return useMemo(() => {
    const imperial = units === 'imperial'
    const weightUnit = weightUnitOf(units)
    const lengthUnit = imperial ? 'in' : 'cm'
    const distanceUnit = imperial ? 'mi' : 'km'
    const weight = (kg: number) => fromKg(kg, weightUnit)
    const length = (cm: number) => (imperial ? cm / CM_PER_IN : cm)
    const distance = (km: number) => (imperial ? km / KM_PER_MI : km)
    return {
      weightUnit,
      lengthUnit,
      distanceUnit,
      weight,
      toKg: (value) => toKg(value, weightUnit),
      length,
      toCm: (value) => (imperial ? Math.round(value * CM_PER_IN * 10) / 10 : value),
      distance,
      formatWeight: (kg) => `${decimal(weight(kg), locale)} ${weightUnit}`,
      formatVolume: (kg) => `${compact(weight(kg), locale)} ${weightUnit}`,
      formatLength: (cm) => `${decimal(length(cm), locale)} ${lengthUnit}`,
      formatDistance: (km) => `${decimal(distance(km), locale)} ${distanceUnit}`,
    }
  }, [units, locale])
}
