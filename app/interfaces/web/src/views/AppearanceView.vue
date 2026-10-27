<script setup>
import { t } from '../i18n.js';
import { ref, computed } from 'vue';
import { Upload, Check, Box, AlertTriangle, Trash2, Pencil, X } from 'lucide-vue-next';
import { state, pet, character, refresh, report } from '../state.js';
import api from '../api.js';

const busy = ref(false), input = ref(null);
const deleting = ref('');      // 正在确认删除的模型 id
const renaming = ref('');      // 正在重命名的模型 id
const newName = ref('');
const preview = item => state.previews[item.id];

/** 展示用的格式标签：旧版 Cubism 2.1 与新版必须能区分开。 */
const formatLabel = item => {
  if (item.type === 'sprite') return 'Codex · Sprite';
  return item.format === 'cubism2' ? 'Live2D · 旧版 2.1' : 'Live2D · Cubism 3/4/5';
};

const missingRuntime = computed(() => state.pets.filter(item => item.runtime_ready === false));
/** 只有导入目录里的模型可以删/改名；内置目录（pet/live2d、pet/codexpet）不归界管。 */
const editable = item => item.id.startsWith('imported:');

async function select(item) {
  try {
    if (character.value) {
      const { builtin, avatar, ...body } = character.value;
      await api.updatePersona(body.name, { ...body, pet_model: item.id });
    }
    state.selectedPet = item.id;
    localStorage.setItem('xinbot.pet', item.id);
    await refresh();
  } catch (error) { report(error); }
}

async function upload(event) {
  const file = event.target.files[0];
  if (!file) return;
  busy.value = true;
  try {
    const result = await api.importPet(file);
    const model = result?.data?.model;
    await refresh();
    state.notice = model?.warnings?.length
      ? `已导入 ${model.name}：${model.warnings.join('；')}`
      : `已导入 ${model?.name || '模型'}`;
  } catch (error) { report(error); }
  finally { busy.value = false; event.target.value = ''; }
}

function askDelete(item) { deleting.value = item.id; renaming.value = ''; }

async function confirmDelete(item) {
  busy.value = true;
  try {
    await api.deletePet(item.name);
    // 如果删的正是当前外观，清掉绑定，避免主页指向不存在的模型
    if (pet.value?.id === item.id) {
      state.selectedPet = '';
      localStorage.removeItem('xinbot.pet');
    }
    await refresh();
    state.notice = `已删除 ${item.name}`;
  } catch (error) { report(error); }
  finally { busy.value = false; deleting.value = ''; }
}

function askRename(item) { renaming.value = item.id; deleting.value = ''; newName.value = item.name; }

async function confirmRename(item) {
  const name = newName.value.trim();
  if (!name || name === item.name) { renaming.value = ''; return; }
  busy.value = true;
  try {
    const result = await api.renamePet(item.name, name);
    // 当前选中的模型改名后 id 变了，需要同步绑定，否则主页会找不到外观
    if (pet.value?.id === item.id) {
      const manifest = result?.data?.model?.manifest;
      const location = result?.data?.model?.location || '';
      const container = location.split(/[\\/]/).slice(-2)[0];
      const nextId = manifest && container ? `imported:${container}/${name}/${manifest}` : '';
      if (nextId) {
        state.selectedPet = nextId;
        localStorage.setItem('xinbot.pet', nextId);
      }
    }
    await refresh();
    state.notice = `已重命名为 ${name}`;
  } catch (error) { report(error); }
  finally { busy.value = false; renaming.value = ''; }
}
</script>

<template>
  <section class="page-view">
    <header class="view-header">
      <div><span class="eyebrow">APPEARANCE</span><h2>{{ t('appearance.title') }}</h2></div>
      <button class="button" :disabled="busy" @click="input.click()"><Upload :size="16"/>{{ t('appearance.import') }}</button>
      <input hidden ref="input" type="file" accept=".zip" @change="upload"/>
    </header>

    <div class="page-body">
      <div v-if="missingRuntime.length" class="runtime-warning">
        <AlertTriangle :size="16"/>
        <span>有 {{ missingRuntime.length }} 个模型缺少运行时，暂时无法显示：{{ missingRuntime[0].runtime_missing }}</span>
      </div>

      <div class="section-label">{{ t('appearance.library') }} <span>{{ state.pets.length }} 个外观</span></div>
      <div class="asset-grid">
        <div v-for="item in state.pets" :key="item.id" class="asset-card"
             :class="{ selected: pet?.id === item.id, unavailable: item.runtime_ready === false }">
          <button class="asset-main" @click="select(item)">
            <div class="asset-preview">
              <div v-if="item.type === 'sprite'" class="sprite-preview" :style="{ backgroundImage: `url(${item.url})` }"/>
              <img v-else-if="preview(item)" :src="preview(item)" :alt="item.name"/>
              <Box v-else :size="40" class="model-symbol"/>
            </div>
            <div class="asset-info"><strong>{{ item.name }}</strong><Check v-if="pet?.id === item.id" :size="17"/></div>
            <span class="badge">{{ formatLabel(item) }}</span>
            <span v-if="item.runtime_ready === false" class="badge warn">{{ t('appearance.missingRuntime') }}</span>
          </button>

          <!-- 内置目录里的模型不提供删除/改名：它们属于发布包资产 -->
          <div v-if="editable(item)" class="asset-actions">
            <button class="mini" title="重命名" aria-label="重命名" @click.stop="askRename(item)"><Pencil :size="14"/></button>
            <button class="mini danger" title="删除" aria-label="删除" @click.stop="askDelete(item)"><Trash2 :size="14"/></button>
          </div>

          <div v-if="renaming === item.id" class="inline-panel">
            <input v-model="newName" maxlength="100" placeholder="新名字" @keyup.enter="confirmRename(item)"/>
            <button class="mini" @click="confirmRename(item)">保存</button>
            <button class="mini" @click="renaming = ''"><X :size="14"/></button>
          </div>

          <div v-if="deleting === item.id" class="inline-panel">
            <span>删除「{{ item.name }}」？</span>
            <button class="mini danger" @click="confirmDelete(item)">删除</button>
            <button class="mini" @click="deleting = ''">取消</button>
          </div>
        </div>
      </div>

      <div v-if="!state.pets.length" class="empty">{{ t('appearance.empty') }}</div>

      <p class="hint">
        支持三种格式：Live2D Cubism 3/4/5（<code>.model3.json</code>）、
        Live2D Cubism 2.1 旧版（<code>.model.json</code>，需要自行放置
        <code>pet/vendor/live2d.min.js</code>）、Codex 8×9 精灵图（<code>pet.json</code>）。
        命令行等价操作：<code>xinbot model import &lt;zip&gt;</code>、
        <code>xinbot model rename</code>、<code>xinbot model remove</code>。
      </p>
    </div>
  </section>
</template>

<style scoped>
.runtime-warning {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; margin-bottom: 14px;
  border-radius: 8px; font-size: 13px;
  background: rgba(217, 119, 6, 0.12); color: #d97706;
}
.asset-card { position: relative; display: flex; flex-direction: column; }
.asset-card.unavailable { opacity: 0.62; }
.asset-main { display: flex; flex-direction: column; gap: 8px; width: 100%; background: none; border: none; cursor: pointer; text-align: left; padding: 0; }
.badge.warn { margin-left: 6px; background: rgba(220, 38, 38, 0.15); color: #dc2626; }
.asset-actions { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; opacity: 0; transition: opacity .15s; }
.asset-card:hover .asset-actions { opacity: 1; }
.mini {
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  min-height: 26px; padding: 3px 8px; border-radius: 6px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-secondary); color: var(--text-muted);
}
.mini:hover { color: var(--text); }
.mini.danger { color: #dc2626; border-color: rgba(220, 38, 38, .4); }
.inline-panel {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-top: 10px; padding: 8px; border-radius: 8px;
  background: var(--bg-secondary); border: 1px solid var(--border); font-size: 12px;
}
.inline-panel input {
  flex: 1; min-width: 100px; padding: 4px 8px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--bg-card); color: var(--text);
}
.hint { margin-top: 18px; font-size: 12px; line-height: 1.9; color: var(--text-muted); }
.hint code { padding: 1px 5px; border-radius: 4px; background: var(--bg-card); }
</style>
