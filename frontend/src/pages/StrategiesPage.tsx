import { useState, useEffect, useRef } from 'react'

interface Strategy {
  strategy_id: string
  name: string
  description: string
  version: number
  latest_version?: number
  parent_id: string | null
  created_at: string
  updated_at?: string
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [fadingOut, setFadingOut] = useState<Set<string>>(new Set())
  const [hoverDesc, setHoverDesc] = useState<string | null>(null)
  const [hoverTarget, setHoverTarget] = useState<{ x: number; y: number } | null>(null)
  const hoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchStrategies()
  }, [])

  const fetchStrategies = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/strategies/?limit=50')
      if (!res.ok) {
        throw new Error(`请求失败: ${res.status}`)
      }
      const data = await res.json()
      setStrategies(data.strategies || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : '未知错误'
      console.error('Failed to fetch strategies:', err)
      setError(`加载策略失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (strategyId: string, name: string) => {
    if (!confirm(`确定要删除策略 "${name}" 吗？此操作不可撤销。`)) {
      return
    }
    // Start fade-out animation
    setFadingOut((prev) => new Set(prev).add(strategyId))

    // Wait for animation to complete before removing
    setTimeout(async () => {
      setDeleting(strategyId)
      try {
        const res = await fetch(`/api/strategies/${strategyId}`, { method: 'DELETE' })
        if (!res.ok) {
          throw new Error(`删除失败: ${res.status}`)
        }
        setStrategies((prev) => prev.filter((s) => s.strategy_id !== strategyId))
      } catch (err) {
        const message = err instanceof Error ? err.message : '未知错误'
        alert(`删除失败: ${message}`)
      } finally {
        setDeleting(null)
        setFadingOut((prev) => { const n = new Set(prev); n.delete(strategyId); return n })
      }
    }, 400) // match animation duration
  }

  const handleDescHover = (desc: string, e: React.MouseEvent) => {
    if (!desc || desc === '-') return
    setHoverDesc(desc)
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setHoverTarget({ x: rect.left + rect.width / 2, y: rect.top })
  }

  const handleDescLeave = () => {
    setHoverDesc(null)
    setHoverTarget(null)
  }

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        策略管理
      </h1>

      {error && (
        <div
          className="mb-4 px-4 py-3 rounded-lg flex items-center justify-between"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid var(--danger)',
          }}
        >
          <p className="text-sm" style={{ color: 'var(--danger)' }}>{error}</p>
          <button
            onClick={fetchStrategies}
            className="text-xs underline ml-4"
            style={{ color: 'var(--danger)' }}
          >
            重试
          </button>
        </div>
      )}

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
              <th className="px-4 py-3 text-left font-medium" style={{ color: 'var(--text-secondary)' }}>最近修改</th>
              <th className="px-4 py-3 text-center font-medium" style={{ color: 'var(--text-secondary)' }}>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center" style={{ color: 'var(--text-muted)' }}>
                  加载中...
                </td>
              </tr>
            ) : strategies.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center" style={{ color: 'var(--text-muted)' }}>
                  暂无策略
                </td>
              </tr>
            ) : (
              strategies.map((s) => (
                <tr
                  key={s.strategy_id}
                  className="border-t hover:opacity-80"
                  style={{
                    borderColor: 'var(--border)',
                    transition: 'opacity 0.4s ease, transform 0.4s ease',
                    opacity: fadingOut.has(s.strategy_id) ? 0 : 1,
                    transform: fadingOut.has(s.strategy_id) ? 'translateX(-30px)' : 'translateX(0)',
                    pointerEvents: fadingOut.has(s.strategy_id) ? 'none' : 'auto',
                  }}
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
                      {s.latest_version && s.latest_version > s.version && (
                        <span style={{ color: 'var(--accent)' }}> → v{s.latest_version}</span>
                      )}
                    </span>
                  </td>
                  <td
                    className="px-4 py-3 text-xs max-w-md truncate relative"
                    style={{ color: 'var(--text-secondary)' }}
                    onMouseEnter={(e) => handleDescHover(s.description, e)}
                    onMouseMove={(e) => handleDescHover(s.description, e)}
                    onMouseLeave={handleDescLeave}
                  >
                    {s.description || '-'}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                    {s.updated_at ? new Date(s.updated_at).toLocaleString('zh-CN') : (s.created_at ? new Date(s.created_at).toLocaleString('zh-CN') : '-')}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => handleDelete(s.strategy_id, s.name)}
                      disabled={deleting === s.strategy_id || fadingOut.has(s.strategy_id)}
                      className="px-3 py-1 rounded text-xs font-medium transition-colors hover:opacity-80 disabled:opacity-40"
                      style={{
                        backgroundColor: 'rgba(239, 68, 68, 0.15)',
                        color: 'var(--danger)',
                      }}
                    >
                      {deleting === s.strategy_id ? '...' : '删除'}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Description tooltip */}
      {hoverDesc && hoverTarget && (
        <div
          ref={hoverRef}
          className="fixed z-50 max-w-md px-4 py-3 rounded-lg border text-xs leading-relaxed shadow-xl"
          style={{
            top: hoverTarget.y - 12,
            left: hoverTarget.x,
            transform: 'translate(-50%, -100%)',
            backgroundColor: 'var(--bg-secondary)',
            borderColor: 'var(--border)',
            color: 'var(--text-primary)',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            pointerEvents: 'none',
          }}
        >
          <p className="whitespace-pre-wrap break-words">{hoverDesc}</p>
          {/* Arrow */}
          <div
            className="absolute left-1/2 -translate-x-1/2 w-3 h-3 rotate-45"
            style={{
              bottom: '-6px',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border)',
              borderTopColor: 'transparent',
              borderLeftColor: 'transparent',
            }}
          />
        </div>
      )}
    </div>
  )
}
