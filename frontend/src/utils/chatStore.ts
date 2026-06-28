/** Chat persistence: stores conversations in localStorage. */

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

const STORAGE_KEY = 'aifund5_chats'

function loadAll(): ChatRecord[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveAll(records: ChatRecord[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(records))
}

export function listChats(): ChatRecord[] {
  return loadAll().sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
}

export function getChat(id: string): ChatRecord | null {
  return loadAll().find((c) => c.id === id) || null
}

export function saveChat(id: string, messages: ChatMessage[]): void {
  const records = loadAll()
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
  saveAll(records)
}

export function deleteChat(id: string): void {
  const records = loadAll().filter((c) => c.id !== id)
  saveAll(records)
}

export function createChat(): string {
  return crypto.randomUUID()
}
