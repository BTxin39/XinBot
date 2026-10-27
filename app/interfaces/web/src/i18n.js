/**
 * 前端多语言。
 *
 * 范围：先把**高频界面**（导航、页头、外观/日志/主题页的标题与按钮）抽成语言包，
 * 其余视图仍是中文——文档里已标注，避免给人"全都翻了"的错觉。
 *
 * 为什么不用 vue-i18n：只需要一个 `t()` 和一个响应式 locale，
 * 引入完整 i18n 框架（含复数、日期格式、消息编译）不值得。
 */

import { ref, computed } from 'vue';

const STORAGE_KEY = 'xinbot.locale';

/** 界面文案。键名用 `区域.用途`，与后端 `i18n_service` 的命名习惯一致。 */
export const MESSAGES = {
  'zh-CN': {
    'nav.conversation': '对话',
    'nav.appearance': '外观',
    'nav.persona': '角色',
    'nav.knowledge': '知识库',
    'nav.logs': '运行日志',
    'nav.settings': '设置',
    'header.online': '本地运行中',
    'header.offline': '未连接',
    'menu.tools': '工具箱',
    'menu.manage': '管理',
    'menu.account': '账户',
    'menu.ascii': '字符画',
    'menu.calculator': '计算器',
    'menu.persona': '角色卡',
    'menu.memory': '记忆',
    'menu.knowledge': '知识库',
    'menu.appearance': '桌宠外观',
    'menu.profile': '离线档案',
    'menu.settings': '设置',
    'menu.terminal': '终端',
    'menu.about': '项目属性',
    'menu.theme': '主题',
    'header.busy': '正在思考',
    'header.companion': '陪伴中',
    'pet.pickAppearance': '请先在网页端选择外观',
    'appearance.title': '桌宠外观',
    'appearance.import': '导入 ZIP',
    'appearance.library': '模型库',
    'appearance.empty': '暂无模型',
    'appearance.missingRuntime': '缺运行时',
    'logs.pause': '暂停刷新',
    'logs.autoRefresh': '自动刷新',
    'logs.levelAll': '全部',
    'logs.levelInfo': 'INFO 以上',
    'logs.levelWarning': 'WARNING 以上',
    'logs.levelError': '仅 ERROR',
    'logs.title': '运行状态与日志',
    'logs.refresh': '刷新',
    'logs.export': '导出',
    'logs.clear': '清空',
    'logs.empty': '暂无日志。',
    'theme.title': '主题',
    'theme.palette': '配色方案',
    'settings.language': '界面语言',
    'common.confirm': '确定',
    'common.cancel': '取消',
    'common.save': '保存',
    'common.delete': '删除',
    'common.rename': '重命名',
  },
  en: {
    'nav.conversation': 'Chat',
    'nav.appearance': 'Appearance',
    'nav.persona': 'Characters',
    'nav.knowledge': 'Knowledge',
    'nav.logs': 'Logs',
    'nav.settings': 'Settings',
    'header.online': 'Running locally',
    'header.offline': 'Disconnected',
    'menu.tools': 'Tools',
    'menu.manage': 'Manage',
    'menu.account': 'Account',
    'menu.ascii': 'ASCII art',
    'menu.calculator': 'Calculator',
    'menu.persona': 'Characters',
    'menu.memory': 'Memory',
    'menu.knowledge': 'Knowledge',
    'menu.appearance': 'Appearance',
    'menu.profile': 'Profile',
    'menu.settings': 'Settings',
    'menu.terminal': 'Terminal',
    'menu.about': 'About',
    'menu.theme': 'Theme',
    'header.busy': 'Thinking',
    'header.companion': 'Here with you',
    'pet.pickAppearance': 'Pick an appearance in the web UI first',
    'appearance.title': 'Appearance',
    'appearance.import': 'Import ZIP',
    'appearance.library': 'Library',
    'appearance.empty': 'No models yet',
    'appearance.missingRuntime': 'Runtime missing',
    'logs.pause': 'Pause',
    'logs.autoRefresh': 'Auto refresh',
    'logs.levelAll': 'All',
    'logs.levelInfo': 'INFO+',
    'logs.levelWarning': 'WARNING+',
    'logs.levelError': 'ERROR only',
    'logs.title': 'Status & Logs',
    'logs.refresh': 'Refresh',
    'logs.export': 'Export',
    'logs.clear': 'Clear',
    'logs.empty': 'No logs yet.',
    'theme.title': 'Theme',
    'theme.palette': 'Color schemes',
    'settings.language': 'Language',
    'common.confirm': 'OK',
    'common.cancel': 'Cancel',
    'common.save': 'Save',
    'common.delete': 'Delete',
    'common.rename': 'Rename',
  },
};

export const DEFAULT_LOCALE = 'zh-CN';

/** 当前语言（响应式，切换后所有 `t()` 立即更新） */
export const locale = ref(localStorage.getItem(STORAGE_KEY) || DEFAULT_LOCALE);

/** 服务端可选语言（含显示名），由 `/api/locale` 填充 */
export const available = ref([{ code: 'zh-CN', label: '简体中文' }, { code: 'en', label: 'English' }]);

export function normalize(value) {
  const text = String(value || '').trim().replace('_', '-');
  if (!text) return DEFAULT_LOCALE;
  if (MESSAGES[text]) return text;
  const base = text.split('-')[0].toLowerCase();
  if (base === 'zh') return 'zh-CN';
  if (MESSAGES[base]) return base;
  return DEFAULT_LOCALE;
}

/**
 * 取文案。回落顺序：当前语言 → 默认语言 → 键名本身。
 * 返回键名而不是空串，是为了让漏翻一眼可见（而不是界面上出现空白）。
 */
export function translate(key, target = locale.value) {
  const current = MESSAGES[normalize(target)] || {};
  const fallback = MESSAGES[DEFAULT_LOCALE] || {};
  return current[key] ?? fallback[key] ?? key;
}

/** 组件里用：`const t = useT()` 后 `t('nav.logs')` 会随语言变化重算。 */
export function useT() {
  return computed(() => translate);
}

/** 直接调用（不依赖组件上下文） */
export const t = translate;

export function applyLocale(value) {
  locale.value = normalize(value);
  localStorage.setItem(STORAGE_KEY, locale.value);
  document.documentElement.setAttribute('lang', locale.value);
  return locale.value;
}

export async function loadLocale() {
  const response = await fetch('/api/locale').then(r => r.json()).catch(() => null);
  if (!response || !response.ok) return locale.value;
  const data = response.data;
  if (Array.isArray(data.available) && data.available.length) available.value = data.available;
  return applyLocale(data.current);
}

export async function chooseLocale(value) {
  const response = await fetch('/api/locale', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locale: value }),
  }).then(r => r.json());
  if (!response.ok) throw new Error(response.error || '切换语言失败');
  if (Array.isArray(response.data.available) && response.data.available.length) {
    available.value = response.data.available;
  }
  return applyLocale(response.data.current);
}
