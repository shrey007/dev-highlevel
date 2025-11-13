const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export interface ChatResponse {
  reply: string
  actions: Array<{
    tool: string
    input: any
    output?: any
    error?: string
  }>
  memory_diff: Array<{
    key: string
    old_value: any
    new_value: any
  }>
}

export async function chatApi(sessionId: string, message: string, apiKey?: string): Promise<ChatResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json'
  }
  
  if (apiKey) {
    headers['X-OPENAI-KEY'] = apiKey
  }
  
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      session_id: sessionId,
      message
    })
  })
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  
  return response.json()
}

