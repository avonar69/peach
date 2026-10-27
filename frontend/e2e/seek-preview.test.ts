import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, VIEWPORTS } from './harness.ts';
import { ITEM, openItemPage } from './item-fixture.ts';

describe('时间轴单格预览', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}: 独立抽帧通知显示进度并停止工作者`, async () => {
      const opened = await openItemPage(browser, `/assets/${ITEM.plain}`, viewport);
      const page = opened.page;
      let stopped = false;
      let speed = 'low';
      try {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route(url => url.pathname === '/api/thumbnail-jobs', async route => {
          if (route.request().method() === 'POST') {
            const body = route.request().postDataJSON();
            if (body.action === 'set_speed') speed = body.speed_mode;
            else { assert.deepEqual(body, { mode: 'off' }); stopped = true; }
          }
          await route.fulfill({ json: { status: stopped ? 'idle' : 'running', speed_mode: speed, total: 10, done: 2, current_frame: 55, current_frames: 100 } });
        });
        await page.goto(new URL('/data-cleanup', page.url()).href);
        const popup = page.getByRole('status', { name: 'Generating seek thumbnails', exact: true });
        await popup.waitFor();
        assert.match(await popup.innerText(), /55 of 100 frames/);
        const bounds = await popup.boundingBox();
        assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= viewport.width + 1);
        const card = page.getByRole('region', { name: 'Generating seek thumbnails', exact: true });
        await card.waitFor();
        assert.match(await card.innerText(), /55 of 100 frames/);
        await popup.locator('.processing-effort-trigger button').click();
        await page.getByRole('slider').press('ArrowRight');
        await page.waitForFunction(() => document.querySelector('[data-processing-dock] [data-speed="standard"]') !== null);
        assert.equal(speed, 'standard');
        await page.keyboard.press('Escape');
        assert.equal(await card.locator('[data-speed="standard"]').count(), 1);
        await popup.getByRole('button', { name: 'Stop thumbnail generation', exact: true }).click();
        await popup.waitFor({ state: 'hidden' });
        await card.waitFor({ state: 'hidden' });
        assert.equal(stopped, true);
      } finally { await opened.close(); }
    });
  }
  for (const viewport of VIEWPORTS) for (const resume of [0, 91]) {
    it(`${viewport.name}: 起播位置 ${resume} 保持完整表与末张表的单格裁切`, async () => {
      const opened = await openItemPage(browser, `/assets/${ITEM.plain}`, viewport);
      const page = opened.page;
      let release = () => {};
      const delayed = new Promise<void>(resolve => { release = resolve });
      try {
        await page.context().addInitScript(({ id, position }) => {
          localStorage.setItem(`peach.playback-position.v1:item:${id}`, String(position));
        }, { id: ITEM.plain, position: resume });
        await page.route(url => url.pathname === '/api/timeline', async route => {
          if (resume) await delayed;
          await route.fulfill({ json: { frames: 123, interval: 10, columns: 10, rows: 10 } });
        });
        await page.route(url => url.pathname === '/timeline', async route => {
          const rows = new URL(route.request().url()).searchParams.get('s') === '1' ? 3 : 10;
          await route.fulfill({ contentType: 'image/svg+xml', body:
            `<svg xmlns="http://www.w3.org/2000/svg" width="3200" height="${rows * 180}"><rect width="100%" height="100%" fill="#336699"/></svg>` });
        });
        const metadata = page.waitForResponse(response => new URL(response.url()).pathname === '/api/timeline');
        await page.reload();
        await page.locator('#stage .vjs-progress-control').waitFor();
        await page.waitForFunction(() => !!document.querySelector('#stage [data-player-seek-preview]'));
        await page.evaluate(() => document.querySelector('#stage video')?.dispatchEvent(new Event('loadedmetadata')));
        const move = async (ratio: number) => {
          await page.locator('#stage .vjs-progress-control').evaluate((element, fraction) => {
            const rect = element.getBoundingClientRect();
            element.dispatchEvent(new PointerEvent('pointermove', { pointerType: 'mouse', bubbles: true,
              clientX: rect.left + rect.width * fraction, clientY: rect.top }));
          }, ratio);
        };
        if (resume) {
          await move(.05);
          await page.waitForFunction(() => document.querySelector<HTMLImageElement>('#stage [data-player-seek-preview] img')?.src.includes('/poster?'));
          release();
        }
        assert.equal((await (await metadata).json()).frames, 123);
        for (const [ratio, rows] of [[.05, 10], [.95, 3]] as const) {
          await move(ratio);
          await page.waitForFunction(fraction => {
            const progress = document.querySelector<HTMLElement>('#stage .vjs-progress-control')!;
            const rect = progress.getBoundingClientRect();
            progress.dispatchEvent(new PointerEvent('pointermove', { pointerType: 'mouse', bubbles: true,
              clientX: rect.left + rect.width * fraction, clientY: rect.top }));
            return document.querySelector<HTMLImageElement>('#stage [data-player-seek-preview] img')?.src.includes('/timeline?');
          }, ratio, { timeout: 5000 });
          const image = page.locator('#stage [data-player-seek-preview] img');
          await image.evaluate(img => (img as HTMLImageElement).decode());
          const size = await image.evaluate(img => {
            const frame = img.parentElement!;
            return { imageWidth: img.getBoundingClientRect().width, imageHeight: img.getBoundingClientRect().height,
              frameWidth: frame.clientWidth, frameHeight: frame.clientHeight, overflow: getComputedStyle(frame).overflow,
              source: (img as HTMLImageElement).src, style: img.getAttribute('style'), maxWidth: getComputedStyle(img).maxWidth };
          });
          assert.ok(Math.abs(size.imageWidth / size.frameWidth - 10) < .05, JSON.stringify(size));
          assert.ok(Math.abs(size.imageHeight / size.frameHeight - rows) < .05, JSON.stringify(size));
          assert.equal(size.overflow, 'hidden');
        }
        await page.screenshot({ path: `../build/agent-verification/seek-preview-${viewport.name}-${resume}.png` });
      } finally { release(); await opened.close() }
    });
  }
});
