import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, visit, VIEWPORTS } from './harness.ts';
import { ITEM, openItemPage } from './item-fixture.ts';

describe('全屏快进反馈与演员性别筛选', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}: 快进显示居中的时间与进度后自动消失`, { timeout: 45_000 }, async () => {
      const opened = await openItemPage(browser, `/assets/${ITEM.plain}`, viewport);
      const page = opened.page;
      try {
        await page.locator('#stage video.vjs-tech').waitFor({ state: 'attached' });
        await page.locator('#stage .video-js').evaluate(node => node.requestFullscreen());
        await page.waitForFunction(() => !!document.fullscreenElement);
        await page.evaluate(() => {
          const video = document.querySelector<HTMLVideoElement>('#stage video.vjs-tech')!;
          video.pause();
          Object.defineProperty(video, 'duration', { configurable: true, value: 120 });
          video.currentTime = 30;
        });
        await page.keyboard.press('ArrowRight');
        const popup = page.locator('[data-fullscreen-seek]');
        await popup.waitFor();
        assert.match(await popup.innerText(), /0:40\s*\/\s*2:00/);
        assert.equal(await popup.locator('progress').evaluate(node => (node as HTMLProgressElement).value), 40);
        const layout = await popup.evaluate(node => {
          const rect = node.getBoundingClientRect();
          return { center: rect.x + rect.width / 2, top: rect.top, width: window.innerWidth, right: rect.right };
        });
        assert.ok(Math.abs(layout.center - layout.width / 2) < 2);
        assert.ok(layout.top >= 0 && layout.right <= layout.width);
        await page.keyboard.press('ArrowLeft');
        assert.equal(await popup.count(), 1);
        await popup.waitFor({ state: 'hidden', timeout: 4000 });
        await page.evaluate(() => document.exitFullscreen());
      } finally { await opened.close() }
    });
    it(`${viewport.name}: 多选筛选在重载和随机演员请求中保留`, { timeout: 45_000 }, async () => {
      const opened = await visit(browser, '/performers', viewport);
      const page = opened.page;
      try {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route('**/api/index?**', route => route.fulfill({ json: { items: [], has_more: false } }));
        await page.reload();
        const toggle = page.getByRole('button', { name: 'Actor genders', exact: true });
        await toggle.click();
        const menu = page.getByRole('menu', { name: 'Actor genders' });
        await menu.getByRole('menuitemcheckbox', { name: 'Male', exact: true }).click();
        assert.equal(await menu.getByRole('menuitemcheckbox', { name: 'Male', exact: true }).getAttribute('aria-checked'), 'false');
        await page.keyboard.press('Escape');
        const saved = await page.evaluate(() => localStorage.getItem('peach.actor-genders.v1'));
        assert.ok(saved && !JSON.parse(saved).includes('MALE'));
        await page.reload(); await toggle.click();
        assert.equal(await page.getByRole('menuitemcheckbox', { name: 'Male', exact: true }).getAttribute('aria-checked'), 'false');
        await page.keyboard.press('Escape');
        const requested = page.waitForRequest(request => {
          const url = new URL(request.url());
          return url.pathname === '/api/tops' && url.searchParams.has('genders');
        });
        await page.goto(new URL('/', page.url()).href);
        const url = new URL((await requested).url());
        assert.equal(url.searchParams.get('genders')?.split(',').includes('MALE'), false);
        assert.ok(url.searchParams.get('genders')?.includes('FEMALE'));
      } finally { await opened.close() }
    });
  }
});
