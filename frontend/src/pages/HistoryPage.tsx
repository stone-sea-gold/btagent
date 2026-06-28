import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { listChats, deleteChat, type ChatRecord } from '../utils/chatStore'

export default function HistoryPage() {
  const [chats, setChats] = useState<ChatRecord[]>([])
  const navigate = useNavigate()

  const refresh = () => setChats(listChats())

  useEffect(refresh, [])

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    deleteChat(id)
    refresh()
  }

  const handleSelect = (id: string) => {
    navigate(`/chat?id=${id}`)
  }

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        历史对话
      </h1>

      {chats.length === 0 ? (
        <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
          <div className="text-center">
            <p className="text-lg mb-2">暂无历史记录</p>
            <p className="text-sm">开始新对话后，记录将自动保存</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-auto space-y-2">
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => handleSelect(chat.id)}
              className="w-full p-4 rounded-xl border text-left transition-all duration-200 hover:scale-[1.01] active:scale-[0.99]"
              style={{
                backgroundColor: 'var(--bg-secondary)',
                borderColor: 'var(--border)',
              }}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0 mr-4">
                  <p
                    className="text-sm font-medium truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {chat.title}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                    共 {chat.messages.length} 条消息 · {new Date(chat.updatedAt).toLocaleString('zh-CN')}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, chat.id)}
                  className="flex-shrink-0 px-2 py-1 rounded-lg text-xs transition-colors hover:opacity-80"
                  style={{ color: 'var(--danger)' }}
                  title="删除"
                >
                  删除
                </button>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
