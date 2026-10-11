<script setup>
import { ref } from 'vue';
import api from '../api.js';
const command = ref(''), lines = ref(['XinBot 本地终端', '输入 help 查看可用指令。']);
async function run() { const value=command.value.trim(); command.value=''; if(!value)return; lines.value.push(`> ${value}`); try { if(value==='help')lines.value.push('help, status, clear, memory help'); else if(value==='clear')lines.value=[]; else if(value==='status')lines.value.push(JSON.stringify((await api.getStatus()).data,null,2)); else if(value.startsWith('memory '))lines.value.push(JSON.stringify((await api.memoryCommand(value.slice(7))).data,null,2)); else lines.value.push('未知指令。此终端不执行系统 Shell 命令。'); } catch(error) { lines.value.push(error.message); } }
</script>
<template><section class="terminal-view"><pre aria-live="polite">{{ lines.join('\n') }}</pre><form @submit.prevent="run"><span>&gt;</span><input v-model="command" aria-label="终端指令" autocomplete="off" placeholder="status"/></form></section></template>
<style scoped>.terminal-view{height:100%;min-height:350px;background:#18251e;color:#d9ede0;padding:16px;display:flex;flex-direction:column;font:13px/1.6 Consolas,monospace}.terminal-view pre{flex:1;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}.terminal-view form{display:flex;align-items:center;gap:8px}.terminal-view input{flex:1;background:transparent;border:0;color:inherit;font:inherit}</style>
