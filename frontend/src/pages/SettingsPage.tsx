import { useState, useEffect } from 'react'

interface Preset {
  id: number
  label: string
  base_url: string
  model: string
  is_active: boolean
}

const PRESET_PROVIDERS: { label: string; baseUrl: string; model?: string }[] = [
  { label: 'DeepSeek',        baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  { label: 'Kimi（月之暗面）', baseUrl: 'https://api.moonshot.cn/v1' },
  { label: '千问（通义）',     baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'GLM（智谱）',      baseUrl: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'MiniMax（稀宇）',  baseUrl: 'https://api.minimax.chat/v1' },
  { label: 'MIMO（小米）',     baseUrl: 'https://token-plan-cn.xiaomimimo.com/v1' },
  { label: 'Anthropic',       baseUrl: 'https://api.anthropic.com' },
  { label: 'OpenAI',          baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o' },
]

export default function SettingsPage() {
  const [presets, setPresets] = useState<Preset[]>([])
  const [defaultPreset, setDefaultPreset] = useState<{ label: string; base_url: string; model: string } | null>(null)
  const [activeId, setActiveId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  // Add form
  const [label, setLabel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const showMsg = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text })
    setTimeout(() => setMessage(null), 3000)
  }

  const fetchPresets = async () => {
    try {
      const res = await fetch('/api/settings/presets')
      const data = await res.json()
      setPresets(data.presets || [])
      setDefaultPreset(data.default || null)
      setActiveId(data.active_preset_id ?? null)
    } catch {
      showMsg('error', '加载预设失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchPresets() }, [])

  const handleAdd = async () => {
    if (!label.trim() || !baseUrl.trim() || !apiKey.trim() || !model.trim()) {
      showMsg('error', '所有字段均为必填项')
      return
    }
    setSaving(true)
    try {
      const res = await fetch('/api/settings/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: label.trim(), base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim() }),
      })
      if (!res.ok) {
        const errBody = await res.text().catch(() => '')
        throw new Error(`${res.status} ${errBody}`)
      }
      setLabel(''); setBaseUrl(''); setApiKey(''); setModel('')
      await fetchPresets()
      showMsg('success', '预设已添加')
    } catch (e) {
      console.error('Add preset failed:', e)
      showMsg('error', '添加失败')
    } finally {
      setSaving(false)
    }
  }

  const handleActivate = async (id: number) => {
    try {
      await fetch(`/api/settings/presets/${id}/activate`, { method: 'POST' })
      await fetchPresets()
      showMsg('success', '已切换，下一条消息使用新配置')
    } catch {
      showMsg('error', '切换失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await fetch(`/api/settings/presets/${id}`, { method: 'DELETE' })
      await fetchPresets()
    } catch {
      showMsg('error', '删除失败')
    }
  }

  const handleReset = async () => {
    try {
      await fetch('/api/settings/reset', { method: 'POST' })
      await fetchPresets()
      showMsg('success', '已恢复 .env 默认配置')
    } catch {
      showMsg('error', '重置失败')
    }
  }

  const protocolHint = (url: string) => url.includes('/anthropic') ? 'Anthropic' : 'OpenAI'

  return (
    <div className="h-full flex flex-col">
      <h1 className="text-2xl font-semibold mb-6" style={{ color: 'var(--text-primary)' }}>
        设置
      </h1>

      {/* Toast */}
      {message && (
        <div
          className="mb-4 px-4 py-2 rounded-lg text-sm max-w-2xl"
          style={{
            backgroundColor: message.type === 'success' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
            color: message.type === 'success' ? 'var(--success)' : 'var(--danger)',
          }}
        >
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left: Add form */}
        <div className="p-5 rounded-xl border h-fit" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            添加预设
          </h2>
          <div className="space-y-3">
            <select value={label} onChange={(e) => {
                const selected = e.target.value
                setLabel(selected)
                const preset = PRESET_PROVIDERS.find((p) => p.label === selected)
                if (preset) {
                  setBaseUrl(preset.baseUrl)
                  setModel(preset.model || '')
                }
              }}
              className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200 appearance-none cursor-pointer"
              style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
            >
              <option value="">-- 选择厂商 --</option>
              {PRESET_PROVIDERS.map((p) => (
                <option key={p.label} value={p.label}>{p.label}</option>
              ))}
            </select>
            <input type="text" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="Base URL"
              className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
              style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              onFocus={(e) => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = '0 0 0 2px var(--accent-light)' }}
              onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
            />
            <div className="flex gap-3">
              <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                placeholder="API Key"
                className="flex-1 px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                onFocus={(e) => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = '0 0 0 2px var(--accent-light)' }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
              />
              <input type="text" value={model} onChange={(e) => setModel(e.target.value)}
                placeholder="Model"
                className="flex-1 px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                onFocus={(e) => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = '0 0 0 2px var(--accent-light)' }}
                onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
              />
            </div>
            <button onClick={handleAdd} disabled={saving}
              className="w-full px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-40"
              style={{ background: 'var(--accent-gradient)', color: '#ffffff' }}
            >
              {saving ? '添加中...' : '添加预设'}
            </button>
          </div>
        </div>

        {/* Right: Presets list */}
        <div className="space-y-3">
          {defaultPreset && (
            <PresetCard
              label={defaultPreset.label}
              base_url={defaultPreset.base_url}
              model={defaultPreset.model}
              isActive={activeId === null}
              onClick={handleReset}
              onDelete={null}
            />
          )}
          {presets.map((p) => (
            <PresetCard
              key={p.id}
              label={p.label}
              base_url={p.base_url}
              model={p.model}
              isActive={p.is_active}
              onClick={() => handleActivate(p.id)}
              onDelete={() => handleDelete(p.id)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function PresetCard({
  label, base_url, model, isActive, onClick, onDelete,
}: {
  label: string
  base_url: string
  model: string
  isActive: boolean
  onClick: () => void
  onDelete: (() => void) | null
}) {
  return (
    <button
      onClick={onClick}
      className="w-full p-4 rounded-xl border text-left transition-all duration-200"
      style={{
        backgroundColor: isActive ? 'var(--bg-secondary)' : 'var(--bg-secondary)',
        borderColor: isActive ? 'var(--accent)' : 'var(--border)',
        boxShadow: isActive ? '0 0 0 1px var(--accent), 0 4px 14px rgba(99, 102, 241, 0.15)' : 'none',
        opacity: isActive ? 1 : 0.7,
      }}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0 mr-4">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold" style={{ color: isActive ? 'var(--accent)' : 'var(--text-primary)' }}>
              {label}
            </p>
            {isActive && (
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium" style={{ background: 'var(--accent-gradient)', color: '#ffffff' }}>
                使用中
              </span>
            )}
          </div>
          <p className="text-xs mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>
            {base_url}
          </p>
          <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
            {model}
          </p>
        </div>
        {onDelete && (
          <span
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="flex-shrink-0 px-2 py-1 rounded text-xs transition-colors hover:opacity-80"
            style={{ color: 'var(--danger)' }}
          >
            删除
          </span>
        )}
      </div>
    </button>
  )
}
