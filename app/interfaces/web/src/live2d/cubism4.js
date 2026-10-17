/**
 * Cubism 3/4/5 运行时的**懒加载入口**。
 *
 * 与 cubism2.js 同理：只有真正要显示新格式模型时才动态 import，
 * 避免"用户只想看精灵图"却被要求下载 Cubism Core。
 */
export { Live2DModel } from 'pixi-live2d-display/cubism4';
