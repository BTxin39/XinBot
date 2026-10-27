/**
 * 主题应用与切换。
 *
 * 为什么先把缓存写到 localStorage 再拉接口：
 * 首屏如果等接口回来再上色，会「闪一下默认配色」。所以启动时**同步**应用
 * 缓存里的变量，随后再用服务端结果校准（服务端是唯一真相）。
 */

const CACHE_KEY = 'xinbot.themes';
const NAME_KEY = 'xinbot.theme';

function readCache() {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
  } catch {
    return null;
  }
}

/** 把一套变量写到 <html> 上，并打上 data-theme 供 CSS 区分默认主题。 */
export function applyTheme(name, variables) {
  if (!name) return;
  const root = document.documentElement;
  root.dataset.theme = name;
  for (const [key, value] of Object.entries(variables || {})) {
    root.style.setProperty(key, value);
  }
  localStorage.setItem(NAME_KEY, name);
}

/** 启动时同步应用缓存的配色（不阻塞渲染）。 */
export function applyCachedTheme() {
  const cache = readCache();
  if (!cache || !Array.isArray(cache.items)) return;
  const name = localStorage.getItem(NAME_KEY) || cache.default;
  const entry = cache.items.find(item => item.name === name);
  if (entry) applyTheme(entry.name, entry.variables);
}

/** 拉取主题列表并应用服务端当前选择。 */
export async function loadThemes() {
  const response = await fetch('/api/themes').then(r => r.json());
  if (!response.ok) return null;
  const { items, current, default: fallback } = response.data;
  localStorage.setItem(CACHE_KEY, JSON.stringify({ items, default: fallback }));
  const entry = items.find(item => item.name === current) || items.find(item => item.name === fallback);
  if (entry) applyTheme(entry.name, entry.variables);
  return { items, current };
}

/** 切换主题（服务端持久化 + 立即生效）。 */
export async function chooseTheme(name) {
  const response = await fetch('/api/theme', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }).then(r => r.json());
  if (!response.ok) throw new Error(response.error || '切换主题失败');
  applyTheme(response.data.current, response.data.variables);
  return response.data.current;
}
