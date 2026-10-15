<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue';
import { Send, Trash2, MessageCircle, Paperclip, X, Brain } from 'lucide-vue-next';
import { state, character, refresh, loadHistory, report } from '../state.js';
import api from '../api.js';
import MessageBubble from '../components/MessageBubble.vue';
const draft = ref(''), scroll = ref(null), attachment = ref(null), fileInput = ref(null);
const modelMenu = ref(false), thinking = ref(false), strength = ref(2), selectedModel = ref('');
let socket, timeout;
watch(() => state.config.model_name, value => { selectedModel.value = value || ''; }, { immediate:true });
watch(() => state.status.ready, async ready => { if (ready && !state.busy) try { await loadHistory(); } catch(error) { report(error); } }, { immediate:true });
watch(() => state.messages.map(item => item.content).join(''), async () => { await nextTick(); scroll.value?.scrollTo({top:scroll.value.scrollHeight, behavior:'smooth'}); });
function finish() { clearTimeout(timeout); state.busy = false; socket?.close(); socket = null; }
async function chooseFile(event) { const file=event.target.files[0]; event.target.value=''; if(!file)return; if(file.size>2*1024*1024)return report(new Error('附件不能超过 2 MB')); try { if(file.type.startsWith('image/') && ['image/png','image/jpeg','image/webp'].includes(file.type)) { const reader=new FileReader(); reader.onload=()=>{ attachment.value={name:file.name,image:reader.result}; }; reader.readAsDataURL(file); } else if(file.type==='application/pdf') { const result=await api.extractAttachment(file); attachment.value={name:file.name,text:result.data.text}; } else report(new Error('仅支持 PNG、JPEG、WebP 图片或文本型 PDF')); } catch(error) { report(error); } }
async function switchModel() { const model=state.models.find(item=>item.name===selectedModel.value); if(!model || state.busy)return; try { await api.updateConfig({model_name:model.name,provider:model.provider}); await refresh(); modelMenu.value=false; } catch(error) { report(error); } }
function send() {
  if ((!draft.value.trim() && !attachment.value) || state.busy || !state.status.ready) return;
  const text = draft.value.trim() || '请描述这个附件。';
  const message = attachment.value?.text ? `${text}\n\n[附件：${attachment.value.name}]\n${attachment.value.text}`.slice(0,32000) : text;
  const image = attachment.value?.image || null;
  state.messages.push({role:'user',content:`${text}${attachment.value ? `\n[附件：${attachment.value.name}]` : ''}`});
  draft.value=''; attachment.value=null; state.busy=true;
  const index=state.messages.push({role:'assistant',content:''})-1;
  socket=api.createChatWS();
  socket.onopen=()=>socket.send(JSON.stringify({message,thinking:thinking.value,thinking_strength:strength.value,image}));
  socket.onmessage=event=>{try{const data=JSON.parse(event.data);if(data.error)throw new Error(data.error);if(data.chunk)state.messages[index].content+=data.chunk;if(data.done)finish();}catch(error){report(error);finish();}};
  socket.onerror=()=>{report(new Error('聊天连接失败，请检查模型连接'));finish();};
  socket.onclose=()=>{if(state.busy){report(new Error('连接已中断'));finish();}};
  timeout=setTimeout(()=>{report(new Error('回复超时，请重试'));finish();},180000);
}
async function clear() { if(!confirm('清空当前角色的聊天记录？'))return;try{await api.clearHistory();await loadHistory();}catch(error){report(error);} }
onUnmounted(finish);
</script>
<template><section class="chat-view"><header class="view-header"><div><span class="eyebrow">CONVERSATION</span><h2>和 {{ character?.display_name || 'Xin' }} 聊聊</h2></div><button class="icon-button" title="清空对话" :disabled="state.busy || !state.status.ready" @click="clear"><Trash2 :size="18"/></button></header><div class="messages" ref="scroll"><div v-if="!state.messages.length" class="chat-empty"><MessageCircle :size="32"/><h3>{{ state.status.ready ? '今天，想聊些什么？' : '连接你的第一个模型' }}</h3><p>{{ character?.character_card?.data?.first_mes || '从一句问候开始。' }}</p><RouterLink v-if="!state.status.ready" to="/settings" class="button primary">模型与连接</RouterLink></div><MessageBubble v-for="(message,index) in state.messages" :key="index" :message="message"/><div v-if="state.busy" class="thinking">正在思考<span>...</span></div></div><form class="composer" @submit.prevent="send"><textarea v-model="draft" aria-label="聊天消息" placeholder="说点什么…" rows="3" maxlength="32000" @keydown.enter.exact.prevent="send"/><div v-if="attachment" class="attachment-chip">{{ attachment.name }}<button type="button" class="icon-button" title="移除附件" @click="attachment=null"><X :size="14"/></button></div><div class="composer-bottom"><div class="composer-tools"><div class="model-picker"><button type="button" class="button" @click="modelMenu=!modelMenu">{{ state.config.model_name || '选择模型' }}</button><div v-if="modelMenu" class="model-popover"><label>聊天模型<select v-model="selectedModel" @change="switchModel"><option v-for="item in state.models" :key="item.name" :value="item.name">{{ item.name }}</option></select></label><label class="thinking-toggle"><input type="checkbox" v-model="thinking"/>深度思考 <Brain :size="15"/></label><label v-if="thinking">思考强度 <input type="range" v-model.number="strength" min="1" max="3" step="1"/>{{ ['','简要','标准','深入'][strength] }}</label><small>思考强度为回答指令，具体能力取决于模型。</small></div></div><button type="button" class="icon-button" title="添加图片或 PDF" @click="fileInput.click()"><Paperclip :size="18"/></button><input hidden ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp,application/pdf" @change="chooseFile"/></div><button class="primary icon-button" type="submit" title="发送" :disabled="state.busy || (!draft.trim() && !attachment) || !state.status.ready"><Send :size="18"/></button></div></form></section></template>
<style scoped>.composer-tools{display:flex;align-items:center;gap:6px}.model-picker{position:relative}.model-picker>.button{max-width:180px;overflow:hidden;text-overflow:ellipsis}.model-popover{position:absolute;bottom:42px;left:0;width:min(280px,80vw);background:white;padding:16px;border:1px solid #dce5df;box-shadow:0 8px 28px #14251a22;border-radius:6px;z-index:3;color:#334839;font-size:12px}.model-popover label{display:flex;align-items:center;gap:8px;margin-bottom:12px}.model-popover select{min-width:0;flex:1}.model-popover input[type=range]{flex:1}.model-popover .thinking-toggle input{width:auto}.attachment-chip{display:inline-flex;align-items:center;margin-left:14px;background:#eff4ef;padding:2px 6px;border-radius:4px;font-size:11px}</style>
