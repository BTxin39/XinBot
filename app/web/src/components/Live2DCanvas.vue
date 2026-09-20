<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue';
import { ZoomIn, ZoomOut, RotateCcw, Hand, Pause, Play, Shirt } from 'lucide-vue-next';
import { pet, state } from '../state.js';
const host = ref(null);
const canvas = ref(null);
const error = ref('');
const loading = ref(false);
const paused = ref(false);
const zoom = ref(1);
let application, model, observer, animation, generation = 0, spriteImage, lastFrame = 0, frame = 0, row = 0, interactionUntil = 0;
let baseWidth = 1, baseHeight = 1;
let corePromise;
function loadCore() {
  if (window.Live2DCubismCore) return Promise.resolve();
  if (!corePromise) corePromise = new Promise((resolve, reject) => {
    const script = document.createElement('script'); script.src = '/vendor/live2dcubismcore.min.js';
    script.onload = resolve; script.onerror = () => { corePromise = null; reject(new Error('Cubism Core 未安装')); };
    document.head.appendChild(script);
  });
  return corePromise;
}
function resize() {
  if (!host.value) return;
  const width = host.value.clientWidth, height = host.value.clientHeight;
  if (application && model) {
    application.renderer.resize(width, height);
    const scale = Math.min(width * .94 / baseWidth, height * .94 / baseHeight) * zoom.value;
    model.scale.set(scale); model.anchor.set(.5, 1); model.position.set(width / 2, height * .98);
  }
}
function cleanup() {
  cancelAnimationFrame(animation);
  if (application) application.destroy(false, { children: true, texture: true, baseTexture: true });
  application = null; model = null; spriteImage = null;
}
async function load() {
  const version = ++generation;
  cleanup(); error.value = ''; loading.value = true; zoom.value = 1;
  if (!pet.value || !canvas.value) { loading.value = false; return; }
  try {
    if (pet.value.type === 'live2d') {
      await loadCore();
      const PIXI = await import('pixi.js'); window.PIXI = PIXI;
      const { Live2DModel } = await import('pixi-live2d-display/cubism4');
      if (version !== generation) return;
      const instance = await Live2DModel.from(pet.value.url, { autoInteract: true });
      if (version !== generation) { instance.destroy(); return; }
      model = instance; baseWidth = model.width; baseHeight = model.height;
      application = new PIXI.Application({ view: canvas.value, backgroundAlpha: 0, antialias: true, autoDensity: true, resolution: Math.min(devicePixelRatio, 2), preserveDrawingBuffer: true });
      application.stage.addChild(model); resize();
      application.renderer.render(application.stage);
      state.previews[pet.value.id] = canvas.value.toDataURL('image/png');
      if (paused.value) application.stop();
    } else {
      const picture = new Image(); picture.src = pet.value.url;
      await picture.decode(); if (version !== generation) return;
      spriteImage = picture; frame = 0;
      animateSprite(performance.now());
    }
  } catch (failure) { if (version === generation) error.value = failure.message || '模型加载失败'; }
  finally { if (version === generation) loading.value = false; }
}
function animateSprite(now) {
  if (!spriteImage || !canvas.value || !host.value) return;
  const context = canvas.value.getContext('2d');
  const width = host.value.clientWidth, height = host.value.clientHeight;
  const ratio = Math.min(devicePixelRatio, 2);
  canvas.value.width = width * ratio; canvas.value.height = height * ratio;
  context.scale(ratio, ratio);
  if (now > interactionUntil) row = state.busy ? 7 : ({ happy: 4, sad: 5, sleepy: 5, angry: 8 })[state.status.emotion] || 0;
  if (!paused.value && now - lastFrame > 160) { frame++; lastFrame = now; }
  const columns = pet.value.columns || 8, rows = pet.value.rows || 9;
  const cellWidth = spriteImage.width / columns, cellHeight = spriteImage.height / rows;
  const size = Math.min(width * .86, height * .8) * zoom.value;
  context.drawImage(spriteImage, frame % (pet.value.frames?.[row] || columns) * cellWidth, row * cellHeight, cellWidth, cellHeight,
    (width - size) / 2, (height - size * cellHeight / cellWidth) / 2, size, size * cellHeight / cellWidth);
  animation = requestAnimationFrame(animateSprite);
}
function interact() { if (model) { model.expression(); model.motion('TapBody'); } row = 3; interactionUntil = performance.now() + 2400; }
function changeZoom(amount) { zoom.value = Math.max(.6, Math.min(1.6, zoom.value + amount)); resize(); }
function toggle() { paused.value = !paused.value; if (application) paused.value ? application.stop() : application.start(); }
watch(() => pet.value?.id, load, { flush: 'post' });
onMounted(() => { observer = new ResizeObserver(resize); observer.observe(host.value); load(); });
onUnmounted(() => { generation++; cleanup(); observer?.disconnect(); });
</script>

<template>
  <div class="pet-workspace">
    <div class="pet-stage" ref="host" @click="interact">
      <canvas :key="pet?.id" ref="canvas" :aria-label="pet?.name || '桌宠'" />
      <div v-if="loading || error || !pet" class="stage-status" role="status">{{ error || (loading ? '正在唤醒…' : '还没有桌宠模型') }}<button v-if="error" @click.stop="load">重新加载</button></div>
    </div>
    <div class="pet-caption"><span>{{ pet?.name || '未选择外观' }}</span><span class="badge">{{ pet?.type === 'live2d' ? 'Live2D' : 'Sprite' }}</span></div>
    <div class="pet-toolbar">
      <button class="icon-button" title="缩小" aria-label="缩小" @click="changeZoom(-.1)"><ZoomOut :size="18"/></button>
      <button class="icon-button" title="重置视角" aria-label="重置视角" @click="zoom = 1; resize()"><RotateCcw :size="17"/></button>
      <button class="icon-button" title="放大" aria-label="放大" @click="changeZoom(.1)"><ZoomIn :size="18"/></button>
      <span class="divider"/>
      <button class="icon-button" :title="paused ? '播放' : '暂停'" :aria-label="paused ? '播放' : '暂停'" @click="toggle"><component :is="paused ? Play : Pause" :size="17"/></button>
      <button class="icon-button" title="打招呼" aria-label="打招呼" @click="interact"><Hand :size="18"/></button>
      <RouterLink class="icon-button" title="更换外观" aria-label="更换外观" to="/appearance"><Shirt :size="18"/></RouterLink>
    </div>
  </div>
</template>
