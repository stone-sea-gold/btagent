import { useCopilotAction, useCopilotReadable } from '@copilotkit/react-core'
import { useNavigate } from 'react-router-dom'

export default function ChatPage() {
  const navigate = useNavigate()

  // Share current page context with the Agent
  useCopilotReadable({
    description: '当前用户所在的页面',
    value: '用户正在对话页面（ChatPage）',
  })

  // Let the Agent navigate to other pages
  useCopilotAction({
    name: 'navigate_to_page',
    description: '导航到指定页面。当用户想查看因子库、策略、回测结果等时使用。',
    parameters: [
      {
        name: 'page',
        type: 'string',
        description: '目标页面: factors, strategies, backtest, portfolio, settings',
        enum: ['factors', 'strategies', 'backtest', 'portfolio', 'settings'],
      },
    ],
    handler: ({ page }) => {
      navigate(`/${page}`)
    },
  })

  // Let the Agent open external links or show notifications
  useCopilotAction({
    name: 'show_notification',
    description: '向用户显示一条通知消息',
    parameters: [
      {
        name: 'message',
        type: 'string',
        description: '通知内容',
      },
    ],
    handler: ({ message }) => {
      alert(message)
    },
  })

  const quickActions = [
    { label: '搜索动量因子', query: '帮我搜索动量相关的因子' },
    { label: '运行回测', query: '帮我用3个月动量因子构建策略并回测，2020-2024年，选前10只股票' },
    { label: '查看策略列表', query: '帮我看看已保存的策略' },
    { label: '选股', query: '用动量和价值因子帮我选前50只股票' },
  ]

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-6" style={{ color: 'var(--text-primary)' }}>
        对话
      </h1>

      <div className="flex-1 flex flex-col items-center justify-center gap-8">
        {/* Welcome area */}
        <div className="text-center max-w-lg">
          <div className="text-4xl mb-4">A5</div>
          <p className="text-lg mb-2" style={{ color: 'var(--text-primary)' }}>
            AIFUND5 量化投资助手
          </p>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            使用右侧 Chat 面板与 Agent 对话，或点击下方快捷操作开始
          </p>
        </div>

        {/* Quick action buttons */}
        <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
          {quickActions.map((action) => (
            <button
              key={action.label}
              onClick={() => {
                navigator.clipboard.writeText(action.query).catch(() => {})
              }}
              className="p-4 rounded-lg border text-left transition-colors hover:opacity-80"
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderColor: 'var(--border)',
              }}
            >
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {action.label}
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                {action.query}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
