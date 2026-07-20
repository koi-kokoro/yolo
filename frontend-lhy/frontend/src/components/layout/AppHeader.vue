<template>
  <header class="app-header">
    <div class="header-left">
      <div class="header-logo">
        <span>🌾</span>
      </div>
      <span class="header-title">RSOD 目标检测智能体</span>
    </div>
  </header>
</template>

<script setup>
</script>

<style lang="scss" scoped>
.app-header {
  height: $header-height;
  background: linear-gradient(135deg, #2A241E 0%, #1A1612 100%);
  border-bottom: none;
  display: flex;
  align-items: center;
  padding: 0 $spacing-lg;
  box-shadow: 
    0 2px 12px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
  z-index: 100;
  position: relative;
}

.app-header::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(139, 115, 85, 0.3) 50%, transparent 100%);
}

.header-left {
  display: flex;
  align-items: center;
  gap: $spacing-md;
}

.header-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #8B7355 0%, #A68B67 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  box-shadow: 0 2px 8px rgba(139, 115, 85, 0.3);
}

.header-title {
  font-size: 18px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: 1.5px;
}
</style>
