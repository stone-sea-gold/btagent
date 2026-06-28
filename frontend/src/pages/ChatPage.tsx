import { useState, useRef, useEffect, useCallback } from 'react'
import { useChat } from '@ai-sdk/react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { createChat, getChat, saveChat, listChats, type ChatMessage } from '../utils/chatStore'

const toolLabels: Record<string, string> = {
  _search_factors: '搜索因子',
  _create_factor: '创建因子',
  _compose_strategy: '构建策略',
  _run_backtest: '运行回测',
  _analyze_backtest: '分析回测',
  _save_strategy: '保存策略',
  _load_strategy: '加载策略',
  _list_strategies: '查看策略列表',
  _search_strategies: '搜索策略',
  _compare_strategies: '对比策略',
  _update_strategy: '更新策略',
  _get_version_chain: '查看版本链',
  _select_stocks: '选股',
  _save_holdings: '保存持仓',
  _get_portfolio_status: '查询持仓状态',
  _save_position_rules: '保存仓位规则',
  _optimize_parameters: '参数优化',
  _add_stoploss_rules: '添加止损规则',
  _run_backtest_with_stoploss: '带止损回测',
  _check_stoploss_scenarios: '分析止损场景',
  _get_current_date: '获取当前日期',
  _resolve_relative_date: '解析日期',
  _get_trading_days: '获取交易日',
  _check_data_coverage: '检查数据覆盖',
}

const quickActions = [
  { label: '搜索动量因子', query: '帮我搜索动量相关的因子' },
  { label: '运行回测', query: '帮我用3个月动量因子构建策略并回测，2020-2024年，选前10只股票' },
  { label: '查看策略列表', query: '帮我看看已保存的策略' },
  { label: '选股', query: '用动量和价值因子帮我选前50只股票' },
]

/** Outer wrapper — reads URL, forces re-mount on chatId change via key. */
export default function ChatPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // On first mount without an id in the URL, redirect to latest or new.
  useEffect(() => {
    const id = searchParams.get('id')
    if (!id) {
      const fallback = listChats()[0]?.id || createChat()
      navigate(`/chat?id=${fallback}`, { replace: true })
    }
  }, [])

  const chatId = searchParams.get('id')
  if (!chatId) return null

  return <ChatSession key={chatId} chatId={chatId} />
}

/** Inner session — re-mounts whenever chatId changes, so useChat starts clean. */
function ChatSession({ chatId }: { chatId: string }) {
  const navigate = useNavigate()

  const startNewChat = () => {
    navigate(`/chat?id=${createChat()}`, { replace: true })
  }

  // Load persisted messages
  const saved = getChat(chatId)
  const initialMessages: ChatMessage[] = saved?.messages || []

  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: '/api/chat',
    id: chatId,
    initialMessages,
    maxSteps: 10,
  })

  // Persist messages when they change
  useEffect(() => {
    if (messages.length > 0 && chatId) {
      const msgs: ChatMessage[] = messages.map((m) => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      saveChat(chatId, msgs)
    }
  }, [messages, chatId])

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())
  const [userScrolledUp, setUserScrolledUp] = useState(false)

  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' })
    }
  }, [userScrolledUp])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
    setUserScrolledUp(!isNearBottom)
  }, [])

  const toggleTool = (toolCallId: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev)
      if (next.has(toolCallId)) next.delete(toolCallId)
      else next.add(toolCallId)
      return next
    })
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          AIFUND5 助手
        </h1>
        <button
          onClick={startNewChat}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95 disabled:opacity-40"
          style={{
            background: 'var(--accent-gradient)',
            color: '#ffffff',
          }}
          title="开始新对话"
        >
          ✦ 新对话
        </button>
        {isLoading && (
          <span className="text-sm animate-pulse" style={{ color: 'var(--accent)' }}>
            思考中...
          </span>
        )}
      </div>

      {/* Messages area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto rounded-lg border p-4 mb-4"
        style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-6">
            <div className="text-center">
              <div className="text-4xl mb-3 font-bold" style={{ color: 'var(--accent)' }}>
                A5
              </div>
              <p className="text-lg mb-1" style={{ color: 'var(--text-primary)' }}>
                AIFUND5 量化投资助手
              </p>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                输入自然语言指令，Agent 会自动调用工具完成任务
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 w-full max-w-md">
              {quickActions.map((action) => (
                <button
                  key={action.label}
                  onClick={() => {
                    handleInputChange({ target: { value: action.query } } as React.ChangeEvent<HTMLTextAreaElement>)
                    // Trigger submit after setting input
                    setTimeout(() => {
                      const form = document.querySelector('form')
                      form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
                    }, 0)
                  }}
                  className="p-3 rounded-lg border text-left transition-colors hover:opacity-80"
                  style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)' }}
                >
                  <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {action.label}
                  </p>
                  <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
                    {action.query}
                  </p>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                    msg.role === 'user' ? 'rounded-br-md' : 'rounded-bl-md'
                  }`}
                  style={{
                    background: msg.role === 'user' ? 'var(--accent-gradient)' : 'var(--bg-tertiary)',
                    color: msg.role === 'user' ? '#ffffff' : 'var(--text-primary)',
                    boxShadow: msg.role === 'user' ? '0 4px 14px rgba(99, 102, 241, 0.3)' : 'none',
                  }}
                >
                  {/* Tool invocations */}
                  {msg.toolInvocations?.map((inv) => (
                    <div
                      key={inv.toolCallId}
                      className="mb-2 rounded-lg border overflow-hidden"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      <button
                        onClick={() => toggleTool(inv.toolCallId)}
                        className="w-full px-3 py-2 flex items-center justify-between text-xs"
                        style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
                      >
                        <span className="flex items-center gap-2">
                          {inv.state === 'call' && (
                            <span
                              className="inline-block w-3 h-3 rounded-full animate-pulse"
                              style={{ backgroundColor: 'var(--accent)' }}
                            />
                          )}
                          {inv.state === 'result' && (
                            <span
                              className="inline-block w-3 h-3 rounded-full"
                              style={{ backgroundColor: 'var(--success)' }}
                            />
                          )}
                          {inv.state === 'error' && (
                            <span
                              className="inline-block w-3 h-3 rounded-full"
                              style={{ backgroundColor: 'var(--danger)' }}
                            />
                          )}
                          <span className="font-medium">
                            {toolLabels[inv.toolName] || inv.toolName}
                          </span>
                        </span>
                        <span>{expandedTools.has(inv.toolCallId) ? '▲' : '▼'}</span>
                      </button>

                      {expandedTools.has(inv.toolCallId) && (
                        <div className="px-3 py-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                          {inv.args && (
                            <div className="mb-2">
                              <p className="font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
                                参数:
                              </p>
                              <pre className="whitespace-pre-wrap break-all text-xs">
                                {JSON.stringify(inv.args, null, 2)}
                              </pre>
                            </div>
                          )}
                          {inv.state === 'result' && inv.result && (
                            <div>
                              <p className="font-medium mb-1" style={{ color: 'var(--text-muted)' }}>
                                结果:
                              </p>
                              <pre className="whitespace-pre-wrap break-all text-xs max-h-60 overflow-auto">
                                {typeof inv.result === 'string'
                                  ? inv.result
                                  : JSON.stringify(inv.result, null, 2)}
                              </pre>
                            </div>
                          )}
                          {inv.state === 'call' && (
                            <p className="animate-pulse" style={{ color: 'var(--accent)' }}>
                              执行中...
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Text content with Markdown rendering */}
                  {msg.content && (
                    <div className="text-sm leading-relaxed prose prose-invert max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1 relative group">
          <textarea
            value={input}
            onChange={handleInputChange}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            placeholder="输入指令... (Shift+Enter 换行)"
            rows={1}
            className="w-full px-4 py-3 rounded-xl border text-sm resize-none transition-all duration-200 outline-none"
            style={{
              backgroundColor: 'var(--bg-tertiary)',
              borderColor: 'var(--border)',
              color: 'var(--text-primary)',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = 'var(--accent)'
              e.target.style.boxShadow = '0 0 0 3px var(--accent-light)'
            }}
            onBlur={(e) => {
              e.target.style.borderColor = 'var(--border)'
              e.target.style.boxShadow = 'none'
            }}
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="px-6 py-3 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
          style={{
            background: isLoading ? 'var(--bg-tertiary)' : 'var(--accent-gradient)',
            color: '#ffffff',
            boxShadow: !isLoading && input.trim() ? '0 4px 14px rgba(99, 102, 241, 0.4)' : 'none',
          }}
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="inline-block w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="inline-block w-2 h-2 rounded-full bg-current animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          ) : (
            '发送'
          )}
        </button>
      </form>
    </div>
  )
}
