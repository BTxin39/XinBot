<script setup>
import { ref, onMounted } from 'vue';
import { Upload, Search, Trash2, Link } from 'lucide-vue-next';
import api from '../api.js';
import { report, state } from '../state.js';
const sources=ref([]),results=ref([]),query=ref(''),url=ref(''),input=ref(null),busy=ref(false);
async function load(){ sources.value=(await api.getRagSources()).data; }
async function run(action){ busy.value=true; try { await action(); } catch(error) { report(error); } finally { busy.value=false; } }
async function upload(event){ const file=event.target.files[0]; if(!file)return; await run(async()=>{await api.ingestFile(file);await load();state.notice='文档已导入';});event.target.value=''; }
async function ingest(){await run(async()=>{await api.ingestUrl(url.value);url.value='';await load();});}
async function search(){await run(async()=>{results.value=(await api.searchRag(query.value)).data;});}
async function remove(source){if(confirm('删除此知识源？'))await run(async()=>{await api.deleteSource(source);await load();});}
async function clear(){if(confirm('清空全部知识库？'))await run(async()=>{await api.clearRag();await load();results.value=[];});}
onMounted(()=>run(load));
</script>
<template><section class="page-view"><header class="view-header"><div><span class="eyebrow">KNOWLEDGE</span><h2>知识库</h2></div><button class="button" :disabled="busy" @click="input.click()"><Upload :size="16"/>导入文档</button><input type="file" hidden ref="input" @change="upload"/></header><div class="page-body"><form class="knowledge-row" @submit.prevent="ingest"><input type="url" v-model="url" aria-label="网页地址" placeholder="https://…" required/><button class="icon-button" title="导入网页" :disabled="busy"><Link :size="18"/></button></form><form class="knowledge-row" @submit.prevent="search"><input v-model="query" aria-label="搜索知识库" placeholder="搜索知识库…" required/><button class="icon-button" title="搜索" :disabled="busy"><Search :size="18"/></button></form><div v-if="busy" class="empty">处理中…</div><article v-for="(item,index) in results" :key="index" class="search-result"><p>{{ item.text }}</p><small>{{ item.source }}</small></article><div class="section-label">知识源 · {{ sources.length }}<button class="icon-button" title="清空知识库" :disabled="busy || !sources.length" @click="clear"><Trash2 :size="16"/></button></div><div v-for="item in sources" :key="item.source" class="source-row"><span>{{ item.source }}</span><small>{{ item.chunks }} 段</small><button class="icon-button" title="删除知识源" :disabled="busy" @click="remove(item.source)"><Trash2 :size="16"/></button></div><div v-if="!sources.length && !busy" class="empty">暂无知识源</div></div></section></template>
<style scoped>.knowledge-row{display:flex;gap:10px;align-items:center;margin-bottom:18px}.knowledge-row input{flex:1;min-width:0}.source-row{display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid #edf1ed}.source-row span{flex:1;overflow-wrap:anywhere;font-size:12px}.source-row small{white-space:nowrap}.search-result{font-size:13px;line-height:1.8;border-bottom:1px solid #edf1ed;padding:15px 0;overflow-wrap:anywhere}.section-label{margin-top:25px;align-items:center}</style>
