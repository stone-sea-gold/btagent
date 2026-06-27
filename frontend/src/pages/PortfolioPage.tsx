export default function PortfolioPage() {
  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        仓位管理
      </h1>

      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <div className="text-center">
          <p className="text-lg mb-2">暂无持仓数据</p>
          <p className="text-sm">通过对话记录持仓后，将显示在这里</p>
        </div>
      </div>
    </div>
  )
}
