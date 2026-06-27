import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { CopilotKit } from '@copilotkit/react-core'
import { CopilotSidebar } from '@copilotkit/react-ui'
import Dashboard from './components/Layout/Dashboard'
import ChatPage from './pages/ChatPage'
import FactorsPage from './pages/FactorsPage'
import StrategiesPage from './pages/StrategiesPage'
import BacktestPage from './pages/BacktestPage'
import PortfolioPage from './pages/PortfolioPage'
import SettingsPage from './pages/SettingsPage'
import '@copilotkit/react-ui/styles.css'

function App() {
  return (
    <CopilotKit
      runtimeUrl="/api/chat"
    >
      <CopilotSidebar
        defaultOpen={false}
        labels={{
          title: 'AIFUND5 助手',
          initial: '你好！我是 AIFUND5 量化投资助手。可以帮你选股、构建策略、运行回测。试试说：帮我用动量因子选前10只股票',
        }}
      >
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Dashboard />}>
              <Route index element={<Navigate to="/chat" replace />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="factors" element={<FactorsPage />} />
              <Route path="strategies" element={<StrategiesPage />} />
              <Route path="backtest" element={<BacktestPage />} />
              <Route path="portfolio" element={<PortfolioPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </CopilotSidebar>
    </CopilotKit>
  )
}

export default App
