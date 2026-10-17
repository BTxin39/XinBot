import { test, expect } from '@playwright/test';

/**
 * 启动冒烟测试：页面必须真的渲染出来，且没有未捕获的 JS 错误。
 *
 * 为什么单独加这条：
 * v0.2.1 曾出现"整页空白"。原因是 `pixi-live2d-display/cubism2` 被静态导入，
 * 而它在**模块求值阶段**就要求 `window.Live2D` 存在，缺失直接抛错，
 * 把整个 bundle 带崩——HTML/CSS/JS 全部 200，但 #app 是空的。
 *
 * 这类故障只测接口发现不了（后端一切正常），必须用浏览器断言 DOM。
 */
test('页面能渲染且没有未捕获错误', async ({ page }) => {
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));

  // 屏蔽与本次断言无关的接口，避免依赖真实配置
  await page.route('**/api/status', route => route.fulfill({
    json: { ok: true, data: { ready: true, emotion: 'normal', model_name: 'test-model' } },
  }));
  await page.route('**/api/chat/history', route => route.fulfill({ json: { ok: true, data: [] } }));

  await page.goto('/');

  // 1) 根节点必须有实际内容（空字符串就是"空白页"）
  await expect.poll(async () => (await page.locator('#app').innerHTML()).length, { timeout: 15000 })
    .toBeGreaterThan(200);

  // 2) 关键界面元素在
  await expect(page.locator('.pet-workspace, .pet-stage').first()).toBeVisible();

  // 3) 没有未捕获异常
  expect(failures, `页面抛出了未捕获错误：${failures.join(' / ')}`).toEqual([]);
});
