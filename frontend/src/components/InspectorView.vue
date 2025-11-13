<template>
  <div class="bg-white rounded-lg shadow-lg h-[600px] flex flex-col">
    <div class="p-4 border-b">
      <h2 class="text-xl font-semibold">Inspector</h2>
    </div>
    
    <div class="flex-1 overflow-y-auto p-4 space-y-6">
      <div>
        <h3 class="text-lg font-medium mb-3 text-gray-700">Actions</h3>
        <div v-if="actions.length === 0" class="text-sm text-gray-500">
          No actions yet
        </div>
        <div v-for="(action, idx) in actions" :key="idx" class="mb-4 p-3 rounded border" :class="isActionLoading(action.tool) ? 'bg-blue-50 border-blue-200' : 'bg-gray-50'">
          <div class="flex items-center gap-2 mb-1">
            <div class="font-semibold text-sm text-blue-600">{{ action.tool }}</div>
            <div v-if="isActionLoading(action.tool)" class="flex items-center gap-1">
              <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
              <span class="text-xs text-blue-600">Executing...</span>
            </div>
          </div>
          <div class="text-xs text-gray-600 mb-2">
            <strong>Input:</strong> <pre class="mt-1 text-xs">{{ JSON.stringify(action.input, null, 2) }}</pre>
          </div>
          <div v-if="action.output" class="text-xs text-gray-600">
            <strong>Output:</strong> <pre class="mt-1 text-xs">{{ JSON.stringify(action.output, null, 2) }}</pre>
          </div>
          <div v-if="action.error" class="text-xs text-red-600 mt-2">
            <strong>Error:</strong> {{ action.error }}
          </div>
        </div>
      </div>
      
      <div class="border-t pt-4">
        <h3 class="text-lg font-medium mb-3 text-gray-700">Memory Updates</h3>
        <div v-if="memoryDiff.length === 0" class="text-sm text-gray-500">
          No memory updates yet
        </div>
        <div v-for="(diff, idx) in memoryDiff" :key="idx" class="mb-2 p-2 bg-yellow-50 rounded border border-yellow-200">
          <div class="text-sm font-semibold text-gray-700">{{ diff.key }}</div>
          <div class="text-xs text-gray-600 mt-1">
            <span v-if="diff.old_value !== null">Old: {{ JSON.stringify(diff.old_value) }}</span>
            <span v-else class="text-gray-400">(new)</span>
          </div>
          <div class="text-xs text-green-600 mt-1">
            New: {{ JSON.stringify(diff.new_value) }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useInspectorStore } from '../stores/inspector'

const inspectorStore = useInspectorStore()

const actions = computed(() => inspectorStore.actions)
const memoryDiff = computed(() => inspectorStore.memoryDiff)

const isActionLoading = (toolName: string) => {
  return inspectorStore.isActionLoading(toolName)
}
</script>

