import { computed, reactive } from 'vue';
import api from './api.js';

export const state = reactive({
  config: {}, status: {}, personas: [], pets: [], models: [], providers: [],
  selectedPet: localStorage.getItem('xinbot.pet') || '',
  messages: [], busy: false, error: '', notice: '', connected: false, previews: {},
  // 最近一次互动反应（由后端判定，Live2DCanvas 负责执行）
  reaction: null,
  // 角色真实包围盒（CSS 像素），供桌宠外壳做命中检测
  petBounds: null,
});
export const character = computed(() => state.personas.find(item => item.name === state.config.persona_name));
export const pet = computed(() => state.pets.find(item => item.id === (character.value?.pet_model || state.selectedPet)) || state.pets[0]);
export async function refresh() {
  const [config, personas, pets, models, status] = await Promise.all([
    api.getConfig(), api.listPersonas(), api.pets(), api.models(), api.getStatus(),
  ]);
  Object.assign(state, { config: config.data, personas: personas.data, pets: pets.data,
    models: models.data.models, providers: models.data.providers, status: status.data, connected: true });
}
export async function loadHistory() {
  state.messages = [];
  if (!state.status.ready) return;
  state.messages = (await api.history()).data;
}
export async function activate(name) {
  if (state.busy) return;
  await api.activatePersona(name);
  await refresh();
  await loadHistory();
}
export function report(error) { state.error = error.message || String(error); }
