import { useCopilotReadable } from '@copilotkit/react-core'

export default function BacktestPage() {
  // Share current page context with Agent
  useCopilotReadable({
    description: '当前页面：回测结果页面。用户可以在这里查看回测的收益曲线、指标和分析。',
    value: { page: 'backtest' },
  })

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        回测结果
      </h1>

      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <div className="text-center">
          <p className="text-lg mb-2">暂无回测结果</p>
          <p className="text-sm">通过对话运行回测后，结果将显示在这里</p>
        </div>
      </div>
    </div>
  )
}
