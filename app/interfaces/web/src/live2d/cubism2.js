/**
 * Cubism 2.1 运行时的**懒加载入口**。
 *
 * 为什么单独成一个模块：
 * `pixi-live2d-display/cubism2` 在**模块求值阶段**就检查 `window.Live2D`，
 * 缺失会直接抛 "Could not find Cubism 2 runtime"，把整个 bundle 带崩
 * （表现为页面完全空白）。因此必须满足两个条件：
 *   1. 先加载 `live2d.min.js`，再 import 本模块；
 *   2. 本模块只能被**动态 import**，这样 Vite 会把它拆成独立 chunk，
 *      只有真正要看旧格式模型时才求值。
 *
 * 相关约束见 docs/DECISIONS_v0.2.1.md §1.4。
 */
export { Live2DModel } from 'pixi-live2d-display/cubism2';
