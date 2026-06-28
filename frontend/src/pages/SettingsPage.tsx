import { useState, useEffect } from 'react'
import { useCopilotReadable } from '@copilotkit/react-core'

export default function SettingsPage() {
  const [coverage, setCoverage] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  // Share settings context with the Agent
  useCopilotReadable({
    description: '当前设置页面的数据状态',
    value: coverage || { status: '未加载' },
  })

  useEffect(() => {
    fetch('/api/data/coverage')
      .then((res) => {
        if (!res.ok) throw new Error(`请求失败: ${res.status}`)
        return res.json()
      })
      .then(setCoverage)
      .catch((err) => {
        console.error('Failed to fetch coverage:', err)
        setError('加载数据状态失败')
      })
  }, [])

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-6" style={{ color: 'var(--text-primary)' }}>
        设置
      </h1>

      <div className="space-y-6 max-w-2xl">
        {/* Data coverage */}
        <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <h2 className="text-lg font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            数据状态
          </h2>
          {error ? (
            <p className="text-sm" style={{ color: 'var(--danger)' }}>{error}</p>
          ) : coverage ? (
            <div className="space-y-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <p>数据起始日期: {coverage.data_start_date || '未知'}</p>
              <p>数据截止日期: {coverage.data_end_date || '未知'}</p>
              <p>
                状态:
                <span
                  className="ml-2 px-2 py-1 rounded text-xs"
                  style={{
                    backgroundColor: coverage.is_stale ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)',
                    color: coverage.is_stale ? 'var(--danger)' : 'var(--success)',
                  }}
                >
                  {coverage.is_stale ? `滞后 ${coverage.days_behind} 天` : '正常'}
                </span>
              </p>
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>加载中...</p>
          )}
        </div>

        {/* LLM config info */}
        <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <h2 className="text-lg font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            LLM 配置
          </h2>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            LLM 配置通过后端 .env 文件管理，详见项目文档。
          </p>
        </div>
      </div>
    </div>
  )
}
