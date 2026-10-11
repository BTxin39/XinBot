import { test, expect } from '@playwright/test';

test('management pages, terminal and image conversion', async ({ page }) => {
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  await page.route('**/api/status', route => route.fulfill({ json: { ok: true, data: { ready: true, emotion: 'normal' } } }));
  await page.route('**/api/chat/history', route => route.fulfill({ json: { ok: true, data: [] } }));
  await page.route('**/api/memory', route => route.fulfill({ json: { ok: true, data: [{ name: 'default', count: 0, active: true, description: 'Test memory' }] } }));
  await page.route('**/api/memory/terminal', route => route.fulfill({ json: { ok: true, data: { output: 'list | show NAME | create NAME' } } }));
  await page.route('**/api/ollama/models', route => route.fulfill({ json: { ok: true, data: [{ name: 'qwen3:8b', size: 123 }] } }));
  await page.goto('/');
  await page.getByRole('button', { name: '管理' }).click();
  await page.getByRole('link', { name: '记忆', exact: true }).click();
  await expect(page.getByText('Test memory', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '交互控制台' }).click();
  await page.getByLabel('记忆终端命令').fill('help');
  await page.getByRole('button', { name: '执行命令' }).click();
  await expect(page.getByRole('log')).toContainText('show NAME');
  await page.screenshot({ path: 'test-results/memory-console.png', fullPage: true });
  await page.getByRole('button', { name: '账户' }).click();
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByLabel('接口类型').selectOption('ollama');
  await page.getByRole('button', { name: '读取本机模型' }).click();
  await page.getByLabel('已安装模型').selectOption('qwen3:8b');
  await expect(page.getByLabel('模型 ID', { exact: true })).toHaveValue('qwen3:8b');
  await page.getByRole('button', { name: '运行配置', exact: true }).click();
  await expect(page.getByLabel('Web 端口（重启后生效）')).toHaveAttribute('max', '65535');
  await page.screenshot({ path: 'test-results/config.png', fullPage: true });
  await page.getByRole('button', { name: '工具箱' }).click();
  await page.getByRole('link', { name: '字符画', exact: true }).click();
  const image = await page.evaluate(() => { const canvas = document.createElement('canvas'); canvas.width = 64; canvas.height = 64; const context = canvas.getContext('2d'); context.fillStyle = '#426c53'; context.fillRect(0, 0, 64, 64); return canvas.toDataURL('image/png').split(',')[1]; });
  await page.locator('.floating-panel input[type=file]').setInputFiles({ name: 'sample.png', mimeType: 'image/png', buffer: Buffer.from(image, 'base64') });
  await page.getByRole('button', { name: '转换', exact: true }).click();
  await expect(page.locator('.ascii-output')).toBeVisible();
  await page.screenshot({ path: 'test-results/ascii.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  for (const [menu, label] of [['管理','记忆'], ['账户','设置'], ['工具箱','字符画']]) {
    await page.getByRole('button', { name: menu }).click();
    await page.getByRole('link', { name: label, exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `test-results/mobile-${label}.png`, fullPage: true });
  }
  expect(failures).toEqual([]);
});
