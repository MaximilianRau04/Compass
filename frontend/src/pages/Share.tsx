import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { useCreateNote } from '../api/notes'
import { useImportMfp } from '../api/nutrition'
import { useTodayDate } from '../api/tasks'
import { useImportWorkouts } from '../api/training'
import { QuickAdd } from '../components/QuickAdd'
import { useI18n } from '../i18n/context'
import { isMfpExport, mfpImportMessage } from '../lib/nutrition'
import { importMessage } from '../lib/training'

// Written by public/share-target-sw.js when a file is shared to Compass.
const SHARE_CACHE = 'compass-share'
const SHARED_FILE = '/__shared/file'

function SharedFile({ name }: { name: string }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const workouts = useImportWorkouts()
  const mfp = useImportMfp()
  const [file, setFile] = useState<Blob | null | undefined>(undefined)
  const [isMfp, setIsMfp] = useState(false)

  useEffect(() => {
    caches
      .open(SHARE_CACHE)
      .then((cache) => cache.match(SHARED_FILE))
      .then((response) => (response ? response.blob() : null))
      .then(async (blob) => {
        if (blob) setIsMfp(await isMfpExport(blob))
        setFile(blob)
      })
      .catch(() => setFile(null))
  }, [])

  const done = async (message: string, page: string) => {
    toast(message)
    await caches.open(SHARE_CACHE).then((cache) => cache.delete(SHARED_FILE))
    navigate(page)
  }
  const onError = (error: Error) => toast.error(error.message)
  const pending = workouts.isPending || mfp.isPending

  const run = () => {
    if (!file) return
    if (isMfp) mfp.mutate(file, { onSuccess: (r) => done(mfpImportMessage(r, t), '/nutrition'), onError })
    else workouts.mutate(file, { onSuccess: (r) => done(importMessage(r, t), '/training'), onError })
  }

  return (
    <div className="space-y-4">
      <p className="font-mono text-sm">{t('share.file', { name })}</p>
      {file === null && <p className="text-signal">{t('share.fileMissing')}</p>}
      {file && (
        <button
          type="button"
          onClick={run}
          disabled={pending}
          className="rounded-md bg-brass px-4 py-2 font-medium text-brass-ink hover:opacity-90 disabled:opacity-50"
        >
          {pending ? t('training.importing') : t(isMfp ? 'share.importMfp' : 'share.importWorkouts')}
        </button>
      )}
    </div>
  )
}

/** Shared text or link as a note: the shared title as title, the rest as text. */
function SaveAsNote({ title, text }: { title: string; text: string }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const create = useCreateNote()
  // Without a shared title, the first line (shortened) is the title and the text stays whole.
  const heading = title || text.split('\n')[0].slice(0, 120)
  return (
    <button
      type="button"
      disabled={create.isPending || !text}
      onClick={() =>
        create.mutate(
          { title: heading, body: title || heading !== text ? text : '', source: 'share' },
          {
            onSuccess: (note) => {
              toast.success(t('quick.noteCreated', { title: note.title }))
              navigate(`/notes?id=${note.id}`)
            },
            onError: (error) => toast.error(error.message),
          },
        )
      }
      className="mt-4 rounded-md border border-brass px-4 py-2 text-sm text-brass hover:bg-brass/10 disabled:opacity-50"
    >
      {t('share.asNote')}
    </button>
  )
}

/** Target of the Android share sheet (Web Share Target): shared text or links become a task,
 * or a note, a shared workout export is imported as training data, a MyFitnessPal export as
 * nutrition. */
export function SharePage() {
  const { t } = useI18n()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const today = useTodayDate()

  const parts = ['title', 'text', 'url'].map((key) => params.get(key)?.trim()).filter(Boolean) as string[]
  const text = [...new Set(parts)].join(' ')
  const sharedTitle = params.get('title')?.trim() ?? ''
  const noteBody = [...new Set(['text', 'url'].map((key) => params.get(key)?.trim()).filter(Boolean))].filter((v) => v !== sharedTitle).join('\n\n')
  const file = params.get('file')

  return (
    <>
      <h1 className="mb-2 font-display text-5xl leading-none font-semibold tracking-tight uppercase">{t('share.title')}</h1>
      {file ? (
        <SharedFile name={file} />
      ) : (
        <>
          <p className="mb-6 text-muted">{t('share.hint')}</p>
          <QuickAdd today={today} initialText={text} autoFocus onCreated={() => navigate('/')} />
          <SaveAsNote title={noteBody ? sharedTitle : ''} text={noteBody || text} />
        </>
      )}
    </>
  )
}
