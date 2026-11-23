export type MessageVars = Record<string, string | number>

/**
 * Interpolates `{name}` placeholders and `{name|singular|plural}` forms (1 -> singular, else plural).
 */
export function formatMessage(template: string, vars?: MessageVars): string {
  return template
    .replace(/\{(\w+)\|([^|{}]*)\|([^{}]*)\}/g, (match, name: string, one: string, other: string) => {
      const value = vars?.[name]
      if (value === undefined) return match
      return Number(value) === 1 ? one : other
    })
    .replace(/\{(\w+)\}/g, (_, name: string) => String(vars?.[name] ?? `{${name}}`))
}
