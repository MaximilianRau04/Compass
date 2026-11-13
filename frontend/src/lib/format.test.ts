import { describe, expect, it } from 'vitest'

import type { CalendarEvent } from '../api/types'
import { addDays, daysBetween, eventOnDay, isLeftBehind, isOverdue, localDay, parseAmount, rangeDays, recurrenceLabel, relativeDay, shortTime } from './format'
import { t, task } from './testing'

const TODAY = '2026-11-13' // a Friday

describe('days', () => {
  it('counts and adds calendar days across a change of the clocks', () => {
    // Summer time ends on 25 October 2026 and starts on 29 March.
    expect(daysBetween('2026-10-24', '2026-10-26')).toBe(2)
    expect(daysBetween('2026-03-28', '2026-03-30')).toBe(2)
    expect(daysBetween(TODAY, '2026-11-10')).toBe(-3)
    expect(addDays('2026-10-24', 1)).toBe('2026-10-25')
    expect(addDays('2026-10-25', 1)).toBe('2026-10-26')
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01')
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28')
    expect(rangeDays('2026-10-24', '2026-10-26')).toEqual(['2026-10-24', '2026-10-25', '2026-10-26'])
  })

  it('takes the day of a timestamp at home, not in UTC', () => {
    expect(localDay('2026-10-19T22:30:00Z')).toBe('2026-10-20')
    expect(localDay('2026-10-19T21:30:00Z')).toBe('2026-10-19')
  })
})

describe('relativeDay', () => {
  it('names the days around today', () => {
    expect(relativeDay(TODAY, TODAY, t, 'en-GB')).toBe('date.today')
    expect(relativeDay('2026-11-14', TODAY, t, 'en-GB')).toBe('date.tomorrow')
    expect(relativeDay('2026-11-15', TODAY, t, 'en-GB')).toBe('date.dayAfterTomorrow')
    expect(relativeDay('2026-11-12', TODAY, t, 'en-GB')).toBe('date.yesterday')
    expect(relativeDay('2026-11-10', TODAY, t, 'en-GB')).toBe('date.daysAgo {"n":3}')
  })

  it('writes other days as a date, with the weekday within a week and the year when it differs', () => {
    const soon = relativeDay('2026-11-18', TODAY, t, 'en-GB')
    expect(soon).toContain('Wed')
    expect(soon).toContain('18')
    expect(soon).toContain('Nov')
    const later = relativeDay('2026-12-24', TODAY, t, 'en-GB')
    expect(later).not.toContain('Thu')
    expect(later).not.toContain('2026')
    expect(relativeDay('2027-01-04', TODAY, t, 'en-GB')).toContain('2027')
    expect(relativeDay('2026-10-01', TODAY, t, 'de-DE')).toBe('1.10.')
  })
})

describe('tasks', () => {
  it('is overdue once the deadline has passed and it is still open', () => {
    expect(isOverdue(task({ due_date: '2026-11-12' }), TODAY)).toBe(true)
    expect(isOverdue(task({ due_date: TODAY }), TODAY)).toBe(false)
    expect(isOverdue(task({ due_date: '2026-11-12', status: 'done' }), TODAY)).toBe(false)
    expect(isOverdue(task({ scheduled_date: '2026-11-12' }), TODAY)).toBe(false)
  })

  it('is left behind when the deadline or the planned day has passed', () => {
    expect(isLeftBehind(task({ due_date: '2026-11-12' }), TODAY)).toBe(true)
    expect(isLeftBehind(task({ scheduled_date: '2026-11-12', due_date: '2026-11-20' }), TODAY)).toBe(true)
    expect(isLeftBehind(task({ scheduled_date: TODAY }), TODAY)).toBe(false)
    expect(isLeftBehind(task({ scheduled_date: '2026-11-12', status: 'cancelled' }), TODAY)).toBe(false)
    expect(isLeftBehind(task(), TODAY)).toBe(false)
  })

  it('shortens a time to hours and minutes', () => {
    expect(shortTime('14:00:00')).toBe('14:00')
    expect(shortTime(null)).toBeNull()
  })

  it('names the common repetitions and shows any other rule as it is', () => {
    expect(recurrenceLabel(null, t, 'en-GB')).toBeNull()
    expect(recurrenceLabel('FREQ=DAILY', t, 'en-GB')).toBe('recur.daily')
    expect(recurrenceLabel('FREQ=WEEKLY;INTERVAL=2', t, 'en-GB')).toBe('recur.everyNWeeks {"n":2}')
    expect(recurrenceLabel('FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', t, 'en-GB')).toBe('recur.weekdays')
    expect(recurrenceLabel('FREQ=WEEKLY;BYDAY=TH', t, 'en-GB')).toBe('recur.everyWeekday {"day":"Thursday"}')
    expect(recurrenceLabel('FREQ=HOURLY', t, 'en-GB')).toBe('FREQ=HOURLY')
  })
})

describe('eventOnDay', () => {
  const event = (fields: Partial<CalendarEvent>) => ({ all_day: false, ends_at: null, ...fields }) as CalendarEvent

  it('puts an event on the local day it starts, and an all-day one on every day before its end', () => {
    expect(eventOnDay(event({ starts_at: '2026-11-13T23:30:00Z' }), '2026-11-14')).toBe(true)
    const trip = event({ all_day: true, starts_at: '2026-11-13T00:00:00+01:00', ends_at: '2026-11-15T00:00:00+01:00' })
    expect(['2026-11-12', '2026-11-13', '2026-11-14', '2026-11-15'].map((day) => eventOnDay(trip, day))).toEqual([false, true, true, false])
  })
})

describe('parseAmount', () => {
  it('reads an amount typed in either way', () => {
    expect(parseAmount('1.000,50', 'de-DE')).toBe(1000.5)
    expect(parseAmount('1,000.50', 'de-DE')).toBe(1000.5)
    expect(parseAmount('1,5', 'de-DE')).toBe(1.5)
    expect(parseAmount('1.5', 'de-DE')).toBe(1.5)
    expect(parseAmount('1,000', 'en-GB')).toBe(1000)
    expect(parseAmount('1.000', 'de-DE')).toBe(1000)
    expect(parseAmount(' 12 € ', 'de-DE')).toBe(12)
    expect(parseAmount('', 'de-DE')).toBeNaN()
  })
})
