import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, requiredEnv, visit, VIEWPORTS } from './harness.ts';

describe('目录扫描策略、RSS 多选与触屏快进', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}: 忽略词重匹配保存设置并提交独立范围`, { timeout: 60_000 }, async () => {
      for (const mode of ['filename', 'stashdb'] as const) {
        const calls: { path: string; body: Record<string, unknown> }[] = [];
        const stage = mode === 'filename' ? 'filename_ignored' : 'stashdb_ignored';
        const settings = mode === 'filename' ? '/api/configuration/filename-matching' : '/api/configuration/stashdb/settings';
        const section = mode === 'filename' ? '这台电脑' : '来源与订阅';
        const opened = await visit(browser, '/settings/library?section=' + encodeURIComponent(section), viewport, async page => {
          await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
          await page.route(url => url.pathname === '/api/configuration', async route => {
            const original = await (await route.fetch()).json();
            await route.fulfill({ json: { ...original, editable: true,
              filename_matching: { actors: true, studios: true, ignore_terms: '!' },
              stashdb: { ...original.stashdb, enabled: true, api_key_set: true, ignore_terms: '!' },
            } });
          });
          await page.route(url => url.pathname === settings || url.pathname === '/api/library-processing' && url.search === '', async route => {
            if (route.request().method() !== 'POST') { await route.fallback(); return }
            const path = new URL(route.request().url()).pathname, body = route.request().postDataJSON();
            calls.push({ path, body });
            await route.fulfill({ json: path === settings ? { ...body, api_key_set: true }
              : { job_id: 'test-rematch', requested_stage: stage, status: 'running' } });
          });
        });
        try {
          const page = opened.page;
          const button = page.getByRole('button', { name: mode === 'filename' ? 'Rematch affected filenames' : 'Rematch affected files with StashDB', exact: true });
          await button.click();
          await page.waitForFunction(() => !document.querySelector('[data-action-busy="true"]'));
          assert.deepEqual(calls.map(call => call.path), [settings, '/api/library-processing']);
          assert.equal(calls[0]?.body.ignore_terms, '!');
          assert.equal(calls[1]?.body.stage, stage);
          assert.ok((await layout(page)).scrollWidth <= viewport.width + 1, JSON.stringify(await layout(page)));
          assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
        } finally { await opened.close() }
      }
    });
    it(`${viewport.name}: NZB 详情、图片与下载目的地`, { timeout: 45_000 }, async () => {
      const posts: string[] = [];
      const opened = await visit(browser, '/follow', viewport, async page => {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route(url => url.pathname === '/api/rss', route => route.fulfill({ json: {
          sources: [{ id: 1, name: 'DS' }], total: 1, offset: 0, providers: [], jobs: [], sabnzbd: { configured: true }, nzbget: { configured: true },
          items: [{ id: 1, source_id: 1, title: 'Example.Release.2160p', feed_name: 'DS', published_at: '2026-10-27T12:00:00Z',
            link: 'https://example.org/details/example', links: [{ kind: 'nzb', url: 'https://example.org/example.nzb?key=example' }],
            images: { main: { src: '/peach-logo.png', href: 'https://example.org/details/example' }, previews: [] } }],
        } }));
        await page.route('**/api/rss/sabnzbd', route => {
          posts.push(route.request().postData() || '');
          return route.fulfill({ json: { ok: true, ids: ['demo'] } });
        });
        await page.route('**/api/rss/nzbget', route => {
          posts.push(route.request().postData() || '');
          return route.fulfill({ json: { ok: true, ids: [123] } });
        });
      });
      try {
        const page = opened.page;
        await page.getByRole('heading', { name: 'Example.Release.2160p', exact: true }).waitFor();
        assert.equal(await page.getByRole('link', { name: 'Download NZB', exact: true }).getAttribute('href'), 'https://example.org/example.nzb?key=example');
        assert.equal(await page.getByRole('link', { name: 'View page', exact: true }).getAttribute('href'), 'https://example.org/details/example');
        assert.ok(await page.getByRole('img', { name: 'Example.Release.2160p', exact: true }).isVisible());
        await page.getByRole('button', { name: 'Send to SABnzbd', exact: true }).click();
        assert.equal(await page.getByRole('button', { name: 'Sent to SABnzbd', exact: true }).isDisabled(), true);
        assert.deepEqual(JSON.parse(posts[0]!), { entry_id: 1, link_index: 0 });
        await page.getByRole('button', { name: 'Send to NZBGet', exact: true }).click();
        assert.equal(await page.getByRole('button', { name: 'Sent to NZBGet', exact: true }).isDisabled(), true);
        assert.equal(posts.length, 2);
        assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
        assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
      } finally { await opened.close() }
    });
    it(`${viewport.name}: SABnzbd 配置与连接回执`, { timeout: 45_000 }, async () => {
      const posts: { url: string; body: Record<string, unknown> }[] = [];
      const opened = await visit(browser, '/settings/downloads', viewport, async page => {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route('**/api/configuration/sabnzbd**', route => {
          if (route.request().method() === 'POST') {
            posts.push({ url: new URL(route.request().url()).pathname, body: route.request().postDataJSON() });
            return route.fulfill({ json: { ok: true } });
          }
          return route.fulfill({ json: { url: 'http://sabnzbd:8080/api', category: 'movies', configured: true, available: true } });
        });
        await page.route('**/api/configuration/nzbget**', route => {
          if (route.request().method() === 'POST') {
            posts.push({ url: new URL(route.request().url()).pathname, body: route.request().postDataJSON() });
            return route.fulfill({ json: { ok: true } });
          }
          return route.fulfill({ json: { url: 'http://nzbget:6789/jsonrpc', username: 'demo', category: 'movies', configured: true, available: true } });
        });
      });
      try {
        const page = opened.page, form = page.getByRole('form', { name: 'SABnzbd', exact: true });
        await form.locator('input').nth(2).fill('videos');
        await form.getByRole('button', { name: 'Save SABnzbd settings', exact: true }).click();
        await form.getByRole('button', { name: 'Test connection', exact: true }).click();
        await form.getByRole('status').filter({ hasText: 'SABnzbd connection successful.' }).waitFor();
        assert.equal(posts[0]?.body.category, 'videos');
        assert.equal(posts[0]?.body.api_key, '');
        assert.equal(posts[1]?.url, '/api/configuration/sabnzbd/check');
        const nzb = page.getByRole('form', { name: 'NZBGet', exact: true });
        await nzb.locator('input[type="password"]').fill('example-password');
        await nzb.getByRole('button', { name: 'Save NZBGet settings', exact: true }).click();
        await nzb.getByRole('button', { name: 'Test connection', exact: true }).click();
        await nzb.getByRole('status').filter({ hasText: 'NZBGet connection successful.' }).waitFor();
        assert.equal(posts[2]?.body.username, 'demo');
        assert.equal(posts[2]?.body.password, 'example-password');
        assert.equal(posts[3]?.url, '/api/configuration/nzbget/check');
        assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
        assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
      } finally { await opened.close() }
    });
    it(`${viewport.name}: 嵌套目录分别显示开关和默认零小时`, { timeout: 45_000 }, async () => {
      let saved: { media_sources?: { scan_updates: boolean; scan_hours: number }[] } | undefined;
      const opened = await visit(browser, '/settings/library?section=' + encodeURIComponent('这台电脑'), viewport, async page => {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route('**/api/configuration', async route => {
          if (route.request().method() === 'POST') {
            saved = route.request().postDataJSON();
            await route.fulfill({ json: { saved: true, revision: 'test', url: page.url() } }); return;
          }
          const original = await (await route.fetch()).json();
          await route.fulfill({ json: { ...original, editable: true, windows: false, media_sources: [
            { location: 'local', root: 'R:\\videos', path: '/videos', library: 'Archive', cost: 'free' },
            { location: 'local', root: 'R:\\videos\\new', path: '/videos/new', library: 'New', cost: 'free' },
          ] } });
        });
      });
      const page = opened.page;
      try {
        const form = page.getByRole('form', { name: 'Media folder', exact: true });
        assert.equal(await form.getByRole('checkbox', { name: 'Scan for updates in folder 1', exact: true }).isChecked(), true);
        const timer = form.locator('input[type="number"]').nth(1);
        assert.equal(await timer.inputValue(), '0');
        await form.locator('[data-folder-row]').nth(0).getByText('Scan for Updates', { exact: true }).click();
        await timer.fill('2');
        assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
        const response = page.waitForResponse(value => value.request().method() === 'POST' && new URL(value.url()).pathname === '/api/configuration');
        await form.getByRole('button', { name: 'Save configuration', exact: true }).click(); await response;
        assert.equal(saved?.media_sources?.[0]?.scan_updates, false);
        assert.equal(saved?.media_sources?.[0]?.scan_hours, 0);
        assert.equal(saved?.media_sources?.[1]?.scan_hours, 2);
      } finally { await opened.close() }
    });
    it(`${viewport.name}: Following 保留多选 RSS 来源且可恢复全部`, { timeout: 45_000 }, async () => {
      const opened = await visit(browser, '/follow', viewport, async page => {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route(url => url.pathname === '/api/rss', async route => {
          const selected = new URL(route.request().url()).searchParams.get('sources');
          const sources = [{ id: 1, name: 'Feed A', last_fetched_at: '2026-10-27T10:00:00Z' }, { id: 2, name: 'Feed B' }];
          const items = sources.filter(source => !selected || selected.split(',').includes(String(source.id)))
            .map(source => ({ id: source.id, source_id: source.id, title: `Post ${source.name}`, feed_name: source.name, published_at: null, links: [] }));
          await route.fulfill({ json: { sources, items, total: items.length, offset: 0, jobs: [], providers: [] } });
        });
        await page.route('**/api/follow/check', route => route.fulfill({ json: route.request().method() === 'POST'
          ? { job_id: 'test-refresh', status: 'running' } : { status: 'idle' } }));
        await page.route('**/api/rss/check', route => route.fulfill({ json: { ok: true, job_id: 'test-rss-refresh' } }));
      });
      const page = opened.page;
      try {
        await page.getByRole('button', { name: 'RSS feeds', exact: true }).click();
        await page.getByRole('menuitemcheckbox', { name: 'Feed B', exact: true }).click();
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => JSON.parse(localStorage.getItem('peach.rss-selected-feeds.v1') || '[]').join() === '1');
        await page.getByRole('heading', { name: 'Post Feed A', exact: true }).waitFor();
        await page.getByRole('heading', { name: 'Post Feed B', exact: true }).waitFor({ state: 'hidden' });
        await page.reload();
        await page.getByRole('button', { name: 'RSS feeds', exact: true }).click();
        assert.equal(await page.getByRole('menuitemcheckbox', { name: 'Feed B', exact: true }).getAttribute('aria-checked'), 'false');
        await page.getByRole('menuitem', { name: 'All RSS feeds', exact: true }).click();
        await page.getByRole('heading', { name: 'Post Feed B', exact: true }).waitFor();
        assert.ok((await page.locator('[data-follow-updated]').textContent())?.includes('Last updated:'));
        const creatorRefresh = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/follow/check');
        await page.getByRole('button', { name: 'Refresh all', exact: true }).click();
        const refreshed = await creatorRefresh;
        assert.equal(refreshed.postDataJSON().include_rss, true);
        assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      } finally { await opened.close() }
    });
  }
  it('mobile: 原生全屏不可用时所有视图保留全屏入口', { timeout: 45_000 }, async () => {
    const opened = await visit(browser, `/assets/${requiredEnv('PEACH_E2E_ITEM')}`, VIEWPORTS[1]!, async page => {
      await page.context().addInitScript(() => {
        localStorage.setItem('peach.settings.v1', JSON.stringify({ detailAutoplay: false }));
        Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, value: false });
      });
    });
    const page = opened.page;
    try {
      const fullscreen = page.locator('#stage .vjs-fullscreen-control');
      await fullscreen.waitFor({ state: 'visible' });
      await page.locator('#stage [data-player-expand]').click();
      assert.equal(await fullscreen.isVisible(), true);
      await page.locator('#stage [data-player-theater]').click();
      assert.equal(await fullscreen.isVisible(), true);
      await fullscreen.click();
      await page.locator('#stage [data-peach-full-window]').waitFor();
      assert.ok((await layout(page)).scrollWidth <= VIEWPORTS[1]!.width + 1);
      await page.screenshot({ path: '../build/agent-verification/mobile-fullscreen-fallback.png' });
      await fullscreen.click();
      await page.locator('#stage [data-peach-full-window]').waitFor({ state: 'hidden' });
    } finally { await opened.close() }
  });
  it('mobile: 左右双击使用小步长并保持暂停', { timeout: 45_000 }, async () => {
    const opened = await visit(browser, `/assets/${requiredEnv('PEACH_E2E_ITEM')}`, VIEWPORTS[1]!, async page => {
      await page.context().addInitScript(() => localStorage.setItem('peach.settings.v1', JSON.stringify({ detailAutoplay: false, playerSeek: {
        smallForward: { seconds: 1, shortcut: 'ArrowRight' }, smallRewind: { seconds: 1, shortcut: 'ArrowLeft' },
      } })));
    });
    const page = opened.page, video = page.locator('#stage video.vjs-tech');
    try {
      await video.waitFor({ state: 'attached' });
      const fullscreen = page.locator('#stage .vjs-fullscreen-control');
      await fullscreen.waitFor({ state: 'visible' });
      const controlBox = await fullscreen.boundingBox(), stageBox = await page.locator('#stage').boundingBox();
      assert.ok(controlBox && stageBox && controlBox.x + controlBox.width <= stageBox.x + stageBox.width + 1);
      await fullscreen.click();
      await page.waitForFunction(() => !!document.fullscreenElement);
      await fullscreen.click();
      await page.waitForFunction(() => !document.fullscreenElement);
      await page.waitForFunction(() => (document.querySelector<HTMLVideoElement>('#stage video.vjs-tech')?.duration || 0) > 1.5);
      await video.evaluate(node => {
        const media = node as HTMLVideoElement; media.pause();
        media.currentTime = .2;
        media.dispatchEvent(new Event('loadedmetadata'));
      });
      const box = await video.boundingBox(); assert.ok(box);
      const tap = (side: number) => page.touchscreen.tap(box.x + box.width * side, box.y + box.height / 2);
      await tap(.8); await tap(.8);
      await page.waitForFunction(() => Math.abs((document.querySelector<HTMLVideoElement>('#stage video.vjs-tech')?.currentTime || 0) - 1.2) < .02);
      await tap(.2); await tap(.2);
      await page.waitForFunction(() => Math.abs((document.querySelector<HTMLVideoElement>('#stage video.vjs-tech')?.currentTime || 0) - .2) < .02);
      assert.equal(await video.evaluate(node => (node as HTMLVideoElement).paused), true);
      assert.equal(await page.evaluate(() => !!document.fullscreenElement), false);
    } finally { await opened.close() }
  });
});
