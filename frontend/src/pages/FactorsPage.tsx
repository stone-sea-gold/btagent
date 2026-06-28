import { useState, useEffect } from 'react'

interface Factor {
  id: string
  name: string
  description: string
  category: string
  tags: string[]
  source: string
}

export default function FactorsPage() {
  const [factors, setFactors] = useState<Factor[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchFactors()
  }, [])

  const fetchFactors = async (category = '') => {
    setLoading(true)
    setError(null)
    try {
      const url = category
        ? `/api/factors/?category=${category}&limit=100`
        : '/api/factors/?limit=100'
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`请求失败: ${res.status} ${res.statusText}`)
      }
      const data = await res.json()
      setFactors(data.factors || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : '未知错误'
      console.error('Failed to fetch factors:', err)
      setError(`加载因子失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      fetchFactors(categoryFilter)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `/api/factors/search?q=${encodeURIComponent(searchQuery)}&limit=20`
      )
      if (!res.ok) {
        throw new Error(`搜索失败: ${res.status}`)
      }
      const data = await res.json()
      setFactors(data.factors || [])
    } catch (err) {
      const message = err instanceof Error ? err.message : '未知错误'
      console.error('Search failed:', err)
      setError(`搜索失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }

  const categories = [
    '',
    'momentum',
    'value',
    'quality',
    'volatility',
    'size',
    'liquidity',
    'growth',
    'technical',
  ]
  const categoryLabels: Record<string, string> = {
    '': '全部',
    momentum: '动量',
    value: '价值',
    quality: '质量',
    volatility: '波动率',
    size: '规模',
    liquidity: '流动性',
    growth: '成长',
    technical: '技术',
  }

  const sourceColors: Record<string, string> = {
    custom: 'var(--accent)',
    alpha158: 'var(--success)',
    alpha360: 'var(--warning)',
  }

  return (
    <div className="h-full flex flex-col">
      <h1
        className="text-2xl font-semibold mb-4"
        style={{ color: 'var(--text-primary)' }}
      >
        因子库
      </h1>

      {/* Search and filters */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="搜索因子..."
            className="flex-1 px-3 py-2 rounded-lg border text-sm"
            style={{
              backgroundColor: 'var(--bg-tertiary)',
              borderColor: 'var(--border)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            onClick={handleSearch}
            className="px-4 py-2 rounded-lg text-sm font-medium"
            style={{ backgroundColor: 'var(--accent)', color: 'white' }}
          >
            搜索
          </button>
        </div>

        <select
          value={categoryFilter}
          onChange={(e) => {
            setCategoryFilter(e.target.value)
            fetchFactors(e.target.value)
          }}
          className="px-3 py-2 rounded-lg border text-sm"
          style={{
            backgroundColor: 'var(--bg-tertiary)',
            borderColor: 'var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {categoryLabels[cat]}
            </option>
          ))}
        </select>
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="mb-4 px-4 py-3 rounded-lg flex items-center justify-between"
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'var(--danger)',
            border: '1px solid',
          }}
        >
          <p className="text-sm" style={{ color: 'var(--danger)' }}>
            {error}
          </p>
          <button
            onClick={() => fetchFactors(categoryFilter)}
            className="text-xs underline ml-4"
            style={{ color: 'var(--danger)' }}
          >
            重试
          </button>
        </div>
      )}

      {/* Factor count */}
      <p className="text-sm mb-3" style={{ color: 'var(--text-muted)' }}>
        共 {factors.length} 个因子
      </p>

      {/* Factor table */}
      <div
        className="flex-1 overflow-auto rounded-lg border"
        style={{ borderColor: 'var(--border)' }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ backgroundColor: 'var(--bg-secondary)' }}>
              <th
                className="px-4 py-3 text-left font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                ID
              </th>
              <th
                className="px-4 py-3 text-left font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                名称
              </th>
              <th
                className="px-4 py-3 text-left font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                类别
              </th>
              <th
                className="px-4 py-3 text-left font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                来源
              </th>
              <th
                className="px-4 py-3 text-left font-medium"
                style={{ color: 'var(--text-secondary)' }}
              >
                描述
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center"
                  style={{ color: 'var(--text-muted)' }}
                >
                  加载中...
                </td>
              </tr>
            ) : factors.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center"
                  style={{ color: 'var(--text-muted)' }}
                >
                  未找到因子
                </td>
              </tr>
            ) : (
              factors.map((factor) => (
                <tr
                  key={factor.id}
                  className="border-t hover:opacity-80"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <td
                    className="px-4 py-3 font-mono text-xs"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {factor.id}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {factor.name}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="px-2 py-1 rounded text-xs"
                      style={{
                        backgroundColor: 'var(--bg-tertiary)',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      {categoryLabels[factor.category] || factor.category}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="px-2 py-1 rounded text-xs font-medium"
                      style={{
                        backgroundColor: 'var(--bg-tertiary)',
                        color:
                          sourceColors[factor.source] || 'var(--text-secondary)',
                      }}
                    >
                      {factor.source}
                    </span>
                  </td>
                  <td
                    className="px-4 py-3 text-xs max-w-md truncate"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {factor.description}
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
