export default function ChatPage() {
  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        对话
      </h1>
      <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>
        <div className="text-center">
          <p className="text-lg mb-2">使用右侧 Chat 面板与 Agent 对话</p>
          <p className="text-sm">点击右上角的聊天图标打开面板</p>
        </div>
      </div>
    </div>
  )
}
