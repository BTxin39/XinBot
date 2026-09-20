<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue';
import { Send, Trash2, MessageCircle } from 'lucide-vue-next';
import { state, character, activate, loadHistory, report } from '../state.js';
import api from '../api.js';
import MessageBubble from '../components/MessageBubble.vue';
const draft = ref(''), scroll = ref(null);
let socket, timeout;
watch(() => state.status.ready, async ready => { if (ready && !state.busy) try { await loadHistory(); } catch(error) { report(error); } }, { immediate:true });
watch(() => state.messages.map(item => item.content).join(''), async () => { await nextTick(); scroll.value?.scrollTo({top:scroll.value.scrollHeight, behavior:'smooth'}); });
function finish() { clearTimeout(timeout); state.busy = false; socket?.close(); socket = null; }
function send() {
  if (!draft.value.trim() || state.busy || !state.status.ready) return;
  const text = draft.value.trim(); draft.value = ''; state.busy = true;
  state.messages.push({role:'user', content:text});
  const index = state.messages.push({role:'assistant', content:''}) - 1;
  socket = api.createChatWS();
  socket.onopen = () => socket.send(JSON.stringify({message:text}));
  socket.onmessage = event => {
    try { const data = JSON.parse(event.data); if (data.error) throw new Error(data.error); if (data.chunk) state.messages[index].content += data.chunk; if (data.done) finish(); }
    catch(error) { report(error); finish(); }
  };
  socket.onerror = () => { report(new Error('聊天连接失败，请检查模型连接')); finish(); };
  socket.onclose = () => { if (state.busy) { report(new Error('连接已中断')); finish(); } };
  timeout = setTimeout(() => { report(new Error('回复超时，请重试')); finish(); }, 180000);
}
async function clear() { if (!confirm('清空当前角色的聊天记录？')) return; try { await api.clearHistory(); await loadHistory(); } catch(error) { report(error); } }
async function switchCharacter(event) { try { await activate(event.target.value); } catch(error) { report(error); } }
onUnmounted(finish);
</script>
<template><section class="chat-view"><header class="view-header"><div><span class="eyebrow">CONVERSATION</span><h2>和 {{ character?.display_name || 'Xin' }} 聊聊</h2></div><div class="actions"><select aria-label="切换角色" :value="state.config.persona_name" :disabled="state.busy" @change="switchCharacter"><option v-for="item in state.personas" :value="item.name" :key="item.name">{{ item.display_name }}</option></select><button class="icon-button" title="清空对话" :disabled="state.busy || !state.status.ready" @click="clear"><Trash2 :size="18"/></button></div></header><div class="messages" ref="scroll"><div v-if="!state.messages.length" class="chat-empty"><MessageCircle :size="32"/><h3>{{ state.status.ready ? '今天，想聊些什么？' : '连接你的第一个模型' }}</h3><p>{{ character?.character_card?.data?.first_mes || '从一句问候开始。' }}</p><RouterLink v-if="!state.status.ready" to="/settings" class="button primary">模型与连接</RouterLink></div><MessageBubble v-for="(message,index) in state.messages" :key="index" :message="message"/><div v-if="state.busy" class="thinking">正在思考<span>...</span></div></div><form class="composer" @submit.prevent="send"><textarea v-model="draft" aria-label="聊天消息" placeholder="说点什么…" rows="3" maxlength="32000" @keydown.enter.exact.prevent="send"/><div class="composer-bottom"><span>{{ state.config.model_name || '尚未配置模型' }}</span><button class="primary icon-button" type="submit" title="发送" :disabled="state.busy || !draft.trim() || !state.status.ready"><Send :size="18"/></button></div></form></section></template>
