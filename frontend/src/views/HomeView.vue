<template>
  <div class="min-h-screen bg-gray-50">
    <div class="container mx-auto px-4 py-6">
      <h1 class="text-3xl font-bold text-gray-800 mb-6">Travel Agent</h1>
      
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2">
          <ChatView />
        </div>
        <div class="lg:col-span-1">
          <InspectorView />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import ChatView from '../components/ChatView.vue'
import InspectorView from '../components/InspectorView.vue'
</script>
