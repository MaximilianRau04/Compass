import { describe, expect, it } from 'vitest'

import { checklist, toggled, withNewItem } from './checklist'

const NOTES = ['Before the weekend:', '- [x] get boxes', '- [ ] rent a van', '  * [X] indented\r', '- [ ]', '-[ ] no item', '- [] neither', 'The end'].join('\n')

describe('checklist', () => {
  it('finds the items with their lines and leaves other text alone', () => {
    expect(checklist(NOTES)).toEqual([
      { line: 1, done: true, text: 'get boxes' },
      { line: 2, done: false, text: 'rent a van' },
      { line: 3, done: true, text: 'indented' },
    ])
    expect(checklist(null)).toEqual([])
    expect(checklist('just a note')).toEqual([])
  })
})

describe('toggled', () => {
  it('ticks and unticks one line and keeps the rest of the text', () => {
    expect(toggled(NOTES, 2).split('\n')[2]).toBe('- [x] rent a van')
    expect(toggled(NOTES, 1).split('\n')[1]).toBe('- [ ] get boxes')
    expect(toggled(NOTES, 3).split('\n')[3]).toBe('  * [ ] indented\r')
    expect(toggled(toggled(NOTES, 2), 2)).toBe(NOTES)
  })

  it('does nothing on a line that is not an item', () => {
    expect(toggled(NOTES, 0)).toBe(NOTES)
    expect(toggled(NOTES, 99)).toBe(NOTES)
  })
})

describe('withNewItem', () => {
  it('starts an item on a new last line', () => {
    expect(withNewItem('')).toBe('- [ ] ')
    expect(withNewItem('a')).toBe('a\n- [ ] ')
    expect(withNewItem('a\n')).toBe('a\n- [ ] ')
  })
})
