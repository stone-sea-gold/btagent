import { useState, useEffect } from 'react'

interface Strategy {
  strategy_id: string
  name: string
  description: string
  version: number
  parent_id: string | null
  created_at: string
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchStrategies()
  }, [])

  const fetchStrategies = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/strategies?limit=50')
      const data = await res.json()
      setStrategies(data.strategies || [])
    } catch (err) {
      console.error('Failed to fetch strategies:', err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        策略管理
      </h1>

      <p className="text-sm mb-3" style={{ color: 'var(--text-muted)' }}>
        共 {strategies.length} 个策略
      </p>

      <div className="flex-1 overflow-auto rounded-lg border" style={{ borderColor: 'var(--border)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <th className="px-4 py-3 text-left font-medium" style={{ color: 'var(--text-secondary)' }}>名称</th>
              <th className="px-4 py-3 text-left font-medium" style={{ color: 'var(--text-secondary)' }}>版本</th>
              <th className="px-4 py-3 text-left font-medium" style={{ color: 'var(--text-secondary)' }}>描述</th>
              <th className="px-4 py-3 text-left font-medium" style={{ color: 'var(--text-secondary)' }}>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center" style={{ color: 'var(--text-muted)' }}>
                  加载中...
                </td>
              </tr>
            ) : strategies.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center" style={{ color: 'var(--text-muted)' }}>
                  暂无策略
                </td>
              </tr>
            ) : (
              strategies.map((s) => (
                <tr
                  key={s.strategy_id}
                  className="border-t hover:opacity-80"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <td className="px-4 py-3 font-medium" style={{ color: 'var(--text-primary)' }}>
                    {s.name}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="px-2 py-1 rounded text-xs"
                      style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                    >
                      v{s.version}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs max-w-md truncate" style={{ color: 'var(--text-secondary)' }}>
                    {s.description || '-'}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                    {new Date(s.created_at).toLocaleString('zh-CN')}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
