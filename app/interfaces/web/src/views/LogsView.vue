<script setup>
import { t } from '../i18n.js';
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { RefreshCw, Trash2, Play, Pause, Activity, Download } from 'lucide-vue-next';
import api from '../api.js';

const entries = ref([]);
const status = ref(null);
const level = ref('');
const error = ref('');
const autoRefresh = ref(true);
const loading = ref(false);
let timer = null;

const LEVELS = [
  { value: '', label: t('logs.levelAll') },
  { value: 'INFO', label: t('logs.levelInfo') },
  { value: 'WARNING', label: t('logs.levelWarning') },
  { value: 'ERROR', label: t('logs.levelError') },
];

const uptime = computed(() => {
  const seconds = Math.round(status.value?.uptime_seconds || 0);
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return h ? `${h}小时${m}分` : m ? `${m}分${s}秒` : `${s}秒`;
});

async function reload() {
  loading.value = true;
  try {
    const result = await api.logs(200, level.value || undefined);
    entries.value = result.data.entries;
    status.value = result.data.status;
    error.value = '';
  } catch (failure) { error.value = failure.message || '读取日志失败'; }
  finally { loading.value = false; }
}

async function clearLogs() {
  try { await api.clearLogs(); await reload(); }
  catch (failure) { error.value = failure.message; }
}

/**
 * 导出为 .log 文件。
 * 直接请求导出端点（服务端已带完整日期与表头），用 blob 触发下载；
 * 不走 JSON 接口再拼字符串，避免前端与服务端格式分叉。
 */
async function exportLogs() {
  try {
    const query = new URLSearchParams({ limit: '500' });
    if (level.value) query.set('level', level.value);
    const response = await fetch(`/api/logs/export?${query}`);
    if (!response.ok) throw new Error(`导出失败 (${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    link.href = url;
    link.download = `xinbot-logs-${stamp}.log`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (failure) { error.value = failure.message || '导出失败'; }
}

function toggle() {
  autoRefresh.value = !autoRefresh.value;
  schedule();
}

function schedule() {
  window.clearInterval(timer);
  timer = autoRefresh.value ? window.setInterval(reload, 2000) : null;
}

onMounted(() => { reload(); schedule(); });
onUnmounted(() => window.clearInterval(timer));
</script>

<template>
  <section class="page-view">
    <header class="view-header">
      <div><span class="eyebrow">RUNTIME</span><h2>{{ t('logs.title') }}</h2></div>
      <div class="actions">
        <button class="button ghost" @click="toggle">
          <component :is="autoRefresh ? Pause : Play" :size="16"/>{{ autoRefresh ? t('logs.pause') : t('logs.autoRefresh') }}
        </button>
        <button class="button ghost" :disabled="loading" @click="reload"><RefreshCw :size="16"/>{{ t('logs.refresh') }}</button>
        <button class="button ghost" @click="exportLogs"><Download :size="16"/>{{ t('logs.export') }}</button>
        <button class="button ghost" @click="clearLogs"><Trash2 :size="16"/>{{ t('logs.clear') }}</button>
      </div>
    </header>

    <div class="page-body">
      <div v-if="status" class="stat-grid">
        <div class="stat">
          <span class="stat-label"><Activity :size="14"/>已运行</span>
          <strong>{{ uptime }}</strong>
        </div>
        <div class="stat">
          <span class="stat-label">缓冲</span>
          <strong>{{ status.buffered }} / {{ status.capacity }}</strong>
        </div>
        <div class="stat">
          <span class="stat-label">警告</span>
          <strong class="warn">{{ status.warnings }}</strong>
        </div>
        <div class="stat">
          <span class="stat-label">错误</span>
          <strong class="err">{{ status.errors }}</strong>
        </div>
      </div>

      <div class="toolbar">
        <label v-for="item in LEVELS" :key="item.value" class="chip"
               :class="{ active: level === item.value }" @click="level = item.value; reload()">
          {{ item.label }}
        </label>
      </div>

      <div v-if="error" class="empty">{{ error }}</div>
      <div v-else class="log-list">
        <div v-for="(item, index) in entries" :key="index" class="log-row" :class="item.level.toLowerCase()">
          <span class="log-time">{{ item.stamp }}</span>
          <span class="log-level">{{ item.level }}</span>
          <span class="log-logger">{{ item.logger }}</span>
          <span class="log-message">{{ item.message }}</span>
        </div>
        <div v-if="!entries.length" class="empty">{{ t('logs.empty') }}</div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.actions { display: flex; gap: 8px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 16px; }
.stat { padding: 12px 14px; border-radius: 10px; background: var(--bg-card); border: 1px solid var(--border); }
.stat-label { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-muted); }
.stat strong { display: block; margin-top: 6px; font-size: 18px; }
.stat strong.warn { color: #d97706; }
.stat strong.err { color: #dc2626; }
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; }
.chip { padding: 5px 12px; border-radius: 999px; font-size: 12px; cursor: pointer;
        background: var(--bg-card); border: 1px solid var(--border); color: var(--text-muted); }
.chip.active { color: var(--text); border-color: var(--accent); }
.log-list { max-height: 60vh; overflow-y: auto; border-radius: 10px; border: 1px solid var(--border); background: var(--bg-card); }
.log-row { display: grid; grid-template-columns: 74px 74px 130px 1fr; gap: 10px;
           padding: 5px 12px; font-family: ui-monospace, Consolas, monospace; font-size: 12px;
           border-bottom: 1px solid var(--border); }
.log-row:last-child { border-bottom: none; }
.log-time { color: var(--text-muted); }
.log-level { font-weight: 600; }
.log-row.info .log-level { color: #16a34a; }
.log-row.warning .log-level { color: #d97706; }
.log-row.error .log-level, .log-row.critical .log-level { color: #dc2626; }
.log-logger { color: var(--accent); overflow: hidden; text-overflow: ellipsis; }
.log-message { white-space: pre-wrap; word-break: break-word; }
</style>
