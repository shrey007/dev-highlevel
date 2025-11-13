<template>
  <div class="bg-white rounded-lg shadow-lg h-[600px] flex flex-col">
    <div class="p-4 border-b">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-xl font-semibold">Chat</h2>
        <div class="flex items-center gap-2">
          <button
            @click="clearConversation"
            class="text-xs px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded text-gray-700"
            title="Clear conversation"
          >
            Clear
          </button>
          <div class="flex flex-col">
            <input
              v-model="apiKey"
              type="password"
              placeholder="OpenAI API Key (optional)"
              class="text-xs px-2 py-1 border rounded"
              @input="saveApiKey"
            />
            <span class="text-xs text-gray-500 mt-0.5">Leave empty to use server key</span>
          </div>
        </div>
      </div>
    </div>
    
    <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-4">
      <div v-for="(msg, idx) in messages" :key="idx" class="flex" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
        <div class="max-w-[80%] rounded-lg p-3" :class="msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-800'">
          <p class="text-sm whitespace-pre-wrap">{{ msg.content }}</p>
        </div>
      </div>
      <div v-if="loading" class="flex justify-start">
        <div class="bg-gray-200 rounded-lg p-3">
          <p class="text-sm text-gray-600">Thinking...</p>
        </div>
      </div>
    </div>
    
    <div class="p-4 border-t">
      <form @submit.prevent="sendMessage" class="flex gap-2">
        <input
          v-model="inputMessage"
          type="text"
          placeholder="Type your message..."
          class="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          :disabled="loading"
        />
        <button
          type="submit"
          class="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          :disabled="loading || !inputMessage.trim()"
        >
          Send
        </button>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { chatApi, getConversation } from '../api'
import { useInspectorStore } from '../stores/inspector'

const messages = ref<Array<{ role: string; content: string }>>([])
const inputMessage = ref('')
const loading = ref(false)
const apiKey = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inspectorStore = useInspectorStore()

// Generate or retrieve session ID
const generateSessionId = () => {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9)
}

const getSessionId = () => {
  let sessionId = localStorage.getItem('travel_agent_session_id')
  if (!sessionId) {
    sessionId = generateSessionId()
    localStorage.setItem('travel_agent_session_id', sessionId)
  }
  return sessionId
}

const sessionId = ref(getSessionId())

onMounted(async () => {
  // Load saved API key
  const saved = sessionStorage.getItem('openai_api_key')
  if (saved) {
    apiKey.value = saved
  }
  
  // Try to load existing conversation
  try {
    const conversation = await getConversation(sessionId.value)
    
    if (conversation.exists && conversation.turns && conversation.turns.length > 0) {
      // Restore conversation from backend
      messages.value = conversation.turns.map(turn => ({
        role: turn.role,
        content: turn.content
      }))
      scrollToBottom()
    } else {
      // New conversation
      messages.value.push({
        role: 'assistant',
        content: 'Hello! I\'m your travel agent. I can help you plan trips by searching for flights, hotels, and activities. What would you like to do?'
      })
    }
  } catch (error) {
    // If backend call fails, start fresh
    console.error('Failed to load conversation:', error)
    messages.value.push({
      role: 'assistant',
      content: 'Hello! I\'m your travel agent. I can help you plan trips by searching for flights, hotels, and activities. What would you like to do?'
    })
  }
})

const saveApiKey = () => {
  sessionStorage.setItem('openai_api_key', apiKey.value)
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const clearConversation = () => {
  if (confirm('Clear conversation history? This will start a new session.')) {
    // Generate new session ID and clear localStorage
    sessionId.value = generateSessionId()
    localStorage.setItem('travel_agent_session_id', sessionId.value)
    
    // Reset UI
    messages.value = [{
      role: 'assistant',
      content: 'Hello! I\'m your travel agent. I can help you plan trips by searching for flights, hotels, and activities. What would you like to do?'
    }]
    inspectorStore.clearActions()
    inspectorStore.clearMemoryDiff()
  }
}

const sendMessage = async () => {
  if (!inputMessage.value.trim() || loading.value) return
  
  const userMessage = inputMessage.value
  messages.value.push({ role: 'user', content: userMessage })
  inputMessage.value = ''
  loading.value = true
  scrollToBottom()
  
  inspectorStore.clearActions()
  inspectorStore.clearMemoryDiff()
  
  try {
    const response = await chatApi(sessionId.value, userMessage, apiKey.value)
    
    messages.value.push({ role: 'assistant', content: response.reply })
    
    if (response.actions && response.actions.length > 0) {
      inspectorStore.setActions(response.actions)
    }
    
    if (response.memory_diff && response.memory_diff.length > 0) {
      inspectorStore.setMemoryDiff(response.memory_diff)
    }
  } catch (error: any) {
    messages.value.push({
      role: 'assistant',
      content: `Error: ${error.message || 'Something went wrong'}`
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}
</script>

