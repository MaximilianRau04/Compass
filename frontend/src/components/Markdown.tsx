import type { ReactNode } from 'react'

/*
 * A small Markdown subset for the texts Claude saves (daily brief, news report): headings,
 * lists, paragraphs, **bold**, `code` and [links](https://...). Everything becomes React
 * elements, never HTML, and only http(s) links are linked, because the texts are partly built
 * from web content.
 */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g
const LINK = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="font-mono text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      )
    }
    const link = LINK.exec(part)
    if (link) {
      return (
        <a key={i} href={link[2]} target="_blank" rel="noopener noreferrer nofollow" className="text-brass underline decoration-brass/40 underline-offset-2 hover:decoration-brass">
          {link[1]}
        </a>
      )
    }
    return part
  })
}

type Block = { type: 'h'; level: number; text: string } | { type: 'ul' | 'ol'; items: string[] } | { type: 'p'; lines: string[] }

function blocks(source: string): Block[] {
  const out: Block[] = []
  for (const raw of source.split('\n')) {
    const line = raw.trimEnd()
    const last = out[out.length - 1]
    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (!line.trim()) out.push({ type: 'p', lines: [] })
    else if (heading) out.push({ type: 'h', level: heading[1].length, text: heading[2] })
    else if (bullet || numbered) {
      const type = bullet ? 'ul' : 'ol'
      const text = (bullet ?? numbered)![1]
      if (last?.type === type) last.items.push(text)
      else out.push({ type, items: [text] })
    } else if (last?.type === 'p') last.lines.push(line)
    else out.push({ type: 'p', lines: [line] })
  }
  return out.filter((b) => b.type !== 'p' || b.lines.length > 0)
}

export function Markdown({ text, className = '' }: { text: string; className?: string }) {
  return (
    <div className={`space-y-2 leading-relaxed ${className}`}>
      {blocks(text).map((block, i) => {
        if (block.type === 'h') {
          return (
            <h3 key={i} className={block.level <= 2 ? 'pt-1 font-display text-[13px] font-semibold tracking-[0.18em] text-muted uppercase' : 'font-semibold'}>
              {inline(block.text)}
            </h3>
          )
        }
        if (block.type === 'p') {
          return (
            <p key={i}>
              {block.lines.map((line, j) => (
                <span key={j}>
                  {j > 0 && <br />}
                  {inline(line)}
                </span>
              ))}
            </p>
          )
        }
        const List = block.type
        return (
          <List key={i} className={`space-y-1 pl-5 ${block.type === 'ul' ? 'list-disc marker:text-brass' : 'list-decimal marker:text-muted'}`}>
            {block.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        )
      })}
    </div>
  )
}
