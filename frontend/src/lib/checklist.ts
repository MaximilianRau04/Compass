/**
 * Checklist lines in the notes of a task: "- [ ] rent a van" is open, "- [x] get boxes" is done.
 * The notes stay plain text, so Claude and the search read them as before.
 */
const ITEM = /^(\s*[-*] \[)([ xX])(\] ?)(.*?)(\r?)$/

export interface ChecklistItem {
  /** The index of its line in the notes. */
  line: number
  done: boolean
  text: string
}

export function checklist(notes: string | null): ChecklistItem[] {
  return (notes ?? '').split('\n').flatMap((text, line) => {
    const match = ITEM.exec(text)
    return match && match[4].trim() ? [{ line, done: match[2] !== ' ', text: match[4] }] : []
  })
}

/** The notes with the item on that line ticked, or unticked if it was done. */
export function toggled(notes: string, line: number): string {
  return notes
    .split('\n')
    .map((text, i) =>
      i === line ? text.replace(ITEM, (_, start, mark, end, rest, cr) => `${start}${mark === ' ' ? 'x' : ' '}${end}${rest}${cr}`) : text,
    )
    .join('\n')
}

/** The notes with an empty item on a new last line, ready to be typed. */
export function withNewItem(notes: string): string {
  return `${notes}${notes === '' || notes.endsWith('\n') ? '' : '\n'}- [ ] `
}
