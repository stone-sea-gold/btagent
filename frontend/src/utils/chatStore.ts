/** Chat persistence: localStorage cache + backend SQLite source of truth. */

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt?: string
}

export interface ChatRecord {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
}

const CACHE_KEY = 'btagent_chats'

// ── localStorage cache (fast read) ──────────────────────────────

function loadCache(): ChatRecord[] {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || '[]')
  } catch {
    return []
  }
}

function writeCache(records: ChatRecord[]): void {
  localStorage.setItem(CACHE_KEY, JSON.stringify(records))
}

// ── Backend sync helpers ────────────────────────────────────────

async function fetchBackend<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Public API ──────────────────────────────────────────────────

/** Parse a stored timestamp, tolerating both the legacy and the ISO shape.
 *
 * The backend used to write `YYYY-MM-DD HH:MM:SS` — UTC, but with no zone
 * marker — which JavaScript parses as *local* time. That rendered every time
 * eight hours early and scrambled the ordering once such values were mixed with
 * `toISOString()` ones in the cache. Legacy strings are therefore tagged as UTC
 * before parsing; ISO values pass straight through.
 */
export function parseTimestamp(value: string | undefined): number {
  if (!value) return 0
  const iso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? `${value.replace(' ', 'T')}Z`
    : value
  const ms = new Date(iso).getTime()
  return Number.isNaN(ms) ? 0 : ms
}

/** Most recently updated first. */
function byRecency(a: ChatRecord, b: ChatRecord): number {
  return parseTimestamp(b.updatedAt) - parseTimestamp(a.updatedAt)
}

export async function listChats(): Promise<ChatRecord[]> {
  // Try backend first, fall back to cache
  try {
    const { chats } = await fetchBackend<{ chats: { id: string; title: string; createdAt: string; updatedAt: string }[] }>('/api/chats')
    const full: ChatRecord[] = []
    for (const meta of chats) {
      try {
        const { found, chat } = await fetchBackend<{ found: boolean; chat?: ChatRecord }>(`/api/chats/${meta.id}`)
        if (found && chat) full.push(chat)
      } catch { /* skip */ }
    }
    writeCache(full)
    return full.sort(byRecency)
  } catch {
    return loadCache().sort(byRecency)
  }
}

/** Synchronous version for initial render (uses cache only). */
export function listChatsSync(): ChatRecord[] {
  return loadCache().sort(byRecency)
}

export function getChat(id: string): ChatRecord | null {
  // Read from cache (fast); the backend will be the source on next sync
  return loadCache().find((c) => c.id === id) || null
}

export async function getChatFromBackend(id: string): Promise<ChatRecord | null> {
  try {
    const { found, chat } = await fetchBackend<{ found: boolean; chat?: ChatRecord }>(`/api/chats/${id}`)
    return found && chat ? chat : null
  } catch {
    return getChat(id)
  }
}

export function saveChat(id: string, messages: ChatMessage[]): void {
  const records = loadCache()
  const now = new Date().toISOString()
  const existing = records.find((c) => c.id === id)
  const title = messages.find((m) => m.role === 'user')?.content?.slice(0, 40) || '新对话'

  if (existing) {
    existing.messages = messages
    existing.title = title
    existing.updatedAt = now
  } else {
    records.push({ id, title, messages, createdAt: now, updatedAt: now })
  }
  writeCache(records)

  // Sync to backend (fire-and-forget)
  fetch('/api/chats', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, messages, title }),
  }).catch(() => {})
}

export function deleteChat(id: string): void {
  const records = loadCache().filter((c) => c.id !== id)
  writeCache(records)

  // Sync to backend
  fetch(`/api/chats/${id}`, { method: 'DELETE' }).catch(() => {})
}

export function createChat(): string {
  return crypto.randomUUID()
}
