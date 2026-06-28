import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ErrorBoundary from './components/Common/ErrorBoundary'
import Dashboard from './components/Layout/Dashboard'
import ChatPage from './pages/ChatPage'
import HistoryPage from './pages/HistoryPage'
import FactorsPage from './pages/FactorsPage'
import StrategiesPage from './pages/StrategiesPage'
import BacktestPage from './pages/BacktestPage'
import PortfolioPage from './pages/PortfolioPage'
import SettingsPage from './pages/SettingsPage'

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />}>
            <Route index element={<Navigate to="/chat" replace />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="chat/:id" element={<ChatPage />} />
            <Route path="history" element={<HistoryPage />} />
            <Route path="factors" element={<FactorsPage />} />
            <Route path="strategies" element={<StrategiesPage />} />
            <Route path="backtest" element={<BacktestPage />} />
            <Route path="portfolio" element={<PortfolioPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}

export default App
