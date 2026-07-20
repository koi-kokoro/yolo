<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const MIN_SIDEBAR_WIDTH = 224
const MAX_SIDEBAR_WIDTH = 356
const COLLAPSE_THRESHOLD = 120
const DEFAULT_SIDEBAR_WIDTH = 272
const SIDEBAR_WIDTH_KEY = 'rsod-sidebar-width'
const SIDEBAR_COLLAPSED_KEY = 'rsod-sidebar-collapsed'

function getStoredWidth() {
  const value = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY))
  return Number.isFinite(value)
    ? Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, value))
    : DEFAULT_SIDEBAR_WIDTH
}

const sidebarWidth = ref(getStoredWidth())
const lastExpandedWidth = ref(sidebarWidth.value)
const isSidebarCollapsed = ref(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true')
const isResizing = ref(false)

const sidebarStyle = computed(() => ({
  '--sidebar-current-width': `${isSidebarCollapsed.value ? 0 : sidebarWidth.value}px`,
}))

function saveSidebarState() {
  window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(lastExpandedWidth.value))
  window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(isSidebarCollapsed.value))
}

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  if (!isSidebarCollapsed.value) {
    sidebarWidth.value = lastExpandedWidth.value
  }
  saveSidebarState()
}

function handlePointerMove(event) {
  if (!isResizing.value) return

  if (event.clientX < COLLAPSE_THRESHOLD) {
    isSidebarCollapsed.value = true
    return
  }

  const nextWidth = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, event.clientX))
  isSidebarCollapsed.value = false
  sidebarWidth.value = nextWidth
  lastExpandedWidth.value = nextWidth
}

function stopResizing() {
  if (!isResizing.value) return
  isResizing.value = false
  document.body.classList.remove('is-resizing-sidebar')
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', stopResizing)
  window.removeEventListener('pointercancel', stopResizing)
  saveSidebarState()
}

function startResizing(event) {
  if (event.button !== 0) return
  isResizing.value = true
  document.body.classList.add('is-resizing-sidebar')
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopResizing)
  window.addEventListener('pointercancel', stopResizing)
  event.preventDefault()
}

function handleResizerKeydown(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()

  if (event.key === 'Home') {
    isSidebarCollapsed.value = true
    saveSidebarState()
    return
  }

  const direction = event.key === 'ArrowLeft' ? -1 : 1
  const nextWidth = event.key === 'End'
    ? MAX_SIDEBAR_WIDTH
    : Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, sidebarWidth.value + direction * 16))

  sidebarWidth.value = nextWidth
  lastExpandedWidth.value = nextWidth
  saveSidebarState()
}

onBeforeUnmount(stopResizing)
</script>

<template>
  <div class="main-layout">
    <AppHeader :sidebar-collapsed="isSidebarCollapsed" @toggle-sidebar="toggleSidebar" />
    <div
      class="main-layout__body"
      :class="{ 'main-layout__body--resizing': isResizing }"
      :style="sidebarStyle"
    >
      <AppSidebar :collapsed="isSidebarCollapsed" />
      <div
        v-if="!isSidebarCollapsed"
        class="main-layout__resizer"
        role="separator"
        tabindex="0"
        aria-label="调整侧边栏宽度"
        aria-orientation="vertical"
        :aria-valuenow="sidebarWidth"
        :aria-valuemin="MIN_SIDEBAR_WIDTH"
        :aria-valuemax="MAX_SIDEBAR_WIDTH"
        @pointerdown="startResizing"
        @keydown="handleResizerKeydown"
      />
      <main class="main-layout__content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.main-layout {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(rgba($primary-color, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba($primary-color, 0.035) 1px, transparent 1px),
    linear-gradient(180deg, #f8fbff 0%, #eef3f9 52%, #f7fafc 100%);
  background-size: 44px 44px, 44px 44px, auto;

  &::before {
    position: fixed;
    inset: 0;
    pointer-events: none;
    content: '';
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.38), rgba(255, 255, 255, 0));
  }
}

.main-layout__body {
  position: relative;
  z-index: 1;
  display: flex;
  min-height: calc(100vh - $header-height);
}

.main-layout__resizer {
  position: relative;
  z-index: 2;
  flex: 0 0 8px;
  width: 8px;
  margin-left: -4px;
  cursor: col-resize;
  touch-action: none;

  &::after {
    position: absolute;
    top: 18px;
    bottom: 18px;
    left: 3px;
    width: 2px;
    content: '';
    background: rgba($primary-color, 0.16);
    border-radius: 999px;
    transition: background-color 0.15s ease, box-shadow 0.15s ease;
  }

  &:hover::after,
  &:focus-visible::after,
  .main-layout__body--resizing &::after {
    background: $primary-light;
    box-shadow: 0 0 20px rgba($primary-color, 0.58);
  }

  &:focus-visible {
    outline: 0;
  }
}

.main-layout__content {
  flex: 1;
  min-width: 0;
  max-height: calc(100vh - $header-height);
  padding: 20px;
  overflow: auto;
}

@media (max-width: 768px) {
  .main-layout__body {
    flex-direction: column;
  }

  .main-layout__content {
    max-height: none;
    padding: 16px;
  }

  .main-layout__resizer {
    display: none;
  }
}

:global(body.is-resizing-sidebar) {
  cursor: col-resize;
  user-select: none;
}
</style>
