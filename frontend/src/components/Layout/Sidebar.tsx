import { NavLink } from 'react-router-dom'

const navItems = [
  { path: '/chat', label: '对话', icon: '💬' },
  { path: '/factors', label: '因子库', icon: '📊' },
  { path: '/strategies', label: '策略', icon: '📋' },
  { path: '/backtest', label: '回测', icon: '📈' },
  { path: '/portfolio', label: '仓位', icon: '💰' },
  { path: '/settings', label: '设置', icon: '⚙️' },
]

export default function Sidebar() {
  return (
    <aside
      className="w-16 flex flex-col items-center py-4 border-r"
      style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
    >
      {/* Logo */}
      <div className="mb-8 text-xl font-bold" style={{ color: 'var(--accent)' }}>
        A5
      </div>

      {/* Navigation items */}
      <nav className="flex flex-col gap-2 flex-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 px-2 py-2 rounded-lg transition-colors ${
                isActive ? 'opacity-100' : 'opacity-50 hover:opacity-75'
              }`
            }
            style={({ isActive }) => ({
              backgroundColor: isActive ? 'var(--bg-tertiary)' : 'transparent',
            })}
          >
            <span className="text-lg">{item.icon}</span>
            <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
              {item.label}
            </span>
          </NavLink>
        ))}
      </nav>

      {/* Data status indicator */}
      <div className="mt-auto mb-2">
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: 'var(--success)' }}
          title="数据已连接"
        />
      </div>
    </aside>
  )
}
