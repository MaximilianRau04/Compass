import type { ImportResult } from '../api/types'
import type { Translate } from '../i18n/context'

export function importMessage(result: ImportResult, t: Translate): string {
  if (result.sets_created + result.sets_updated === 0) return t('training.importNothing', { rows: result.rows })
  return t('training.imported', {
    sets: result.sets_created,
    updated: result.sets_updated,
    sessions: result.sessions_created,
  })
}
