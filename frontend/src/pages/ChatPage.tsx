import { useState, useRef, useEffect, useCallback, memo } from 'react'
import { useChat } from '@ai-sdk/react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { createChat, getChat, saveChat, listChatsSync, type ChatMessage } from '../utils/chatStore'

// Optimized Markdown component with memo
// `break-words` wraps long unbreakable tokens (URLs, JSON, digit runs) that
// would otherwise run past the bubble edge, and `overflow-x-auto` lets wide
// tables scroll inside the bubble instead of spilling out of it.
const MemoizedMarkdown = memo(({ content }: { content: string }) => (
  <div className="text-sm leading-relaxed prose prose-invert max-w-none break-words overflow-x-auto">
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  </div>
))

MemoizedMarkdown.displayName = 'MemoizedMarkdown'

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
      const fallback = listChatsSync()[0]?.id || createChat()
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
  const initialMessages = saved?.messages.map(m => ({
    ...m,
    createdAt: m.createdAt ? new Date(m.createdAt) : undefined,
  })) || []

  const { messages, input, handleInputChange, handleSubmit, isLoading, stop, setMessages, setInput } = useChat({
    api: '/api/chat',
    id: chatId,
    initialMessages,
    maxSteps: 5,
  })

  // Refresh: resend a user message, removing it and all subsequent messages
  const handleRefresh = useCallback((messageId: string) => {
    const idx = messages.findIndex(m => m.id === messageId)
    if (idx === -1) return
    const content = messages[idx].content
    if (!content) return

    // Remove this message and everything after it
    const newMessages = messages.slice(0, idx)
    setMessages(newMessages)

    // Set input and trigger submit
    setInput(content)
    // Use setTimeout to ensure state updates before submit
    setTimeout(() => {
      const form = document.querySelector('form')
      form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    }, 50)
  }, [messages, setMessages])

  // Persist messages when they change (debounced)
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (messages.length > 0 && chatId) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
      saveTimeoutRef.current = setTimeout(() => {
        const msgs: ChatMessage[] = messages.map((m) => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
        }))
        saveChat(chatId, msgs)
      }, 500) // Debounce: 500ms
    }
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
    }
  }, [messages, chatId])

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())
  const [userScrolledUp, setUserScrolledUp] = useState(false)
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced scroll to bottom
  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp) {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
      scrollTimeoutRef.current = setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'auto' })
      }, 100) // Debounce: 100ms
    }
  }, [userScrolledUp])

  useEffect(() => {
    scrollToBottom()
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current)
      }
    }
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
          BT Agent
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
                BT Agent 量化投资助手
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
              <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} group`}>
                <div className="relative max-w-[80%]">
                  {/* Refresh button for user messages */}
                  {msg.role === 'user' && !isLoading && (
                    <button
                      onClick={() => handleRefresh(msg.id)}
                      className="absolute -left-8 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1 rounded hover:bg-white/10"
                      title="重新提问"
                    >
                      <svg className="w-4 h-4" style={{ color: 'var(--text-muted)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                    </button>
                  )}
                <div
                  className={`rounded-2xl px-4 py-3 ${
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
                    <MemoizedMarkdown content={msg.content} />
                  )}
                </div>
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
        {isLoading ? (
          <button
            type="button"
            onClick={stop}
            className="px-6 py-3 rounded-xl text-sm font-medium transition-all duration-200 hover:scale-105 active:scale-95"
            style={{
              background: 'linear-gradient(135deg, #ef4444 0%, #f97316 100%)',
              color: '#ffffff',
              boxShadow: '0 4px 14px rgba(239, 68, 68, 0.4)',
            }}
          >
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
              停止
            </span>
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="px-6 py-3 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed hover:scale-105 active:scale-95"
            style={{
              background: 'var(--accent-gradient)',
              color: '#ffffff',
              boxShadow: input.trim() ? '0 4px 14px rgba(99, 102, 241, 0.4)' : 'none',
            }}
          >
            发送
          </button>
        )}
      </form>
    </div>
  )
}
