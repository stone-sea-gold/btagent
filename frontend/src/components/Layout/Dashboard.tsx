import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function Dashboard() {
  return (
    <div className="flex h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
      {/* Left sidebar navigation */}
      <Sidebar />

      {/* Main content area */}
      <main className="flex-1 overflow-auto" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="h-full p-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
