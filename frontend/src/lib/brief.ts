/**
 * The short part of a report for the today page: the "## Kurz" (or "## Short") section the news
 * routine writes first, otherwise the first three bullet points.
 */
export function shortPart(body: string, bullets = 3): string {
  const lines = body.split('\n')
  const start = lines.findIndex((line) => /^#{1,3}\s+(kurz|short|tl;dr|das wichtigste)\b/i.test(line.trim()))
  if (start >= 0) {
    const rest = lines.slice(start + 1)
    const end = rest.findIndex((line) => /^#{1,3}\s/.test(line.trim()))
    const section = (end >= 0 ? rest.slice(0, end) : rest).join('\n').trim()
    if (section) return section
  }
  return lines
    .filter((line) => /^\s*[-*•]\s+/.test(line))
    .slice(0, bullets)
    .join('\n')
}
