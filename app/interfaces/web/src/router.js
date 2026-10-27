import { createRouter, createWebHashHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import SettingsView from "./views/SettingsView.vue";
import PersonaView from "./views/PersonaView.vue";
import KnowledgeView from "./views/KnowledgeView.vue";
import AppearanceView from "./views/AppearanceView.vue";
import MemoryView from "./views/MemoryView.vue";
import AsciiView from "./views/AsciiView.vue";
import LogsView from "./views/LogsView.vue";
import PetOnlyView from "./views/PetOnlyView.vue";

const routes = [
  // 桌宠窗口专用：极简、透明、无工作台 UI（App.vue 会据此切换根布局）
  { path: "/pet", name: "pet", component: PetOnlyView },
  { path: "/memory", component: MemoryView },
  { path: "/ascii", component: AsciiView },
  { path: "/appearance", component: AppearanceView },
  { path: "/logs", name: "logs", component: LogsView },
  { path: "/", name: "home", component: HomeView },
  { path: "/settings", name: "settings", component: SettingsView },
  { path: "/persona", name: "persona", component: PersonaView },
  { path: "/knowledge", name: "knowledge", component: KnowledgeView },
  { path: "/calculator", component: HomeView },
  { path: "/terminal", component: HomeView },
  { path: "/profile", component: HomeView },
  { path: "/about", component: HomeView },
  { path: "/theme", component: HomeView },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
});
