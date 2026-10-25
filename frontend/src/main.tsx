import './index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router'
import { Toaster } from 'sonner'

import { Layout } from './components/Layout'
import { I18nProvider } from './i18n/I18nProvider'
import { CalendarPage } from './pages/Calendar'
import { MailPage } from './pages/Mail'
import { NewsPage } from './pages/News'
import { NotesPage } from './pages/Notes'
import { NutritionPage } from './pages/Nutrition'
import { SettingsPage } from './pages/Settings'
import { SharePage } from './pages/Share'
import { SleepPage } from './pages/Sleep'
import { TasksPage } from './pages/Tasks'
import { TodayPage } from './pages/Today'
import { TrainingPage } from './pages/Training'
import { WorkoutLogPage } from './pages/WorkoutLog'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <I18nProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<TodayPage />} />
            <Route path="aufgaben" element={<TasksPage />} />
            <Route path="kalender" element={<CalendarPage />} />
            <Route path="mail" element={<MailPage />} />
            <Route path="news" element={<NewsPage />} />
            <Route path="notizen" element={<NotesPage />} />
            <Route path="training" element={<TrainingPage />} />
            <Route path="training/log" element={<WorkoutLogPage />} />
            <Route path="schlaf" element={<SleepPage />} />
            <Route path="ernaehrung" element={<NutritionPage />} />
            <Route path="einstellungen" element={<SettingsPage />} />
            <Route path="share" element={<SharePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          className: '!bg-paper-raised !text-ink !border-rule !font-sans',
        }}
      />
    </QueryClientProvider>
    </I18nProvider>
  </StrictMode>,
)
