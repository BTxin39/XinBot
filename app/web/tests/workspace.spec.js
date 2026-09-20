import { test, expect } from '@playwright/test';

async function isolate(page) {
  await page.route('**/api/status', route => route.fulfill({json:{ok:true,data:{ready:true,emotion:'normal',model_name:'test-model'}}}));
  await page.route('**/api/chat/history', route => route.fulfill({json:{ok:true,data:[]}}));
  await page.route('**/api/persona', async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.data.forEach(item => { item.pet_model = ''; });
    await route.fulfill({json:body});
  });
}

async function pixels(page) {
  return page.locator('.pet-stage canvas').evaluate(canvas => {
    const copy = document.createElement('canvas'); copy.width = 80; copy.height = 80;
    const context = copy.getContext('2d'); context.drawImage(canvas, 0, 0, 80, 80);
    const data = context.getImageData(0, 0, 80, 80).data;
    return {visible:Array.from(data).filter((value,index)=>index%4===3 && value>0).length,hash:Array.from(data).reduce((total,value,index)=>(total+value*(index+1))%1000000007,0)};
  });
}

test('Live2D is visible, animated and responsive', async ({page}) => {
  const failures=[];page.on('pageerror', error=>failures.push(error.message));
  await isolate(page);
  await page.goto('/');
  await expect(page.locator('.pet-caption')).toContainText('Haru');
  await expect(page.locator('.stage-status')).toHaveCount(0,{timeout:45000});
  await expect.poll(async()=> (await pixels(page)).visible).toBeGreaterThan(250);
  const first=await pixels(page);await page.waitForTimeout(1300);
  expect((await pixels(page)).hash).not.toBe(first.hash);
  await page.screenshot({path:'test-results/desktop.png',fullPage:true});
  await page.getByRole('button',{name:'放大',exact:true}).click();
  await page.getByRole('button',{name:'打招呼',exact:true}).click();
  await page.getByRole('link',{name:'角色卡',exact:true}).click();
  await page.getByRole('button',{name:'新建',exact:true}).click();
  await expect(page.getByLabel('角色名称')).toBeVisible();
  await page.screenshot({path:'test-results/character-editor.png',fullPage:true});
  await page.getByRole('link',{name:'模型与连接',exact:true}).click();
  await expect(page.getByLabel('API 密钥')).toHaveAttribute('type','password');
  await page.screenshot({path:'test-results/settings.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.goto('/');
  await expect(page.locator('.stage-status')).toHaveCount(0,{timeout:45000});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/mobile.png',fullPage:true});
  expect(failures).toEqual([]);
});

test('Codex sprite animation and chat transport', async ({page}) => {
  await isolate(page);
  await page.addInitScript(()=>localStorage.setItem('xinbot.pet','codex:kaguya/pet.json'));
  await page.routeWebSocket('**/ws/chat', socket=>socket.onMessage(()=>{socket.send(JSON.stringify({chunk:'测试回复 **成功**'}));socket.send(JSON.stringify({done:true}));}));
  await page.goto('/');
  await expect(page.locator('.pet-caption')).toContainText('Kaguya');
  await expect(page.locator('.stage-status')).toHaveCount(0);
  expect((await pixels(page)).visible).toBeGreaterThan(250);
  const first=await pixels(page);await page.waitForTimeout(450);expect((await pixels(page)).hash).not.toBe(first.hash);
  await page.getByLabel('聊天消息').fill('你好');await page.getByRole('button',{name:'发送',exact:true}).click();
  await expect(page.locator('.message.assistant')).toContainText('测试回复 成功');
  await page.screenshot({path:'test-results/sprite-chat.png',fullPage:true});
});
