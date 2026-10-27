<script setup>
import { onMounted, onUnmounted, reactive, ref, watch, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Sparkles, UsersRound, SlidersHorizontal, Library, Box, X, Brain, Image, Menu, Wrench, UserRound, Terminal, Info, Palette, Calculator } from 'lucide-vue-next';
import { state, character, refresh, report, activate } from './state.js';
import Live2DCanvas from './components/Live2DCanvas.vue';
import PetOnlyView from './views/PetOnlyView.vue';
import ThemeView from './views/ThemeView.vue';
import HomeView from './views/HomeView.vue';
import CalculatorView from './views/CalculatorView.vue';
import TerminalView from './views/TerminalView.vue';
import api from './api.js';
import { t } from './i18n.js';
import './style.css';
import './management.css';
import './workspace.css';
// theme.css 必须**最后**导入：它用变量覆盖前面样式表的表面色，
// 放前面会被 workspace.css 的同名规则盖掉（实测 companion 底色没跟着主题变）。
import './theme.css';
const route = useRoute(), router = useRouter();
/**
 * 桌宠模式：`/#/pet` 走完全独立的极简布局。
 * 它不渲染顶栏/侧栏/面板，且 App 的 refresh 轮询也不必重复跑
 * （PetOnlyView 自己维护情绪轮询）。
 */
const isPetMode = computed(() => route.path === '/pet');
const openMenu = ref(''), panel = reactive({ x: 0, y: 0 }), profile = reactive(JSON.parse(localStorage.getItem('xinbot.profile') || '{"username":"","email":"","bio":"","avatar":""}'));
const menus = {
  tools: [['/ascii', Image, 'menu.ascii'], ['/calculator', Calculator, 'menu.calculator']],
  manage: [['/persona', UsersRound, 'menu.persona'], ['/memory', Brain, 'menu.memory'], ['/knowledge', Library, 'menu.knowledge'], ['/appearance', Box, 'menu.appearance']],
  account: [['/profile', UserRound, 'menu.profile'], ['/settings', SlidersHorizontal, 'menu.settings'], ['/terminal', Terminal, 'menu.terminal'], ['/about', Info, 'menu.about'], ['/theme', Palette, 'menu.theme']]
};
const titles = { '/ascii':'menu.ascii', '/calculator':'menu.calculator', '/persona':'menu.persona', '/memory':'menu.memory', '/knowledge':'menu.knowledge', '/appearance':'menu.appearance', '/profile':'menu.profile', '/settings':'menu.settings', '/terminal':'menu.terminal', '/about':'menu.about', '/theme':'menu.theme' };
let timer, drag;
watch(() => route.path, () => { openMenu.value = ''; panel.x = 0; panel.y = 0; });
watch(profile, value => localStorage.setItem('xinbot.profile', JSON.stringify(value)), { deep: true });
onMounted(async () => {
  // 桌宠窗口不需要工作台的数据轮询，交给 PetOnlyView
  if (isPetMode.value) return;
  try { await refresh(); } catch (error) { report(error); }
  timer = setInterval(async () => { try { state.status = (await api.getStatus()).data; state.connected = true; } catch { state.connected = false; } }, 5000);
});
onUnmounted(() => clearInterval(timer));
function startDrag(event) { if (event.target.closest('button')) return; drag = { x:event.clientX, y:event.clientY, left:panel.x, top:panel.y }; event.currentTarget.setPointerCapture(event.pointerId); }
function moveDrag(event) { if (!drag) return; panel.x = Math.max(-window.innerWidth * .5, Math.min(window.innerWidth * .5, drag.left + event.clientX - drag.x)); panel.y = Math.max(-window.innerHeight * .5, Math.min(window.innerHeight * .5, drag.top + event.clientY - drag.y)); }
function closePanel() { router.push('/'); }
function uploadAvatar(event) { const file = event.target.files[0]; if (!file) return; if (file.size > 300000 || !file.type.startsWith('image/')) return report(new Error('头像须为 300 KB 以内的图片')); const reader = new FileReader(); reader.onload = () => { profile.avatar = reader.result; }; reader.readAsDataURL(file); }
async function switchCharacter(event) { try { await activate(event.target.value); } catch (error) { report(error); } }
</script>
<template>
  <!-- 桌宠模式：只有角色，透明背景 -->
  <PetOnlyView v-if="isPetMode" />
  <div v-else class="workspace new-workspace">
    <header class="app-header"><RouterLink to="/" class="brand"><span class="brand-mark"><Sparkles :size="20"/></span> XinBot</RouterLink><div class="header-right"><span class="connection"><i :class="{ online:state.connected }"/>{{ state.connected ? t('header.online') : t('header.offline') }}</span><div v-for="(entries,key) in menus" :key="key" class="menu-wrap"><button class="icon-button menu-trigger" :title="t(`menu.${key}`)" :aria-label="t(`menu.${key}`)" @click="openMenu=openMenu===key?'':key"><component :is="{tools:Wrench,manage:Menu,account:UserRound}[key]" :size="20"/></button><div v-if="openMenu===key" class="menu-popover"><RouterLink v-for="[path,icon,label] in entries" :key="path" :to="path"><component :is="icon" :size="16"/>{{ t(label) }}</RouterLink></div></div></div></header>
    <aside class="companion"><div class="character-heading"><h1>{{ character?.display_name || 'Xin' }}</h1><span class="mood"><i/>{{ state.busy ? t('header.busy') : t('header.companion') }}</span></div><Live2DCanvas/><div class="character-selector"><UsersRound :size="18"/><select aria-label="切换角色" :value="state.config.persona_name" :disabled="state.busy" @change="switchCharacter"><option v-for="item in state.personas" :key="item.name" :value="item.name">{{ item.display_name }}</option></select></div></aside>
    <main class="content"><HomeView/></main>
    <div v-if="route.path !== '/'" class="panel-backdrop" @click="closePanel"/><section v-if="route.path !== '/'" class="floating-panel" :style="{transform:`translate(${panel.x}px,${panel.y}px)`}"><header class="floating-title" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="drag=null" @pointercancel="drag=null"><strong>{{ t(titles[route.path] || 'menu.tools') }}</strong><button class="icon-button" title="关闭" @click="closePanel"><X :size="18"/></button></header><div class="floating-body"><CalculatorView v-if="route.path==='/calculator'"/><TerminalView v-else-if="route.path==='/terminal'"/><section v-else-if="route.path==='/profile'" class="page-view"><div class="page-body profile-form"><label>头像<input type="file" accept="image/*" @change="uploadAvatar"/></label><img v-if="profile.avatar" :src="profile.avatar" alt="档案头像"/><label>用户名<input v-model="profile.username" maxlength="80"/></label><label>邮箱<input v-model="profile.email" type="email" maxlength="200"/></label><label>个人简介<textarea v-model="profile.bio" maxlength="1000" rows="5"/></label><small>此档案仅保存在当前浏览器。</small></div></section><section v-else-if="route.path==='/about'" class="page-view"><div class="page-body"><h2>XinBot</h2><p>本地桌宠与对话工作台</p><p>后端：{{ state.connected ? '运行中' : '未连接' }}</p><p>模型：{{ state.status.model_name || '未配置' }}</p></div></section><ThemeView v-else-if="route.path==='/theme'"/><RouterView v-else/></div></section>
    <div v-if="state.error || state.notice" class="toast" :class="{ danger:state.error }" role="status"><span>{{ state.error || state.notice }}</span><button class="icon-button" title="关闭通知" @click="state.error='';state.notice='' "><X :size="16"/></button></div>
  </div>
</template>
