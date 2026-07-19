import { useState, useEffect } from 'react'
import ReactECharts from 'echarts-for-react'

interface BacktestMetrics {
  sharpe_ratio: number
  annualized_return: number
  max_drawdown: number
  volatility: number
  total_return: number
  win_rate: number
  turnover: number
}

interface BacktestSummary {
  backtest_id: string
  strategy_id: string
  metrics: BacktestMetrics
  created_at: string
}

interface BacktestDetail {
  backtest_id: string
  strategy_id: string
  metrics: BacktestMetrics
  equity_curve: { date: string; value: number }[]
  status: string
}

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestSummary[]>([])
  const [selected, setSelected] = useState<BacktestDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    fetch('/api/backtest/')
      .then((r) => r.json())
      .then((data) => setResults(data.results || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const loadDetail = async (id: string) => {
    setDetailLoading(true)
    try {
      const res = await fetch(`/api/backtest/${id}`)
      const data = await res.json()
      if (data.status === 'success') setSelected(data)
    } catch {}
    setDetailLoading(false)
  }

  const fmt = (v: number) => (v * 100).toFixed(1) + '%'
  const color = (v: number) => (v >= 0 ? 'var(--success)' : 'var(--danger)')

  const chartOption = selected?.equity_curve?.length
    ? {
        tooltip: { trigger: 'axis' as const },
        xAxis: { type: 'category' as const, data: selected.equity_curve.map((p) => p.date), axisLabel: { color: '#888' } },
        yAxis: { type: 'value' as const, axisLabel: { color: '#888' }, splitLine: { lineStyle: { color: '#333' } } },
        series: [{ data: selected.equity_curve.map((p) => p.value), type: 'line', showSymbol: false, lineStyle: { width: 2, color: '#818cf8' } }],
        grid: { left: 50, right: 20, top: 20, bottom: 40 },
      }
    : null

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        回测结果
      </h1>

      <div className="flex-1 overflow-auto flex gap-4" style={{ minHeight: 0 }}>
        {/* Left: list */}
        <div className="w-80 shrink-0 overflow-auto rounded-lg border p-3" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          {loading ? (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>加载中...</p>
          ) : results.length === 0 ? (
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>暂无回测记录</p>
          ) : (
            <div className="space-y-2">
              {results.map((r) => (
                <button
                  key={r.backtest_id}
                  onClick={() => loadDetail(r.backtest_id)}
                  className="w-full text-left p-3 rounded-lg border transition-colors hover:opacity-80"
                  style={{
                    backgroundColor: selected?.backtest_id === r.backtest_id ? 'var(--accent-light)' : 'var(--bg-tertiary)',
                    borderColor: selected?.backtest_id === r.backtest_id ? 'var(--accent)' : 'var(--border)',
                  }}
                >
                  <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                    {r.strategy_id}
                  </p>
                  <div className="flex gap-3 mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                    <span style={{ color: color(r.metrics.total_return) }}>
                      收益 {fmt(r.metrics.total_return)}
                    </span>
                    <span>夏普 {r.metrics.sharpe_ratio.toFixed(2)}</span>
                    <span style={{ color: 'var(--danger)' }}>
                      回撤 {fmt(r.metrics.max_drawdown)}
                    </span>
                  </div>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    {r.created_at.replace('T', ' ').slice(0, 16)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: detail */}
        <div className="flex-1 overflow-auto rounded-lg border p-4" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          {!selected ? (
            <div className="flex items-center justify-center h-full" style={{ color: 'var(--text-muted)' }}>
              <p>从左侧选择一条回测记录查看详情</p>
            </div>
          ) : detailLoading ? (
            <p style={{ color: 'var(--text-muted)' }}>加载中...</p>
          ) : (
            <div className="space-y-4">
              <h2 className="text-lg font-medium" style={{ color: 'var(--text-primary)' }}>
                {selected.strategy_id}
              </h2>

              {/* Metric cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  { label: '总收益率', value: fmt(selected.metrics.total_return), c: color(selected.metrics.total_return) },
                  { label: '年化收益', value: fmt(selected.metrics.annualized_return), c: color(selected.metrics.annualized_return) },
                  { label: '夏普比率', value: selected.metrics.sharpe_ratio.toFixed(2), c: 'var(--text-primary)' },
                  { label: '最大回撤', value: fmt(selected.metrics.max_drawdown), c: 'var(--danger)' },
                  { label: '波动率', value: fmt(selected.metrics.volatility), c: 'var(--text-primary)' },
                  { label: '胜率', value: fmt(selected.metrics.win_rate), c: 'var(--text-primary)' },
                  { label: '换手率', value: fmt(selected.metrics.turnover), c: 'var(--text-primary)' },
                  { label: '数据点', value: String(selected.equity_curve?.length || 0), c: 'var(--text-primary)' },
                ].map((card) => (
                  <div key={card.label} className="p-3 rounded-lg border" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)' }}>
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{card.label}</p>
                    <p className="text-xl font-semibold mt-1" style={{ color: card.c }}>{card.value}</p>
                  </div>
                ))}
              </div>

              {/* Equity curve chart */}
              {chartOption && (
                <div className="rounded-lg border p-3" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)' }}>
                  <h3 className="text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>净值曲线</h3>
                  <ReactECharts option={chartOption} style={{ height: 280 }} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
