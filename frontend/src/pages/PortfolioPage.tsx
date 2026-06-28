export default function PortfolioPage() {

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        仓位管理
      </h1>

      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <div className="text-center">
          <p className="text-lg mb-2">暂无持仓数据</p>
          <p className="text-sm">通过右侧 Chat 面板与 Agent 对话来管理持仓</p>
          <p className="text-xs mt-2">例如：&ldquo;帮我保存持仓：贵州茅台 30%，宁德时代 20%&rdquo;</p>
        </div>
      </div>
    </div>
  )
}
