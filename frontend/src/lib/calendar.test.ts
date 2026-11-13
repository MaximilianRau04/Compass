import { describe, expect, it } from 'vitest'

import { addMonths, isoWeek, monthGrid, nextWeekStart, tasksOn, weekStart } from './calendar'
import { task } from './testing'

describe('weeks', () => {
  it('start on Monday', () => {
    expect(weekStart('2026-11-13')).toBe('2026-11-09')
    expect(weekStart('2026-11-15')).toBe('2026-11-09')
    expect(weekStart('2026-11-09')).toBe('2026-11-09')
  })

  it('next week is the Monday after, also seen from a Sunday or a Monday', () => {
    expect(nextWeekStart('2026-11-13')).toBe('2026-11-16')
    expect(nextWeekStart('2026-11-15')).toBe('2026-11-16')
    expect(nextWeekStart('2026-11-16')).toBe('2026-11-23')
    expect(nextWeekStart('2026-12-30')).toBe('2027-01-04')
  })

  it('are numbered as in ISO 8601', () => {
    expect(isoWeek('2026-11-13')).toBe(46)
    expect(isoWeek('2025-12-29')).toBe(1)
    expect(isoWeek('2026-01-01')).toBe(1)
    expect(isoWeek('2026-12-31')).toBe(53)
    expect(isoWeek('2027-01-03')).toBe(53)
    expect(isoWeek('2027-01-04')).toBe(1)
  })
})

describe('months', () => {
  it('step from the first of a month, so the 31st does not skip one', () => {
    expect(addMonths('2026-01-31', 1)).toBe('2026-02-01')
    expect(addMonths('2026-12-15', 1)).toBe('2027-01-01')
    expect(addMonths('2026-03-10', -1)).toBe('2026-02-01')
  })

  it('are laid out in full weeks', () => {
    const grid = monthGrid('2026-11-13')
    expect(grid[0]).toBe('2026-10-26')
    expect(grid.at(-1)).toBe('2026-12-06')
    expect(grid).toHaveLength(42)
    // October 2026 holds the end of summer time and still has every day once.
    expect(new Set(monthGrid('2026-10-01')).size).toBe(monthGrid('2026-10-01').length)
  })
})

describe('tasksOn', () => {
  it('shows a task on its deadline, or on its planned day when the deadline is elsewhere', () => {
    const tasks = [
      task({ id: 1, due_date: '2026-11-13' }),
      task({ id: 2, scheduled_date: '2026-11-13', due_date: '2026-11-20' }),
      task({ id: 3, scheduled_date: '2026-11-13', due_date: '2026-11-13' }),
      task({ id: 4, scheduled_date: '2026-11-14' }),
    ]
    expect(tasksOn(tasks, '2026-11-13').map((entry) => entry.id)).toEqual([1, 2, 3])
    expect(tasksOn(tasks, '2026-11-20').map((entry) => entry.id)).toEqual([2])
  })
})
