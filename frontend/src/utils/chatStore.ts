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
    return full.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  } catch {
    return loadCache().sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  }
}

/** Synchronous version for initial render (uses cache only). */
export function listChatsSync(): ChatRecord[] {
  return loadCache().sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
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
