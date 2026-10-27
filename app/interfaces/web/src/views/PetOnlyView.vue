<script setup>
import { t } from '../i18n.js';
/**
 * 纯净桌宠视图（`/#/pet`）—— 桌面常驻窗专用。
 *
 * 与首页的区别：
 *  - 只有角色，没有顶栏/侧栏/工具栏/标题；
 *  - 背景完全透明（配合外壳的 chroma-key 透明方案）；
 *  - 向 Python 外壳暴露 `window.__xinbotPet` 桥，用于命中检测与情绪驱动。
 *
 * 为什么单独做一个视图而不是给首页加参数：
 * 首页承载聊天、面板、菜单，那些在透明窗口里全是噪音；
 * 而且桌宠窗口的尺寸很小（默认 320×420），复用首页布局会溢出。
 */
import { onMounted, onUnmounted, watch, ref } from 'vue';
import Live2DCanvas from '../components/Live2DCanvas.vue';
import PetBubble from '../components/PetBubble.vue';
import { state, pet, refresh, report } from '../state.js';

let timer = null;
let canvasEl = null;
let hideTimer = null;

/** 气泡文案；空字符串即隐藏 */
const bubbleText = ref('');
/** 已展示过的最后一条回复，用来判断"有新消息" */
let lastSeenMessage = '';

/**
 * 角色在窗口内的可见区域（CSS 像素），外壳用它做点击命中判断。
 *
 * 优先用 Live2D 模型的真实包围盒：窗口整块透明，但只有角色身上该接收鼠标，
 * 用画布矩形（等于整个窗口）会把桌面点击也吃掉。
 */
function measureBounds() {
  const box = state.petBounds;
  if (box && box.width > 0 && box.height > 0) {
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }
  if (!canvasEl) return null;
  const rect = canvasEl.getBoundingClientRect();
  return {
    x: Math.round(rect.left),
    y: Math.round(rect.top),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  };
}

/**
 * 用户点了桌宠：告诉后端"刚刚有互动"，避免刚点完就被搭话。
 * 失败无所谓——这只是优化体验，不该弹错误。
 */
function touchPet() {
  fetch('/api/pet/touch', { method: 'POST' }).catch(() => {});
}

/** 最近一次点击时间，用于识别双击（摸头） */
let lastTapAt = 0;
let dragState = null;

/**
 * 把互动交给后端判定，再执行返回的反应。
 * 冷却在服务端做，所以前端连点也不会刷屏。
 */
async function interact(kind) {
  try {
    const response = await fetch('/api/pet/interact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, emotion: state.status?.emotion || 'normal' }),
    });
    const result = await response.json();
    const reaction = result?.data?.reaction;
    if (!reaction) return;
    // state.reaction 由 Live2DCanvas 监听并执行动作
    state.reaction = reaction;
    if (reaction.bubble) showBubble(reaction.bubble);
    if (reaction.emotion) state.status = { ...state.status, emotion: reaction.emotion };
  } catch {
    // 互动失败不打扰用户
  }
}

function onPointerDown(event) {
  if (event.button !== 0) return;
  dragState = { x: event.clientX, y: event.clientY, dragging: false };
}

function onPointerMove(event) {
  if (!dragState || dragState.dragging) return;
  // 移动超过阈值才算拖拽，否则点击会被误判成拖动
  if (Math.hypot(event.clientX - dragState.x, event.clientY - dragState.y) > 6) {
    dragState.dragging = true;
    interact('drag_start');
  }
}

function onPointerUp() {
  const wasDragging = dragState?.dragging;
  dragState = null;
  if (wasDragging) { interact('drop'); return; }

  const now = Date.now();
  const isDouble = now - lastTapAt < 320;
  lastTapAt = now;
  interact(isDouble ? 'double_tap' : 'tap');
  touchPet();
}

/**
 * 显示一条气泡并在若干秒后淡出。
 * 停留时间随文字长度增加，否则长回复还没读完就消失了。
 */
function showBubble(text) {
  const value = (text || '').trim();
  if (!value) return;
  bubbleText.value = value;
  if (hideTimer) clearTimeout(hideTimer);
  const stay = Math.min(20000, 6000 + value.length * 40);
  hideTimer = setTimeout(() => { bubbleText.value = ''; }, stay);
}

onMounted(async () => {
  document.documentElement.classList.add('pet-mode');
  document.body.classList.add('pet-mode');
  try {
    await refresh();
  } catch (error) {
    report(error);
  }

  canvasEl = document.querySelector('.pet-stage canvas');

  // 暴露给 Python 外壳的桥。外壳用 evaluate_js 调用。
  window.__xinbotPet = {
    ready: Boolean(pet.value),
    petName: pet.value?.name || '',
    emotion: state.status?.emotion || 'normal',
    bounds: measureBounds,
    // 外壳可以直接推一条气泡（托盘提示、报错等）
    bubble: showBubble,
    // 外壳收到右键菜单选择后回调这里
    reload: () => refresh(),
  };

  // 情绪变化时同步给外壳（外壳可据此做托盘提示等）
  watch(
    () => state.status?.emotion,
    (value) => { if (window.__xinbotPet) window.__xinbotPet.emotion = value || 'normal'; },
  );

  // 轮询 `/api/pet/state`：拿情绪 + 最近一条回复
  timer = setInterval(async () => {
    try {
      const result = await fetch('/api/pet/state').then((r) => r.json());
      if (!result.ok) return;
      const data = result.data || {};
      state.status = { ...state.status, emotion: data.emotion || 'normal' };
      state.connected = true;
      if (window.__xinbotPet) window.__xinbotPet.ready = Boolean(pet.value);

      // 只在"有新的完整回复"时弹气泡：避免每轮轮询都重放同一句
      const latest = (data.latest_message || '').trim();
      if (latest && latest !== lastSeenMessage) {
        lastSeenMessage = latest;
        showBubble(latest);
      }

      // 待机行为：后端每次轮询最多给一条（问候 / 搭话）
      const action = data.idle_action;
      if (action && action.text) {
        showBubble(action.text);
        if (action.emotion) {
          state.status = { ...state.status, emotion: action.emotion };
        }
      }

      // 提醒优先：后端已保证一轮只给一条，且不会再重复
      const reminder = data.reminder;
      if (reminder && reminder.text) {
        showBubble(`⏰ ${reminder.text}`);
      }
    } catch {
      state.connected = false;
    }
  }, 2000);
});

onUnmounted(() => {
  clearInterval(timer);
  if (hideTimer) clearTimeout(hideTimer);
  document.documentElement.classList.remove('pet-mode');
  document.body.classList.remove('pet-mode');
  delete window.__xinbotPet;
});
</script>

<template>
  <div
    class="pet-standalone"
    title=""
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="dragState = null"
  >
    <PetBubble class="pet-bubble-slot" :text="bubbleText" />
    <Live2DCanvas bare />
    <div v-if="!pet" class="pet-standalone-empty" :data-hint="t('pet.pickAppearance')"></div>
  </div>
</template>

<style>
/* 全局：桌宠窗口必须让 html/body 透出桌面，否则外壳再怎么做也有一层底色 */
html.pet-mode,
body.pet-mode {
  background: transparent !important;
  overflow: hidden !important;
  margin: 0;
  padding: 0;
  user-select: none;
  -webkit-user-drag: none;
}
html.pet-mode #app,
body.pet-mode #app {
  background: transparent !important;
}
</style>

<style scoped>
.pet-standalone {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  background: transparent;
}
/* 气泡固定在上方：角色贴底，气泡不挤占它的位置 */
.pet-bubble-slot {
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  pointer-events: none;
}
/* 桌宠模式下画布占满窗口，角色贴底 */
.pet-standalone :deep(.pet-workspace) {
  width: 100%;
  height: 100%;
  background: transparent;
  border: none;
  box-shadow: none;
}
.pet-standalone :deep(.pet-stage) {
  width: 100%;
  height: 100%;
  background: transparent !important;
  cursor: grab;
}
.pet-standalone :deep(.pet-stage:active) {
  cursor: grabbing;
}
/*
 * 空状态提示（没有选择外观时）。
 *
 * 桌宠窗口是**完全透明**的，这段文字直接压在用户桌面上：
 * 深色壁纸下浅灰字几乎看不见（实测）。所以给它一个半透明胶囊底 +
 * 文字阴影，保证在任何壁纸/窗口上都可读。
 */
.pet-standalone-empty {
  position: absolute;
  inset: auto 0 12px 0;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.pet-standalone-empty::before {
  content: attr(data-hint);
  max-width: 82%;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1.5;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(2px);
}
</style>
