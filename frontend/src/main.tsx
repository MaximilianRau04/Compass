import './index.css'

import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import { Toaster } from 'sonner'

import { Layout } from './components/Layout'
import { LegacyRedirect } from './components/LegacyRedirect'
import { I18nProvider } from './i18n/I18nProvider'
import { LEGACY_PATHS } from './lib/legacy'
import { initPreferences, openStartPage } from './lib/preferences'
import { registerServiceWorker } from './lib/pwa'
import { persistOptions, queryClient } from './lib/queryCache'
import { CalendarPage } from './pages/Calendar'
import { CorrelationsPage } from './pages/Correlations'
import { FinancePage } from './pages/Finance'
import { JournalPage } from './pages/Journal'
import { MailPage } from './pages/Mail'
import { NewsPage } from './pages/News'
import { NotesPage } from './pages/Notes'
import { NutritionPage } from './pages/Nutrition'
import { SharePage } from './pages/Share'
import { SleepPage } from './pages/Sleep'
import { TasksPage } from './pages/Tasks'
import { TodayPage } from './pages/Today'
import { TrainingPage } from './pages/Training'
import { WelcomePage } from './pages/Welcome'
import { WorkoutLogPage } from './pages/WorkoutLog'

registerServiceWorker()
initPreferences()
openStartPage()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<TodayPage />} />
            <Route path="tasks" element={<TasksPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="mail" element={<MailPage />} />
            <Route path="news" element={<NewsPage />} />
            <Route path="notes" element={<NotesPage />} />
            <Route path="journal" element={<JournalPage />} />
            <Route path="correlations" element={<CorrelationsPage />} />
            <Route path="training" element={<TrainingPage />} />
            <Route path="training/log" element={<WorkoutLogPage />} />
            <Route path="sleep" element={<SleepPage />} />
            <Route path="nutrition" element={<NutritionPage />} />
            <Route path="finance" element={<FinancePage />} />
            {/* Push messages still link here; the layout opens the settings dialog. */}
            <Route path="settings" element={<Navigate to="/" replace state={{ settings: true }} />} />
            <Route path="share" element={<SharePage />} />
            <Route path="welcome" element={<WelcomePage />} />
            {Object.entries(LEGACY_PATHS).map(([from, to]) => (
              <Route key={from} path={from} element={<LegacyRedirect to={to} />} />
            ))}
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          className: '!bg-paper-raised !text-ink !border-rule !font-sans',
        }}
      />
    </PersistQueryClientProvider>
    </I18nProvider>
  </StrictMode>,
)
