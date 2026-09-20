<script setup>
import { onMounted, ref, nextTick } from 'vue';
import { Plus, Save, Download, Trash2, Terminal, ArrowUp, Play } from 'lucide-vue-next';
import api from '../api.js';
import { state, refresh, report } from '../state.js';

const memories=ref([]), selected=ref(null), name=ref(''), busy=ref(false), tab=ref('library');
const facts=ref(''), preferences=ref('{}'), command=ref(''), terminal=ref(null), output=ref(['XinBot Memory Console v0.1', 'help']);
const history=[];let historyIndex=0;
async function load(){memories.value=(await api.memories()).data;}
async function run(action){busy.value=true;try{await action();await load();}catch(error){report(error);}finally{busy.value=false;}}
async function select(memory){await run(async()=>{selected.value=(await api.memory(memory.name)).data;facts.value=selected.value.profile.key_facts?.join('\n') || '';preferences.value=JSON.stringify(selected.value.profile.user_preferences || {},null,2);});}
async function create(){await run(async()=>{await api.createMemory({name:name.value});name.value='';});}
async function save(){await run(async()=>{await api.updateMemory(selected.value.name,{description:selected.value.description,profile:{...selected.value.profile,key_facts:facts.value.split('\n').filter(Boolean),user_preferences:JSON.parse(preferences.value)}});state.notice='记忆已保存';});}
async function activate(memory){await run(async()=>{await api.activateMemory(memory.name);await refresh();state.notice='已切换记忆';});}
async function remove(memory){if(confirm(`永久删除记忆 ${memory.name}？`))await run(async()=>{await api.deleteMemory(memory.name);if(selected.value?.name===memory.name)selected.value=null;});}
async function clear(){if(confirm('清空此记忆的全部消息？长期记忆将保留。'))await run(async()=>{await api.clearMemory(selected.value.name);selected.value.messages=[];});}
function download(){const blob=new Blob([JSON.stringify(selected.value,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=`${selected.value.name}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function execute(){
  const text=command.value.trim();if(!text || busy.value)return;
  command.value='';history.push(text);historyIndex=history.length;output.value.push(`> ${text}`);busy.value=true;
  try{let response=(await api.memoryCommand(text)).data;if(response.confirmation_required){if(!confirm(response.output)){output.value.push('已取消');return;}response=(await api.memoryCommand(text,true)).data;}output.value.push(response.output);await load();await refresh();}
  catch(error){output.value.push(`Error: ${error.message}`);}
  finally{busy.value=false;output.value=output.value.slice(-100);await nextTick();terminal.value?.scrollTo(0,terminal.value.scrollHeight);}
}
function navigate(direction){historyIndex=Math.max(0,Math.min(history.length,historyIndex+direction));command.value=history[historyIndex] || '';}
onMounted(()=>run(load));
</script>

<template>
  <section class="page-view">
    <header class="view-header"><div><span class="eyebrow">MEMORY</span><h2>记忆管理</h2></div><Terminal :size="22"/></header>
    <div class="view-tabs"><button :class="{active:tab==='library'}" @click="tab='library'">记忆库</button><button :class="{active:tab==='terminal'}" @click="tab='terminal'">交互控制台</button></div>
    <div class="page-body">
      <template v-if="tab==='library'">
        <form class="memory-create" @submit.prevent="create"><input v-model="name" aria-label="新记忆名称" placeholder="新记忆名称" required maxlength="100"/><button class="icon-button primary" title="创建记忆" :disabled="busy"><Plus :size="18"/></button></form>
        <div v-for="memory in memories" :key="memory.name" class="management-row">
          <button class="memory-select" @click="select(memory)"><strong>{{ memory.name }}</strong><small>{{ memory.count }} 条消息 · {{ memory.description || '未添加描述' }}</small></button>
          <span v-if="memory.active" class="badge">当前</span>
          <button class="icon-button" :title="`切换记忆 ${memory.name}`" :disabled="memory.active || busy || state.busy" @click="activate(memory)"><Play :size="16"/></button>
          <button class="icon-button" :title="`删除记忆 ${memory.name}`" :disabled="memory.active || busy" @click="remove(memory)"><Trash2 :size="16"/></button>
        </div>
        <form v-if="selected" class="editor-form memory-editor" @submit.prevent="save">
          <div class="section-label"><h3>{{ selected.name }}</h3><button type="button" class="icon-button" title="导出记忆" @click="download"><Download :size="17"/></button></div>
          <label>描述<input v-model="selected.description" maxlength="2000"/></label>
          <div class="form-grid"><label>用户称呼<input v-model="selected.profile.user_name" maxlength="200"/></label><label>关系阶段<select v-model="selected.profile.relationship_stage"><option value="new">初识</option><option value="familiar">熟悉</option><option value="close">亲近</option></select></label></div>
          <label>重要事实<textarea v-model="facts" rows="4"/></label>
          <label>用户偏好 JSON<textarea v-model="preferences" rows="4" spellcheck="false"/></label>
          <label>长期摘要<textarea v-model="selected.profile.conversation_summary" rows="4" maxlength="10000"/></label>
          <button class="button primary" :disabled="busy || state.busy"><Save :size="16"/>保存长期记忆</button>
          <div class="section-label"><h3>消息记录</h3><button type="button" class="icon-button" title="清空消息记录" :disabled="busy || state.busy" @click="clear"><Trash2 :size="17"/></button></div>
          <article v-for="(message,index) in selected.messages" :key="index" class="memory-message"><small>{{ message.role }}</small><p>{{ message.content }}</p></article>
          <div v-if="!selected.messages.length" class="empty">暂无消息</div>
        </form>
      </template>
      <div v-else class="memory-terminal">
        <div class="terminal-title"><Terminal :size="15"/>MEMORY / LOCAL</div>
        <div class="terminal-output" ref="terminal" role="log"><pre v-for="(line,index) in output" :key="index">{{ line }}</pre></div>
        <form class="terminal-input" @submit.prevent="execute"><span>&gt;</span><input v-model="command" aria-label="记忆终端命令" autocomplete="off" spellcheck="false" :disabled="busy" @keydown.up.prevent="navigate(-1)" @keydown.down.prevent="navigate(1)"/><button class="icon-button" title="执行命令" :disabled="busy"><ArrowUp :size="17"/></button></form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.memory-create{display:flex;gap:10px;margin-bottom:15px}.memory-create input{flex:1;min-width:0}.memory-select{text-align:left;flex:1;min-width:0;background:none;border:0}.memory-editor{margin-top:30px}.memory-editor .section-label{margin-top:24px;align-items:center}.memory-message{border-bottom:1px solid #e6ece7;padding:15px 0}.memory-message p{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;margin-top:7px}.memory-terminal{height:100%;min-height:320px;display:flex;flex-direction:column;background:#202722;border:1px solid #354138;border-radius:6px;color:#c9e1cf;overflow:hidden}.terminal-title{display:flex;align-items:center;gap:8px;padding:14px 17px;font-size:11px;border-bottom:1px solid #354138;color:#91ac98}.terminal-output{flex:1;overflow:auto;padding:16px}.terminal-output pre{font:12px/1.8 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:12px}.terminal-input{display:flex;align-items:center;padding:8px 14px;gap:10px;border-top:1px solid #354138}.terminal-input input{background:none;border:0;box-shadow:none;color:#d3e8d8;flex:1;min-width:0;font-family:Consolas,monospace}.terminal-input .icon-button{color:#c9e1cf}
</style>
