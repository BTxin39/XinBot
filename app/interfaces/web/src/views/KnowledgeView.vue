<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { Upload, Search, Trash2, Link, Network, List } from 'lucide-vue-next';
import api from '../api.js';
import { report, state } from '../state.js';
const route = useRoute();
const sources = ref([]), results = ref([]), graph = ref({ sources: [], personas: [] });
const query = ref(''), url = ref(''), tag = ref(route.query.tag || 'default');
const input = ref(null), busy = ref(false), view = ref('list');
const graphLayout = computed(() => {
  const personas = graph.value.personas.map((item, index) => ({ ...item, x: 95, y: 50 + index * 74 }));
  const tags = [...new Set([...graph.value.sources.map(item => item.tag), ...personas.flatMap(item => item.tags)])].map((name, index) => ({ name, x: 370, y: 50 + index * 74 }));
  const sources = graph.value.sources.map((item, index) => ({ ...item, x: 650, y: 50 + index * 74 }));
  const links = [
    ...personas.flatMap(persona => tags.filter(item => persona.tags.includes(item.name)).map(item => ({ x1: persona.x + 78, y1: persona.y, x2: item.x - 70, y2: item.y }))),
    ...sources.flatMap(source => tags.filter(item => source.tag === item.name).map(item => ({ x1: item.x + 70, y1: item.y, x2: source.x - 78, y2: source.y }))),
  ];
  return { personas, tags, sources, links, height: Math.max(200, 100 + 74 * Math.max(personas.length, tags.length, sources.length)) };
});
async function load() { sources.value = (await api.getRagSources()).data; graph.value = (await api.ragGraph()).data; }
async function run(action) { busy.value = true; try { await action(); } catch (error) { report(error); } finally { busy.value = false; } }
async function upload(event) { const file = event.target.files[0]; if (!file) return; await run(async () => { await api.ingestFile(file, tag.value); await load(); state.notice = '文档已导入'; }); event.target.value = ''; }
async function ingest() { await run(async () => { await api.ingestUrl(url.value, tag.value); url.value = ''; await load(); }); }
async function search() { await run(async () => { results.value = (await api.searchRag(query.value, tag.value ? [tag.value] : undefined)).data; }); }
async function rename(item) { const next = prompt('知识库 TAG', item.tag); if (!next?.trim() || next === item.tag) return; await run(async () => { await api.updateSourceTag(item.source, next.trim()); await load(); }); }
async function remove(source) { if (confirm('删除此知识源？')) await run(async () => { await api.deleteSource(source); await load(); }); }
async function clear() { if (confirm('清空全部知识库？')) await run(async () => { await api.clearRag(); await load(); results.value = []; }); }
onMounted(() => run(load));
</script>
<template>
  <section class="page-view"><header class="view-header"><div><span class="eyebrow">KNOWLEDGE</span><h2>知识库</h2></div><div class="actions"><button class="icon-button" title="列表" @click="view='list'"><List :size="18"/></button><button class="icon-button" title="关系图" @click="view='graph'"><Network :size="18"/></button><button class="button" :disabled="busy" @click="input.click()"><Upload :size="16"/>导入</button><input type="file" hidden ref="input" @change="upload"/></div></header>
  <div class="page-body"><label class="knowledge-tag">当前 TAG <input v-model.trim="tag" maxlength="64" placeholder="default"/></label><form class="knowledge-row" @submit.prevent="ingest"><input type="url" v-model="url" aria-label="网页地址" placeholder="https://…" required/><button class="icon-button" title="导入网页" :disabled="busy || !tag"><Link :size="18"/></button></form><form class="knowledge-row" @submit.prevent="search"><input v-model="query" aria-label="搜索知识库" placeholder="搜索当前 TAG…" required/><button class="icon-button" title="搜索" :disabled="busy"><Search :size="18"/></button></form><div v-if="busy" class="empty">处理中…</div><article v-for="(item,index) in results" :key="index" class="search-result"><p>{{ item.text }}</p><small>{{ item.tag }} · {{ item.source }}</small></article>
  <template v-if="view==='list'"><div class="section-label">知识源 · {{ sources.length }}<button class="icon-button" title="清空知识库" :disabled="busy || !sources.length" @click="clear"><Trash2 :size="16"/></button></div><div v-for="item in sources" :key="item.source" class="source-row"><span>{{ item.source }}</span><button class="badge" title="修改 TAG" @click="rename(item)">{{ item.tag }}</button><small>{{ item.chunks }} 段</small><button class="icon-button" title="删除知识源" :disabled="busy" @click="remove(item.source)"><Trash2 :size="16"/></button></div><div v-if="!sources.length && !busy" class="empty">暂无知识源</div></template>
  <div v-else class="rag-graph"><div class="graph-legend"><span>角色</span><span>TAG</span><span>知识源</span></div><svg :viewBox="`0 0 780 ${graphLayout.height}`" role="img" aria-label="角色、TAG 与知识源关系图"><line v-for="(link,index) in graphLayout.links" :key="index" v-bind="link" stroke="#8caf96" stroke-width="2"/><g v-for="item in graphLayout.personas" :key="item.name"><rect :x="item.x-78" :y="item.y-22" width="156" height="44" rx="5" fill="#e5f1e8"/><text :x="item.x" :y="item.y+5" text-anchor="middle">{{ item.display_name.slice(0,16) }}</text></g><g v-for="item in graphLayout.tags" :key="item.name" tabindex="0" @click="tag=item.name;view='list'" @keydown.enter="tag=item.name;view='list'"><rect :x="item.x-70" :y="item.y-22" width="140" height="44" rx="5" fill="#fff0d8"/><text :x="item.x" :y="item.y+5" text-anchor="middle">{{ item.name.slice(0,15) }}</text></g><g v-for="item in graphLayout.sources" :key="item.source"><rect :x="item.x-78" :y="item.y-22" width="156" height="44" rx="5" fill="#e7edf1"/><text :x="item.x" :y="item.y+5" text-anchor="middle">{{ item.source.split(/[\\/]/).pop().slice(0,15) }}</text></g></svg></div></div></section>
</template>
<style scoped>.knowledge-row{display:flex;gap:10px;align-items:center;margin-bottom:14px}.knowledge-row input{flex:1;min-width:0}.knowledge-tag{display:flex;align-items:center;gap:12px;margin-bottom:16px;font-size:12px}.knowledge-tag input{width:180px}.source-row{display:flex;align-items:center;gap:12px;padding:14px 0;border-bottom:1px solid #edf1ed}.source-row span{flex:1;overflow-wrap:anywhere;font-size:12px}.source-row small{white-space:nowrap}.source-row .badge{border:0;cursor:pointer}.search-result{font-size:13px;line-height:1.8;border-bottom:1px solid #edf1ed;padding:15px 0;overflow-wrap:anywhere}.section-label{margin-top:25px;align-items:center}.rag-graph{min-width:520px;overflow-x:auto}.rag-graph svg{width:100%;min-width:780px;height:auto;max-height:600px}.rag-graph text{font-size:13px;fill:#2e4336}.rag-graph g[tabindex]{cursor:pointer}.graph-legend{display:flex;justify-content:space-between;padding:0 45px;font-size:12px;color:#7e8d81}</style>
