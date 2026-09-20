<script setup>
import { onMounted, onUnmounted } from 'vue';
import { MessageCircle, UsersRound, SlidersHorizontal, Library, Box, Sparkles, X, ArrowUpRight, Brain, Image } from 'lucide-vue-next';
import { state, character, refresh, report } from './state.js';
import Live2DCanvas from './components/Live2DCanvas.vue';
import api from './api.js';
import './style.css';
import './management.css';
const links = [ ['/', MessageCircle, '对话'], ['/persona', UsersRound, '角色卡'], ['/appearance', Box, '桌宠外观'], ['/memory', Brain, '记忆'], ['/ascii', Image, '字符画'], ['/knowledge', Library, '知识库'], ['/settings', SlidersHorizontal, '模型与连接'] ];
let timer;
onMounted(async () => {
  try { await refresh(); } catch (error) { report(error); }
  timer = setInterval(async () => {
    try { state.status = (await api.getStatus()).data; state.connected = true; }
    catch { state.connected = false; }
  }, 5000);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <div class="workspace">
    <header class="app-header">
      <RouterLink to="/" class="brand"><span class="brand-mark"><Sparkles :size="22" /></span> XinBot <span class="edition">COMPANION</span></RouterLink>
      <div class="header-right"><span class="connection"><i :class="{ online: state.connected }" />{{ state.connected ? '本地已连接' : '正在连接' }}</span><RouterLink to="/settings" class="model-link">{{ state.config.model_name || '配置模型' }}<ArrowUpRight :size="14" /></RouterLink></div>
    </header>
    <nav class="rail" aria-label="主导航">
      <RouterLink v-for="[path, icon, label] in links" :key="path" :to="path" :title="label" :aria-label="label"><component :is="icon" :size="21"/><span>{{ label === '模型与连接' ? '设置' : label === '桌宠外观' ? '外观' : label }}</span></RouterLink>
      <span class="rail-bottom">X / B</span>
    </nav>
    <aside class="companion">
      <div class="companion-heading"><span class="eyebrow">MY COMPANION</span><RouterLink to="/persona" title="更换角色" aria-label="更换角色"><UsersRound :size="19" /></RouterLink></div>
      <div class="character-heading"><h1>{{ character?.display_name || 'Xin' }}</h1><span class="mood"><i/>{{ state.busy ? '正在思考' : ({normal:'陪伴中', happy:'心情愉快', sad:'有些低落', angry:'闹脾气', sleepy:'困了'})[state.status.emotion] || '陪伴中' }}</span></div>
      <Live2DCanvas />
      <div class="character-footer"><span class="eyebrow">CHARACTER</span><p>{{ character?.character_card?.data?.personality || character?.traits?.join(' · ') || '你的专属陪伴' }}</p><RouterLink to="/persona">查看角色卡 <ArrowUpRight :size="15"/></RouterLink></div>
    </aside>
    <main class="content"><RouterView /></main>
    <div v-if="state.error || state.notice" class="toast" :class="{ danger: state.error }" role="status"><span>{{ state.error || state.notice }}</span><button class="icon-button" title="关闭通知" @click="state.error = ''; state.notice = ''"><X :size="16" /></button></div>
  </div>
</template>
