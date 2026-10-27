import { createApp } from "vue";
import App from "./App.vue";
import router from "./router.js";
import { applyCachedTheme, loadThemes } from "./theme.js";
import { applyLocale, loadLocale, locale } from "./i18n.js";

// 先同步应用缓存配色，避免首屏闪一下默认色；随后再用服务端结果校准。
applyCachedTheme();
loadThemes().catch(() => {});

// 语言同理：先用本地缓存，再与服务端校准（服务端是唯一真相）
applyLocale(locale.value);
loadLocale().catch(() => {});

const app = createApp(App);
app.use(router);
app.mount("#app");
