import { test, expect } from '@playwright/test';

test('workspace menus, floating panels and mobile layout', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.companion')).toBeVisible();
  await expect(page.locator('.chat-view')).toBeVisible();
  await expect(page.locator('.rail')).toHaveCount(0);
  await expect(page.locator('.stage-status')).toHaveCount(0, { timeout: 45000 });
  await expect.poll(async () => page.locator('.pet-stage canvas').evaluate(canvas => {
    const copy = document.createElement('canvas'); copy.width = 40; copy.height = 40;
    const context = copy.getContext('2d'); context.drawImage(canvas, 0, 0, 40, 40);
    return Array.from(context.getImageData(0, 0, 40, 40).data).filter((value, index) => index % 4 === 3 && value > 0).length;
  }), { timeout: 45000 }).toBeGreaterThan(50);
  await page.getByRole('button', { name: '管理' }).click();
  await page.getByRole('link', { name: '角色卡' }).click();
  await expect(page.locator('.floating-panel')).toBeVisible();
  await page.screenshot({ path: 'test-results/v011-desktop.png', fullPage: true });
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const stage = await page.locator('.companion').boundingBox();
  const chat = await page.locator('.content').boundingBox();
  expect(stage.y + stage.height).toBeLessThanOrEqual(chat.y + 1);
  await page.screenshot({ path: 'test-results/v011-mobile-workspace.png', fullPage: true });
  await page.getByRole('button', { name: '工具箱' }).click();
  await page.getByRole('link', { name: '计算器' }).click();
  await expect(page.locator('.calculator')).toBeVisible();
  await page.screenshot({ path: 'test-results/v011-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});
