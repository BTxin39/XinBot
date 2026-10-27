<script setup>
import { t } from '../i18n.js';
/**
 * 主题选择页。
 *
 * 每张卡片用主题自己的变量渲染预览色块——所见即所得，
 * 而不是让用户在几个名字里猜。
 */
import { ref, onMounted } from 'vue';
import { Check, Palette } from 'lucide-vue-next';
import { loadThemes, chooseTheme } from '../theme.js';
import { state, report } from '../state.js';

const items = ref([]);
const current = ref(localStorage.getItem('xinbot.theme') || '');
const busy = ref(false);

onMounted(async () => {
  try {
    const result = await loadThemes();
    if (result) {
      items.value = result.items;
      current.value = result.current;
    }
  } catch (error) { report(error); }
});

async function pick(name) {
  if (busy.value || name === current.value) return;
  busy.value = true;
  try {
    current.value = await chooseTheme(name);
    state.notice = `已切换到「${items.value.find(t => t.name === current.value)?.label || name}」`;
  } catch (error) { report(error); }
  finally { busy.value = false; }
}

/** 预览用的四个色块：底色、卡片、主色、主色淡底 */
function swatch(variables) {
  return [
    variables['--xin-bg'],
    variables['--xin-surface'],
    variables['--xin-accent'],
    variables['--xin-accent-soft'],
  ];
}
</script>

<template>
  <section class="page-view">
    <header class="view-header">
      <div><span class="eyebrow">THEME</span><h2>{{ t('theme.title') }}</h2></div>
      <Palette :size="20" />
    </header>
    <div class="page-body">
      <div class="section-label">{{ t('theme.palette') }} <span>{{ items.length }} 套</span></div>
      <div class="theme-grid">
        <button
          v-for="item in items"
          :key="item.name"
          class="theme-card"
          :class="{ active: item.name === current }"
          :disabled="busy"
          @click="pick(item.name)"
        >
          <div class="theme-preview" :style="{ background: item.variables['--xin-bg'] }">
            <div class="theme-surface" :style="{ background: item.variables['--xin-surface'] }">
              <i :style="{ background: item.variables['--xin-accent'] }" />
              <i :style="{ background: item.variables['--xin-accent-soft'] }" />
              <i :style="{ background: item.variables['--xin-text-muted'] }" />
            </div>
          </div>
          <div class="theme-info">
            <strong>{{ item.label }}</strong>
            <Check v-if="item.name === current" :size="16" />
          </div>
          <small>{{ item.description }}</small>
          <div class="theme-swatches">
            <i v-for="(color, index) in swatch(item.variables)" :key="index" :style="{ background: color }" />
          </div>
        </button>
      </div>
      <div v-if="!items.length" class="empty">暂时没有可选主题</div>
      <p class="hint">
        主题只调整主要表面色与强调色，不改动布局与功能。
        切换会同时保存到后端与本机浏览器，下次打开自动沿用。
      </p>
    </div>
  </section>
</template>

<style scoped>
.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 16px;
}
.theme-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  text-align: left;
  border-radius: 8px;
  border: 1px solid var(--border, #dce3df);
  background: var(--bg-card, #fff);
}
.theme-card.active {
  border-color: var(--accent, #376f55);
  box-shadow: 0 0 0 2px var(--accent-soft, #eaf2ed);
}
.theme-preview {
  height: 92px;
  border-radius: 6px;
  padding: 10px;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.theme-surface {
  height: 100%;
  border-radius: 4px;
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 8px;
}
.theme-surface i {
  width: 18px;
  height: 18px;
  border-radius: 4px;
}
.theme-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.theme-swatches {
  display: flex;
  gap: 4px;
}
.theme-swatches i {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  border: 1px solid rgba(0, 0, 0, 0.08);
}
.hint {
  margin-top: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--text-muted, #78867e);
}
</style>
