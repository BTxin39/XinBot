<script setup>
import { reactive, ref, watch } from 'vue';
import { Save, Plus, KeyRound, Trash2, Pencil, RefreshCw } from 'lucide-vue-next';
import { state, refresh, report } from '../state.js';
import api from '../api.js';

const tab = ref('connections');
const form = reactive({name:'', provider_type:'openai-compatible', base_url:'https://api.openai.com/v1', model:'', api_key:''});
const modelForm = reactive({name:'', provider:''});
const preferences = reactive({model_name:'',temperature:.7,max_memory_messages:20,web_port:3796,web_search_enabled:false});
const busy = ref(false), discovered = ref([]), keyProvider = ref(''), newKey = ref('');
watch(() => state.config, config => {
  for (const key of Object.keys(preferences)) if(config[key] !== undefined) preferences[key] = config[key];
}, {immediate:true});

async function run(action, notice='已保存') {
  busy.value=true;
  try { await action(); await refresh(); if(notice) state.notice=notice; }
  catch(error) { report(error); }
  finally { busy.value=false; }
}
function edit(provider) {
  Object.assign(form, {name:provider.name,provider_type:provider.provider_type,base_url:provider.base_url || 'https://api.openai.com/v1',model:state.models.find(item=>item.provider===provider.name)?.name || '',api_key:''});
  document.getElementById('connection-editor')?.scrollIntoView({behavior:'smooth'});
}
function changeType() {
  form.base_url=form.provider_type==='ollama' ? 'http://127.0.0.1:11434/v1' : 'https://api.openai.com/v1';
  form.api_key=''; discovered.value=[];
}
async function saveConnection() {
  await run(async()=>{ await api.saveConnection(form); form.api_key=''; });
}
async function savePreferences() {
  await run(async()=>{
    const model=state.models.find(item=>item.name===preferences.model_name);
    await api.updateConfig({...preferences,provider:model?.provider});
  }, Number(location.port || 80) !== preferences.web_port ? `设置已保存；重启后端后端口变为 ${preferences.web_port}` : '设置已生效');
}
async function discover() {
  busy.value=true;
  try { discovered.value=(await api.ollamaModels(form.base_url)).data; if(!discovered.value.length) state.notice='Ollama 尚未安装模型'; }
  catch(error) { report(error); }
  finally { busy.value=false; }
}
async function removeModel(model) { if(confirm(`从 XinBot 移除模型 ${model.name}？`)) await run(()=>api.deleteModel(model.name),'模型已移除'); }
async function removeProvider(provider) { if(confirm(`删除连接 ${provider.name} 及其密钥？`)) await run(()=>api.deleteProvider(provider.name),'连接已删除'); }
async function removeKey(provider) { if(confirm(`删除 ${provider.name} 的本机密钥？`)) await run(()=>api.deleteKey(provider.name),'密钥已删除'); }
async function saveKey() { await run(async()=>{ await api.updateKey(keyProvider.value,newKey.value); newKey.value=''; keyProvider.value=''; }); }
</script>

<template>
  <section class="page-view">
    <header class="view-header"><div><span class="eyebrow">PREFERENCES</span><h2>模型与设置</h2></div><KeyRound :size="22"/></header>
    <div class="view-tabs"><button :class="{active:tab==='connections'}" @click="tab='connections'">模型与连接</button><button :class="{active:tab==='config'}" @click="tab='config'">运行配置</button></div>
    <div class="page-body">
      <template v-if="tab==='connections'">
        <section class="form-section">
          <h3>模型库</h3>
          <div v-for="model in state.models" :key="model.name" class="management-row">
            <span><strong>{{ model.name }}</strong><small>{{ model.provider }}</small></span>
            <span v-if="model.name===state.config.model_name" class="badge">当前模型</span>
            <button class="icon-button" :title="`删除模型 ${model.name}`" :disabled="busy || state.busy || model.name===state.config.model_name" @click="removeModel(model)"><Trash2 :size="16"/></button>
          </div>
          <form class="inline-form" @submit.prevent="run(()=>api.registerModel(modelForm))">
            <select v-model="modelForm.provider" aria-label="模型所属连接" required><option value="" disabled>选择连接</option><option v-for="provider in state.providers" :key="provider.name" :value="provider.name">{{ provider.name }}</option></select>
            <input v-model="modelForm.name" aria-label="新增模型 ID" placeholder="模型 ID" required maxlength="200"/>
            <button class="icon-button primary" title="添加模型" :disabled="busy || state.busy"><Plus :size="18"/></button>
          </form>
        </section>
        <section class="form-section">
          <h3>服务连接</h3>
          <div v-for="provider in state.providers" :key="provider.name" class="management-row">
            <span><strong>{{ provider.name }}</strong><small>{{ provider.base_url || 'https://api.openai.com/v1' }}</small><span class="badge">{{ provider.provider_type==='ollama' ? 'Ollama' : provider.has_key ? '密钥已配置' : '未配置密钥' }}</span></span>
            <div class="actions compact">
              <button class="icon-button" :title="`编辑连接 ${provider.name}`" @click="edit(provider)"><Pencil :size="16"/></button>
              <button class="icon-button" :title="`更新密钥 ${provider.name}`" @click="keyProvider=provider.name;newKey='' "><KeyRound :size="16"/></button>
              <button class="icon-button" :title="`删除密钥 ${provider.name}`" :disabled="busy || !provider.has_key" @click="removeKey(provider)"><KeyRound :size="16"/><span class="minus-mark">−</span></button>
              <button class="icon-button" :title="`删除连接 ${provider.name}`" :disabled="busy || provider.name===state.config.provider || state.models.some(model=>model.provider===provider.name)" @click="removeProvider(provider)"><Trash2 :size="16"/></button>
            </div>
          </div>
          <form v-if="keyProvider" class="key-editor" @submit.prevent="saveKey">
            <label>{{ keyProvider }} · 新密钥<input v-model="newKey" type="password" required autocomplete="new-password" maxlength="4096"/></label>
            <div class="actions"><button class="button primary" :disabled="busy"><Save :size="15"/>更新密钥</button><button type="button" class="button" @click="keyProvider='';newKey=''">取消</button></div>
          </form>
        </section>
        <form id="connection-editor" class="form-section" @submit.prevent="saveConnection">
          <h3>添加 / 更新连接</h3>
          <label>接口类型<select v-model="form.provider_type" @change="changeType"><option value="openai-compatible">OpenAI Compatible</option><option value="ollama">Ollama · 本机</option></select></label>
          <div class="form-grid"><label>连接名称<input v-model="form.name" required pattern="[a-zA-Z0-9_-]+" maxlength="60" placeholder="my-provider"/></label><label>模型 ID<input v-model="form.model" required maxlength="200" placeholder="qwen3:8b"/></label></div>
          <label>API Base URL<input v-model="form.base_url" type="url" required/></label>
          <template v-if="form.provider_type==='ollama'">
            <button type="button" class="button" :disabled="busy" @click="discover"><RefreshCw :size="16"/>读取本机模型</button>
            <label v-if="discovered.length">已安装模型<select @change="form.model=$event.target.value"><option value="">选择模型</option><option v-for="model in discovered" :key="model.name" :value="model.name">{{ model.name }}</option></select></label>
          </template>
          <label v-else>API 密钥<input v-model="form.api_key" type="password" autocomplete="new-password" maxlength="4096" placeholder="留空保留已有密钥"/></label>
          <button class="button primary" :disabled="busy || state.busy"><Plus :size="16"/>保存连接</button>
        </form>
      </template>
      <form v-else class="form-section" @submit.prevent="savePreferences">
        <h3>对话</h3>
        <label>语言模型<select v-model="preferences.model_name"><option v-for="model in state.models" :key="model.name" :value="model.name">{{ model.name }} · {{ model.provider }}</option></select></label>
        <div class="form-grid"><label>温度 · {{ preferences.temperature }}<input v-model.number="preferences.temperature" type="range" min="0" max="2" step=".1"/></label><label>记忆消息数<input v-model.number="preferences.max_memory_messages" type="number" min="2" max="200" required/></label></div>
        <h3>本机服务</h3>
        <label>Web 端口（重启后生效）<input v-model.number="preferences.web_port" type="number" min="1024" max="65535" required/></label>
        <label class="checkbox-label"><input type="checkbox" v-model="preferences.web_search_enabled"/>启用网页搜索工具</label>
        <button class="button primary" :disabled="busy || state.busy"><Save :size="16"/>应用设置</button>
      </form>
    </div>
  </section>
</template>

<style scoped>
.inline-form{display:flex;gap:8px;margin-top:18px}.inline-form input{min-width:0;flex:1}.inline-form select{max-width:40%}.key-editor{padding-top:20px}.minus-mark{position:absolute;right:0;bottom:0;font-weight:700;color:#ac5145}.icon-button{position:relative}.compact{gap:2px}.checkbox-label{flex-direction:row;align-items:center}.form-section h3:not(:first-child){margin-top:25px}.management-row>span{min-width:0;flex:1}.management-row .badge{margin-top:6px}.form-section>button{margin-top:8px}
</style>
