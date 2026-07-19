import { useState, useCallback } from 'react'

const API_BASE = '/api'

const tabs = [
  { id: 'quote', label: '实时行情', icon: '📊' },
  { id: 'history', label: '历史K线', icon: '📈' },
  { id: 'financial', label: '基本面', icon: '📋' },
  { id: 'sector', label: '板块列表', icon: '🏭' },
  { id: 'industry', label: '行业股票', icon: '🏢' },
  { id: 'index', label: '指数成分', icon: '📈' },
]

type ResultState = {
  loading: boolean
  data: any
  error: string
}

const initialResult: ResultState = { loading: false, data: null, error: '' }

export default function MarketDataPage() {
  const [activeTab, setActiveTab] = useState('quote')
  const [result, setResult] = useState<ResultState>(initialResult)

  // Form states
  const [symbol, setSymbol] = useState('600519')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [period, setPeriod] = useState('daily')
  const [adjust, setAdjust] = useState('qfq')
  const [industry, setIndustry] = useState('银行')
  const [indexCode, setIndexCode] = useState('csi300')

  const fetchData = useCallback(async (url: string) => {
    setResult({ loading: true, data: null, error: '' })
    try {
      const resp = await fetch(url)
      const data = await resp.json()
      if (data.error) {
        setResult({ loading: false, data: null, error: data.error })
      } else {
        setResult({ loading: false, data, error: '' })
      }
    } catch (e: any) {
      setResult({ loading: false, data: null, error: e.message || '请求失败' })
    }
  }, [])

  const handleQuery = () => {
    switch (activeTab) {
      case 'quote':
        fetchData(`${API_BASE}/market-data/quote?symbol=${symbol}`)
        break
      case 'history':
        fetchData(`${API_BASE}/market-data/history?symbol=${symbol}&start=${startDate}&end=${endDate}&period=${period}&adjust=${adjust}`)
        break
      case 'financial':
        fetchData(`${API_BASE}/market-data/financial?symbol=${symbol}`)
        break
      case 'sector':
        fetchData(`${API_BASE}/market-data/sector-flow`)
        break
      case 'industry':
        fetchData(`${API_BASE}/market-data/industry?industry=${industry}`)
        break
      case 'index':
        fetchData(`${API_BASE}/market-data/index-constituents?index=${indexCode}`)
        break
    }
  }

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        市场数据
      </h1>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 flex-wrap">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => { setActiveTab(tab.id); setResult(initialResult) }}
            className="px-3 py-1.5 rounded-lg text-sm transition-colors"
            style={{
              backgroundColor: activeTab === tab.id ? 'var(--accent)' : 'var(--bg-tertiary)',
              color: activeTab === tab.id ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* Query Form */}
      <div
        className="rounded-lg p-4 mb-4"
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        <div className="flex flex-wrap gap-3 items-end">
          {(activeTab === 'quote' || activeTab === 'history' || activeTab === 'financial') && (
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>股票代码</label>
              <input
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                placeholder="600519"
                className="px-3 py-1.5 rounded text-sm"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
            </div>
          )}

          {activeTab === 'history' && (
            <>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>起始日期</label>
                <input
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  placeholder="20240101"
                  className="px-3 py-1.5 rounded text-sm"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>截止日期</label>
                <input
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  placeholder="20241231"
                  className="px-3 py-1.5 rounded text-sm"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>周期</label>
                <select
                  value={period}
                  onChange={(e) => setPeriod(e.target.value)}
                  className="px-3 py-1.5 rounded text-sm"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                >
                  <option value="daily">日线</option>
                  <option value="weekly">周线</option>
                  <option value="monthly">月线</option>
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>复权</label>
                <select
                  value={adjust}
                  onChange={(e) => setAdjust(e.target.value)}
                  className="px-3 py-1.5 rounded text-sm"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                >
                  <option value="qfq">前复权</option>
                  <option value="hfq">后复权</option>
                  <option value="">不复权</option>
                </select>
              </div>
            </>
          )}

          {activeTab === 'industry' && (
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>行业名称</label>
              <input
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="银行"
                className="px-3 py-1.5 rounded text-sm"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
            </div>
          )}

          {activeTab === 'industry' && (
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>行业名称</label>
              <input
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="银行"
                className="px-3 py-1.5 rounded text-sm"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
            </div>
          )}

          {activeTab === 'index' && (
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>指数代码</label>
              <select
                value={indexCode}
                onChange={(e) => setIndexCode(e.target.value)}
                className="px-3 py-1.5 rounded text-sm"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              >
                <option value="csi300">沪深300</option>
                <option value="csi500">中证500</option>
              </select>
            </div>
          )}

          <button
            onClick={handleQuery}
            disabled={result.loading}
            className="px-4 py-1.5 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: result.loading ? 'var(--bg-tertiary)' : 'var(--accent)',
              color: '#fff',
              opacity: result.loading ? 0.6 : 1,
            }}
          >
            {result.loading ? '查询中...' : '查询'}
          </button>
        </div>
      </div>

      {/* Result Area */}
      <div
        className="flex-1 rounded-lg p-4 overflow-auto"
        style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border)' }}
      >
        {result.error && (
          <div className="p-3 rounded-lg mb-3" style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: 'var(--danger)' }}>
            {result.error}
          </div>
        )}

        {result.data && <ResultDisplay data={result.data} tab={activeTab} />}

        {!result.data && !result.error && !result.loading && (
          <div className="flex items-center justify-center h-full" style={{ color: 'var(--text-muted)' }}>
            <div className="text-center">
              <p className="text-lg mb-2">输入条件后点击查询</p>
              <p className="text-sm">数据来自 pytdx / baostock</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ResultDisplay({ data, tab }: { data: any; tab: string }) {
  // Quote card display
  if (tab === 'quote' && data.symbol) {
    const changeColor = (data.change_pct || 0) >= 0 ? 'var(--danger)' : 'var(--success)'
    return (
      <div>
        <div className="flex items-baseline gap-3 mb-4">
          <span className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{data.name}</span>
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{data.symbol}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="最新价" value={data.price?.toFixed(2)} color={changeColor} />
          <MetricCard label="涨跌幅" value={`${data.change_pct?.toFixed(2)}%`} color={changeColor} />
          <MetricCard label="成交量" value={formatVolume(data.volume)} />
          <MetricCard label="换手率" value={`${data.turnover_rate?.toFixed(2)}%`} />
          <MetricCard label="市盈率" value={data.pe_ratio?.toFixed(2)} />
          <MetricCard label="市净率" value={data.pb_ratio?.toFixed(2)} />
          <MetricCard label="总市值" value={formatMarketCap(data.total_market_cap)} />
          <MetricCard label="成交额" value={formatMarketCap(data.turnover)} />
        </div>
      </div>
    )
  }

  // Financial card display
  if (tab === 'financial' && data.symbol) {
    return (
      <div>
        <div className="flex items-baseline gap-3 mb-4">
          <span className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{data.name}</span>
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>{data.symbol}</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="最新价" value={data.price?.toFixed(2)} />
          <MetricCard label="市盈率(动)" value={data.pe_ratio?.toFixed(2)} />
          <MetricCard label="市净率" value={data.pb_ratio?.toFixed(2)} />
          <MetricCard label="总市值" value={formatMarketCap(data.total_market_cap)} />
          <MetricCard label="流通市值" value={formatMarketCap(data.circulating_market_cap)} />
          <MetricCard label="换手率" value={`${data.turnover_rate?.toFixed(2)}%`} />
          <MetricCard label="振幅" value={`${data.amplitude?.toFixed(2)}%`} />
        </div>
      </div>
    )
  }

  // Sector / Industry / Index table display
  if (data.data && Array.isArray(data.data)) {
    const columns = data.data.length > 0 ? Object.keys(data.data[0]) : []
    return (
      <div>
        <div className="mb-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
          共 {data.count || data.data.length} 条数据
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {columns.map((col) => (
                  <th key={col} className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.map((row: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  {columns.map((col) => (
                    <td key={col} className="py-2 px-3" style={{ color: 'var(--text-primary)' }}>
                      {typeof row[col] === 'number' ? row[col].toLocaleString() : row[col]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  // History data
  if (data.data && Array.isArray(data.data) && data.data.length > 0 && data.data[0].date) {
    return (
      <div>
        <div className="mb-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
          {data.symbol} | {data.period} | 共 {data.count} 条
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th className="text-left py-2 px-3" style={{ color: 'var(--text-muted)' }}>日期</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>开盘</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>最高</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>最低</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>收盘</th>
                <th className="text-right py-2 px-3" style={{ color: 'var(--text-muted)' }}>涨跌幅</th>
              </tr>
            </thead>
            <tbody>
              {data.data.map((row: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="py-2 px-3" style={{ color: 'var(--text-secondary)' }}>{row.date}</td>
                  <td className="py-2 px-3 text-right" style={{ color: 'var(--text-primary)' }}>{row.open?.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right" style={{ color: 'var(--text-primary)' }}>{row.high?.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right" style={{ color: 'var(--text-primary)' }}>{row.low?.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right" style={{ color: 'var(--text-primary)' }}>{row.close?.toFixed(2)}</td>
                  <td className="py-2 px-3 text-right" style={{ color: (row.change_pct || 0) >= 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {row.change_pct?.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  // Fallback: JSON display
  return (
    <pre className="text-xs overflow-auto" style={{ color: 'var(--text-primary)' }}>
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function MetricCard({ label, value, color }: { label: string; value: any; color?: string }) {
  return (
    <div className="rounded-lg p-3" style={{ backgroundColor: 'var(--bg-tertiary)' }}>
      <div className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="text-lg font-semibold" style={{ color: color || 'var(--text-primary)' }}>
        {value ?? '-'}
      </div>
    </div>
  )
}

function formatVolume(v: number): string {
  if (!v) return '-'
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`
  return v.toLocaleString()
}

function formatMarketCap(v: number): string {
  if (!v) return '-'
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}万亿`
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
  if (v >= 1e4) return `${(v / 1e4).toFixed(2)}万`
  return v.toLocaleString()
}
