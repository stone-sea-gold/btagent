import { useState, useEffect } from 'react'

interface Preset {
  id: number
  label: string
  base_url: string
  model: string
  is_active: boolean
}

/** Shape of GET /api/data/coverage. */
interface Coverage {
  data_start_date: string | null
  data_end_date: string | null
  is_stale: boolean
  days_behind: number | null
  status: string
  warning?: string
  warehouse?: {
    status?: string
    bars?: number
    codes?: number
    first_date?: string | null
    last_date?: string | null
    factor_rows?: number
    calendar_days?: number
  }
}

/** Shape of the sync job endpoints. */
interface SyncJob {
  id: string
  status: 'running' | 'done' | 'error' | 'none'
  phase: string
  total: number
  completed: number
  current_code: string
  progress: number
  codes_synced: number
  codes_skipped: number
  codes_failed: number
  bars_written: number
  factors_written: number
  dataset_days: number
  finished_at: string | null
  error: string
}

const PHASE_LABEL: Record<string, string> = {
  starting: '准备中',
  connecting: '连接数据源',
  syncing: '同步行情到仓库',
  exporting: '导出回测数据集',
  finished: '已完成',
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

  // Add form
  const [vendor, setVendor] = useState('')
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
    }
  }

  useEffect(() => { fetchPresets() }, [])

  const handleAdd = async () => {
    const missing: string[] = []
    if (!label.trim()) missing.push('名称')
    if (!baseUrl.trim()) missing.push('Base URL')
    if (!apiKey.trim()) missing.push('API Key')
    if (!model.trim()) missing.push('Model')
    if (missing.length > 0) {
      showMsg('error', `请填写：${missing.join('、')}`)
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
      setVendor(''); setLabel(''); setBaseUrl(''); setApiKey(''); setModel('')
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

      {/* Local market data status + update */}
      <LocalDataCard />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left: Add form */}
        <div className="p-5 rounded-xl border h-fit" style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <h2 className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
            添加预设
          </h2>
          <div className="space-y-3">
            <select value={vendor} onChange={(e) => {
                const selected = e.target.value
                setVendor(selected)
                const preset = PRESET_PROVIDERS.find((p) => p.label === selected)
                if (preset) {
                  setBaseUrl(preset.baseUrl)
                  setModel(preset.model || '')
                  setLabel(preset.label)
                } else if (PRESET_PROVIDERS.some((p) => p.label === label)) {
                  // 从预置厂商切回自定义，清掉自动带入的名称
                  setLabel('')
                }
              }}
              className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200 appearance-none cursor-pointer"
              style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
            >
              <option value="">自定义 / 其他（OpenAI 兼容）</option>
              {PRESET_PROVIDERS.map((p) => (
                <option key={p.label} value={p.label}>{p.label}</option>
              ))}
            </select>
            <input type="text" value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder="名称（自定义时可随意命名）"
              className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
              style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              onFocus={(e) => { e.target.style.borderColor = 'var(--accent)'; e.target.style.boxShadow = '0 0 0 2px var(--accent-light)' }}
              onBlur={(e) => { e.target.style.borderColor = 'var(--border)'; e.target.style.boxShadow = 'none' }}
            />
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

/** Latest dates the local data covers, plus a one-click update.
 *
 * The warehouse and the exported dataset are separate stores and drift apart:
 * the warehouse can be current while the dataset a backtest actually reads is a
 * year behind. Both dates are therefore shown, and a run re-exports at the end
 * so the engine is never left reading the older window.
 */
function LocalDataCard() {
  const [coverage, setCoverage] = useState<Coverage | null>(null)
  const [job, setJob] = useState<SyncJob | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')

  const loadCoverage = async () => {
    try {
      const res = await fetch('/api/data/coverage')
      setCoverage(await res.json())
    } catch {
      setError('读取本地数据状态失败')
    }
  }

  useEffect(() => {
    loadCoverage()
    // A sync may already be running from before this page was opened.
    fetch('/api/data/sync/latest')
      .then((res) => res.json())
      .then((data: SyncJob) => { if (data.status === 'running') setJob(data) })
      .catch(() => { /* no job yet */ })
  }, [])

  // Poll while the job runs, then refresh the coverage figures once it settles.
  const jobId = job?.id
  const jobStatus = job?.status
  useEffect(() => {
    if (!jobId || jobStatus !== 'running') return
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/data/sync/${jobId}`)
        const data: SyncJob = await res.json()
        setJob(data)
        if (data.status !== 'running') loadCoverage()
      } catch { /* transient: keep polling */ }
    }, 1500)
    return () => clearInterval(timer)
  }, [jobId, jobStatus])

  const startSync = async () => {
    setError('')
    setStarting(true)
    try {
      const res = await fetch('/api/data/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: 'csi300' }),
      })
      const data = await res.json()
      if (!res.ok) setError(data.detail || '启动同步失败')
      else setJob(data)
    } catch {
      setError('启动同步失败')
    } finally {
      setStarting(false)
    }
  }

  const warehouse = coverage?.warehouse
  const datasetEnd = coverage?.data_end_date ?? null
  const warehouseEnd = warehouse?.last_date ?? null
  const datasetBehind = Boolean(warehouseEnd && datasetEnd && warehouseEnd > datasetEnd)
  const running = job?.status === 'running'

  const row = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-4 text-sm">
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  )

  return (
    <div
      className="mb-5 p-5 rounded-xl border"
      style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <h2 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          本地数据
        </h2>
        <button
          onClick={startSync}
          disabled={running || starting}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 hover:scale-105 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--accent-gradient)', color: '#ffffff' }}
        >
          {running ? '更新中…' : '更新数据'}
        </button>
      </div>

      <div className="space-y-1.5">
        {row('行情仓库最新', warehouseEnd
          || (warehouse?.status === 'no_warehouse' ? '尚未同步' : '—'))}
        {row('回测数据集截至', datasetEnd || '尚未导出')}
        {row('股票数 / bar 数', warehouse?.codes != null
          ? `${warehouse.codes} 只 / ${(warehouse.bars ?? 0).toLocaleString()} 条`
          : '—')}
        {row('复权因子行数', warehouse?.factor_rows != null
          ? warehouse.factor_rows.toLocaleString()
          : '—')}
      </div>

      {datasetBehind && (
        <p className="mt-3 text-xs" style={{ color: 'var(--warning)' }}>
          ⚠️ 回测数据集落后于仓库（{datasetEnd} &lt; {warehouseEnd}）。回测只会用到数据集内的数据，
          点「更新数据」会重新导出。
        </p>
      )}

      {coverage?.is_stale && !datasetBehind && (
        <p className="mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>
          数据滞后 {coverage.days_behind} 天（最新 {datasetEnd}）。
        </p>
      )}

      {running && job && (
        <div className="mt-4">
          <div className="flex justify-between text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            <span>
              {PHASE_LABEL[job.phase] || job.phase}
              {job.current_code ? ` · ${job.current_code}` : ''}
            </span>
            <span>{job.completed} / {job.total || '…'}</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-tertiary)' }}>
            <div
              className="h-full transition-all duration-300"
              style={{ width: `${Math.round(job.progress * 100)}%`, background: 'var(--accent-gradient)' }}
            />
          </div>
          <p className="mt-2 text-xs" style={{ color: 'var(--text-muted)' }}>
            逐只拉取，300 只约需数分钟；期间可离开本页，任务在后台继续。
          </p>
        </div>
      )}

      {job?.status === 'done' && (
        <p className="mt-3 text-xs" style={{ color: 'var(--success)' }}>
          ✅ 更新完成：{job.codes_synced} 只已同步
          {job.codes_skipped > 0 && ` · ${job.codes_skipped} 只已是最新`}
          {job.codes_failed > 0 && ` · ${job.codes_failed} 只失败`}
          {' · '}{job.bars_written.toLocaleString()} 条 bar
          {job.dataset_days > 0 && ` · 数据集 ${job.dataset_days} 个交易日`}
        </p>
      )}

      {job?.status === 'error' && (
        <p className="mt-3 text-xs" style={{ color: 'var(--danger)' }}>
          ❌ 更新失败：{job.error}
        </p>
      )}

      {error && <p className="mt-3 text-xs" style={{ color: 'var(--danger)' }}>{error}</p>}
    </div>
  )
}
