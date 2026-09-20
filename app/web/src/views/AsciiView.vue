<script setup>
import { ref, onUnmounted } from 'vue';
import { Upload, Download, Copy, WandSparkles } from 'lucide-vue-next';
import api from '../api.js';
import { report, state } from '../state.js';
const file=ref(null), preview=ref(''), width=ref(60), mode=ref('braille'), output=ref(''), busy=ref(false), input=ref(null);
function choose(event){const selected=event.target.files[0];if(!selected)return;if(selected.size>10*1024*1024){report(new Error('图片不能超过 10 MB'));return;}if(preview.value)URL.revokeObjectURL(preview.value);file.value=selected;preview.value=URL.createObjectURL(selected);output.value='';}
async function convert(){if(!file.value)return;busy.value=true;try{const form=new FormData();form.append('file',file.value);form.append('width',width.value);form.append('mode',mode.value);output.value=(await api.ascii(form)).data.text;}catch(error){report(error);}finally{busy.value=false;}}
async function copy(){try{await navigator.clipboard.writeText(output.value);state.notice='字符画已复制';}catch(error){report(error);}}
function download(){const url=URL.createObjectURL(new Blob([output.value],{type:'text/plain;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='xinbot-art.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
onUnmounted(()=>{if(preview.value)URL.revokeObjectURL(preview.value);});
</script>
<template>
  <section class="page-view">
    <header class="view-header"><div><span class="eyebrow">IMAGE TO TEXT</span><h2>图片转字符画</h2></div><button class="button" @click="input.click()"><Upload :size="16"/>选择图片</button><input ref="input" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="choose"/></header>
    <div class="page-body">
      <div class="ascii-source"><img v-if="preview" :src="preview" alt="待转换图片"/><Upload v-else :size="32"/></div>
      <form class="form-section" @submit.prevent="convert">
        <div class="form-grid"><label>字符集<select v-model="mode"><option value="braille">Braille 点阵</option><option value="ascii">ASCII 文本</option></select></label><label>宽度 · {{ width }} 字符<input type="range" v-model.number="width" min="10" max="160" step="2"/></label></div>
        <button class="button primary" :disabled="!file || busy"><WandSparkles :size="16"/>{{ busy ? '转换中' : '转换' }}</button>
      </form>
      <template v-if="output"><div class="section-label">转换结果<div class="actions"><button class="icon-button" title="复制字符画" @click="copy"><Copy :size="17"/></button><button class="icon-button" title="下载字符画" @click="download"><Download :size="17"/></button></div></div><pre class="ascii-output">{{ output }}</pre></template>
    </div>
  </section>
</template>
<style scoped>.ascii-source{height:200px;background:#f0f4f1;display:grid;place-items:center;margin-bottom:25px;color:#91a596}.ascii-source img{height:100%;max-width:100%;object-fit:contain}.form-section label{display:flex;flex-direction:column;gap:10px}.ascii-output{overflow:auto;padding:18px;background:#222923;color:#d9e7dc;border-radius:5px;font:11px/1.15 Consolas,'Segoe UI Symbol',monospace;max-height:500px}.section-label{align-items:center}</style>
