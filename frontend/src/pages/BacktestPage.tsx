import { useState } from 'react'

interface BacktestMetrics {
  sharpe_ratio: number
  annualized_return: number
  max_drawdown: number
  volatility: number
  total_return: number
  win_rate: number
  turnover: number
}

interface BacktestResult {
  backtest_id: string
  strategy_name: string
  metrics: BacktestMetrics
  equity_curve_summary: { data_points: number; start_value: number; end_value: number }
  is_cached?: boolean
  status: string
}

export default function BacktestPage() {
  const [backtestData, setBacktestData] = useState<BacktestResult | null>(null)

  const m = backtestData?.metrics

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        回测结果
      </h1>

      {backtestData ? (
        <div className="flex-1 overflow-auto">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {m?.sharpe_ratio !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>夏普比率</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {Number(m.sharpe_ratio).toFixed(2)}
                </p>
              </div>
            )}
            {m?.annualized_return !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>年化收益</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--success)' }}>
                  {(Number(m.annualized_return) * 100).toFixed(1)}%
                </p>
              </div>
            )}
            {m?.max_drawdown !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>最大回撤</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--danger)' }}>
                  {(Number(m.max_drawdown) * 100).toFixed(1)}%
                </p>
              </div>
            )}
            {m?.volatility !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>波动率</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {(Number(m.volatility) * 100).toFixed(1)}%
                </p>
              </div>
            )}
          </div>

          {/* Metric cards row 2 */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {m?.total_return !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>总收益率</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--success)' }}>
                  {(Number(m.total_return) * 100).toFixed(1)}%
                </p>
              </div>
            )}
            {m?.win_rate !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>胜率</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {(Number(m.win_rate) * 100).toFixed(1)}%
                </p>
              </div>
            )}
            {m?.turnover !== undefined && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>换手率</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {(Number(m.turnover) * 100).toFixed(1)}%
                </p>
              </div>
            )}
            {backtestData.equity_curve_summary && (
              <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>数据点数</p>
                <p className="text-2xl font-semibold mt-1" style={{ color: 'var(--text-primary)' }}>
                  {backtestData.equity_curve_summary.data_points}
                </p>
              </div>
            )}
          </div>

          {/* Raw result table */}
          <div className="p-4 rounded-lg border" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
            <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>详细指标</h2>
            <div className="space-y-1 text-xs" style={{ color: 'var(--text-secondary)' }}>
              {Object.entries(m ?? {}).map(([key, value]) => (
                <div key={key} className="flex justify-between py-1 border-b" style={{ borderColor: 'var(--border)' }}>
                  <span>{key}</span>
                  <span className="font-mono">{typeof value === 'number' ? value.toFixed(4) : String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
          <div className="text-center">
            <p className="text-lg mb-2">暂无回测结果</p>
            <p className="text-sm">通过右侧 Chat 面板运行回测后，结果将显示在这里</p>
          </div>
        </div>
      )}
    </div>
  )
}
