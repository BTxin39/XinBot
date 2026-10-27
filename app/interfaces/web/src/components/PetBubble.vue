<script setup>
/**
 * 桌宠语音气泡。
 *
 * 设计取舍：
 *  - **打字机效果在前端做**，不依赖后端逐 token。理由：气泡展示的是"已经生成完
 *    的最近一条回复"，重放它不需要流；而真流式（v0.2.2 已实现）用于用户正在
 *    对话的界面。两者互补，不在一个组件里耦合。
 *  - 文字超长时自动加速，避免 500 字要等 15 秒。
 *  - 用 CSS transition 淡入淡出，透明窗口里不要有生硬的方块出现。
 */
import { ref, watch, onUnmounted, computed } from 'vue';

const props = defineProps({
  text: { type: String, default: '' },
  /** 每字毫秒数；长文本会自动折算得更快 */
  speed: { type: Number, default: 32 },
  maxChars: { type: Number, default: 220 },
});

const shown = ref('');
let timer = null;

const display = computed(() => {
  const value = (props.text || '').replace(/\s+/g, ' ').trim();
  if (value.length <= props.maxChars) return value;
  return `${value.slice(0, props.maxChars)}…`;
});

function stop() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }
}

function type() {
  stop();
  shown.value = '';
  const full = display.value;
  if (!full) return;
  // 长文本加速：保证整段在 2.5 秒左右出完
  const perChar = Math.max(8, Math.min(props.speed, Math.round(2500 / full.length)));
  let index = 0;
  timer = setInterval(() => {
    index += 1;
    shown.value = full.slice(0, index);
    if (index >= full.length) stop();
  }, perChar);
}

watch(() => props.text, type, { immediate: true });
onUnmounted(stop);
</script>

<template>
  <transition name="bubble">
    <div v-if="shown" class="pet-bubble" role="status" aria-live="polite">
      <span>{{ shown }}</span>
      <i v-if="shown.length < display.length" class="caret" />
    </div>
  </transition>
</template>

<style scoped>
.pet-bubble {
  position: relative;
  max-width: 260px;
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.55;
  color: #1f2937;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.28);
  word-break: break-word;
  white-space: pre-wrap;
}
/* 小尾巴指向角色 */
.pet-bubble::after {
  content: '';
  position: absolute;
  left: 26px;
  bottom: -6px;
  width: 12px;
  height: 12px;
  background: rgba(255, 255, 255, 0.96);
  transform: rotate(45deg);
  border-radius: 2px;
}
.caret {
  display: inline-block;
  width: 2px;
  height: 12px;
  margin-left: 2px;
  vertical-align: -2px;
  background: #6b7280;
  animation: blink 1s steps(2) infinite;
}
@keyframes blink {
  50% { opacity: 0; }
}
.bubble-enter-active,
.bubble-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.bubble-enter-from,
.bubble-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
