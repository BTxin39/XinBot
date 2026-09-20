<script setup>
import { ref } from 'vue';
import { Upload, Check, Box } from 'lucide-vue-next';
import { state, pet, character, refresh, report } from '../state.js';
import api from '../api.js';
const busy = ref(false), input = ref(null);
const preview = item => state.previews[item.id];
async function select(item) { try { if (character.value) { const {builtin,avatar,...body}=character.value; await api.updatePersona(body.name,{...body,pet_model:item.id}); } state.selectedPet=item.id; localStorage.setItem('xinbot.pet',item.id); await refresh(); } catch(error) { report(error); } }
async function upload(event) { const file=event.target.files[0]; if(!file)return; busy.value=true; try { await api.importPet(file); await refresh(); state.notice='模型已导入'; } catch(error) { report(error); } finally { busy.value=false; event.target.value=''; } }
</script>
<template>
  <section class="page-view">
    <header class="view-header">
      <div><span class="eyebrow">APPEARANCE</span><h2>桌宠外观</h2></div>
      <button class="button" :disabled="busy" @click="input.click()"><Upload :size="16"/>导入 ZIP</button>
      <input hidden ref="input" type="file" accept=".zip" @change="upload"/>
    </header>
    <div class="page-body">
      <div class="section-label">模型库 <span>{{ state.pets.length }} 个外观</span></div>
      <div class="asset-grid">
        <button v-for="item in state.pets" :key="item.id" class="asset-card" :class="{selected:pet?.id===item.id}" @click="select(item)">
          <div class="asset-preview">
            <div v-if="item.type==='sprite'" class="sprite-preview" :style="{backgroundImage:`url(${item.url})`}"/>
            <img v-else-if="preview(item)" :src="preview(item)" :alt="item.name"/>
            <Box v-else :size="40" class="model-symbol"/>
          </div>
          <div class="asset-info"><strong>{{ item.name }}</strong><Check v-if="pet?.id===item.id" :size="17"/></div>
          <span class="badge">{{ item.type === 'live2d' ? 'Live2D · Cubism' : 'Codex · Sprite' }}</span>
        </button>
      </div>
      <div v-if="!state.pets.length" class="empty">暂无模型</div>
    </div>
  </section>
</template>
