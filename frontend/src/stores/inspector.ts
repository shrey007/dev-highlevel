import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useInspectorStore = defineStore('inspector', () => {
  const actions = ref<any[]>([])
  const memoryDiff = ref<any[]>([])
  const loadingActions = ref<Set<string>>(new Set())
  
  function setActions(newActions: any[]) {
    actions.value = newActions
    loadingActions.value.clear()
  }
  
  function setMemoryDiff(diffs: any[]) {
    memoryDiff.value = diffs
  }
  
  function clearActions() {
    actions.value = []
    loadingActions.value.clear()
  }
  
  function clearMemoryDiff() {
    memoryDiff.value = []
  }
  
  function setActionLoading(toolName: string, loading: boolean) {
    if (loading) {
      loadingActions.value.add(toolName)
    } else {
      loadingActions.value.delete(toolName)
    }
  }
  
  function isActionLoading(toolName: string): boolean {
    return loadingActions.value.has(toolName)
  }
  
  return {
    actions,
    memoryDiff,
    loadingActions,
    setActions,
    setMemoryDiff,
    clearActions,
    clearMemoryDiff,
    setActionLoading,
    isActionLoading
  }
})

