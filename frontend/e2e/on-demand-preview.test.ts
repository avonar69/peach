import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, requiredEnv, visit, VIEWPORTS } from './harness.ts';

describe('浏览器按需时间轴画面', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}: 真视频按需取帧，不启动采集，也不改变主播放器位置`, async () => {
      const requests: { path: string; query: string; method: string }[] = [];
      const opened = await visit(browser, `/assets/${requiredEnv('PEACH_E2E_ITEM')}`, viewport, async page => {
        await page.context().addInitScript(() => {
          localStorage.setItem('peach.settings.v1', JSON.stringify({ onDemandSeekPreviews: true, detailAutoplay: false }));
        });
        page.on('request', request => {
          const url = new URL(request.url());
          requests.push({ path: url.pathname, query: url.search, method: request.method() });
        });
      });
      const { page } = opened;
      try {
        await page.locator('#stage .vjs-progress-control').waitFor();
        await page.waitForFunction(() => (document.querySelector<HTMLVideoElement>('#stage video')?.readyState || 0) >= 1);
        const position = await page.evaluate(() => { const video = document.querySelector<HTMLVideoElement>('#stage video')!; video.pause(); return video.currentTime });
        await page.evaluate(() => {
          const bar = document.querySelector<HTMLElement>('#stage .vjs-progress-control')!;
          const rect = bar.getBoundingClientRect();
          bar.dispatchEvent(new PointerEvent('pointermove', { pointerType: 'mouse', bubbles: true, clientX: rect.left + rect.width / 2, clientY: rect.top }));
        });
        await page.waitForFunction(() => document.querySelector<HTMLImageElement>('#stage [data-player-seek-preview] img')?.src.startsWith('data:image/jpeg'));
        const frame = page.locator('#stage [data-player-seek-preview] img');
        await frame.evaluate(image => (image as HTMLImageElement).decode());
        assert.ok(await frame.evaluate(image => (image as HTMLImageElement).naturalWidth > 0));
        assert.ok(Math.abs(await page.locator('#stage video.vjs-tech').evaluate(video => (video as HTMLVideoElement).currentTime) - position) < .05);
        assert.ok(requests.some(row => row.path === '/stream' && row.query.includes('preview=true') && row.query.includes('native_play=true')));
        assert.equal(requests.filter(row => row.method === 'POST' && ['/api/thumbnail-jobs', '/api/library-processing'].includes(row.path)).length, 0);
        await page.locator('#stage .vjs-progress-control').dispatchEvent('pointerleave');
        await page.waitForFunction(() => document.querySelector<HTMLElement>('#stage [data-player-seek-preview]')?.hidden === true);
      } finally { await opened.close() }
    });
  }
});
