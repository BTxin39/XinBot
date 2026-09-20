async function request(method, path, body) {
  const multipart = body instanceof FormData;
  const response = await fetch(path, {
    method,
    headers: multipart ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({ error: `请求失败 (${response.status})` }));
  if (!response.ok || result.ok === false) throw new Error(result.error || '请求失败');
  return result;
}
function upload(path, file) {
  const form = new FormData();
  form.append('file', file);
  return request('POST', path, form);
}
const id = encodeURIComponent;
export default {
  registerModel: data => request('POST', '/api/models/register', data),
  deleteModel: name => request('DELETE', `/api/models/${id(name)}`),
  deleteProvider: name => request('DELETE', `/api/providers/${id(name)}`),
  deleteKey: name => request('DELETE', `/api/providers/${id(name)}/key`),
  updateKey: (name, api_key) => request('PUT', `/api/providers/${id(name)}/key`, {api_key}),
  ollamaModels: base_url => request('POST', '/api/ollama/models', {base_url}),
  memories: () => request('GET', '/api/memory'),
  memory: name => request('GET', `/api/memory/${id(name)}`),
  createMemory: data => request('POST', '/api/memory', data),
  updateMemory: (name, data) => request('PUT', `/api/memory/${id(name)}`, data),
  activateMemory: name => request('POST', `/api/memory/${id(name)}/activate`),
  clearMemory: name => request('DELETE', `/api/memory/${id(name)}/messages`),
  deleteMemory: name => request('DELETE', `/api/memory/${id(name)}`),
  memoryCommand: (command, confirm = false) => request('POST', '/api/memory/terminal', {command, confirm}),
  ascii: form => request('POST', '/api/ascii', form),
  getStatus: () => request('GET', '/api/status'),
  getConfig: () => request('GET', '/api/config'),
  updateConfig: data => request('POST', '/api/config', data),
  models: () => request('GET', '/api/models'),
  saveConnection: data => request('POST', '/api/models', data),
  pets: () => request('GET', '/api/pet/models'),
  importPet: file => upload('/api/pet/models/import', file),
  listPersonas: () => request('GET', '/api/persona'),
  createPersona: data => request('POST', '/api/persona', data),
  updatePersona: (name, data) => request('PUT', `/api/persona/${id(name)}`, data),
  activatePersona: name => request('POST', `/api/persona/${id(name)}/activate`),
  deletePersona: name => request('DELETE', `/api/persona/${id(name)}`),
  importPersona: file => upload('/api/persona/import', file),
  history: () => request('GET', '/api/chat/history'),
  clearHistory: () => request('DELETE', '/api/chat/history'),
  createChatWS: () => new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/chat`),
  getRagSources: () => request('GET', '/api/rag/sources'),
  ingestFile: file => upload('/api/rag/ingest', file),
  ingestUrl: url => request('POST', '/api/rag/ingest-url', { url }),
  searchRag: query => request('POST', '/api/rag/search', { query }),
  deleteSource: source => request('DELETE', `/api/rag/sources/${id(source)}`),
  clearRag: () => request('DELETE', '/api/rag/clear'),
};
