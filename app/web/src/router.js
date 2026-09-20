import { createRouter, createWebHashHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import SettingsView from "./views/SettingsView.vue";
import PersonaView from "./views/PersonaView.vue";
import KnowledgeView from "./views/KnowledgeView.vue";
import AppearanceView from "./views/AppearanceView.vue";

const routes = [
  { path: "/appearance", component: AppearanceView },
  { path: "/", name: "home", component: HomeView },
  { path: "/settings", name: "settings", component: SettingsView },
  { path: "/persona", name: "persona", component: PersonaView },
  { path: "/knowledge", name: "knowledge", component: KnowledgeView },
];

export default createRouter({
  history: createWebHashHistory(),
  routes,
});
