import { describe, expect, it } from 'vitest'

import { formatMessage } from './format'

describe('formatMessage', () => {
  it('replaces simple variables and keeps unknown placeholders intact', () => {
    expect(formatMessage('Hello {name}', { name: 'Compass' })).toBe('Hello Compass')
    expect(formatMessage('Keep {code} here')).toBe('Keep {code} here')
  })

  it('picks singular for 1 and plural for 0 or >1', () => {
    const tpl = '{n} {n|Tag|Tage}'
    expect(formatMessage(tpl, { n: 0 })).toBe('0 Tage')
    expect(formatMessage(tpl, { n: 1 })).toBe('1 Tag')
    expect(formatMessage(tpl, { n: 5 })).toBe('5 Tage')
  })
})
