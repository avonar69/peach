/* RSS 下载图标、直链、容器目录与凭据隔离的桌面和手机验证。 */
import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, visit, VIEWPORTS } from './harness.ts';
import { stubServer } from './settings-fixture.ts';

describe('RSS and debrid downloads', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: illustrated posts keep every preview and save the per-feed link filter`, async () => {
    const posts: Array<Record<string, unknown>> = [];
    const state = { providers: [{ id: 'alldebrid', label: 'AllDebrid', configured: true, download_folder: '', hosts: ['rg.to'] }],
      sources: [{ id: 1, name: 'Example RSS', enabled: true, interval_minutes: 360, hide_unsupported: false }],
      items: [{ id: 1, source_id: 1, title: 'Studio - Example Actor', feed_name: 'Example RSS', published_at: '2026-10-25T01:32:24Z',
        description: 'This prose must stay hidden.',
        images: { main: { src: 'https://images.example.org/main.webp', href: 'https://images.example.org/main' },
          previews: [{ src: 'https://images.example.org/preview.webp', href: 'https://images.example.org/full-preview' },
            { src: 'https://images.example.org/preview2.webp', href: 'https://images.example.org/full-preview2' }] },
        links: [{ url: 'https://unsupported.example.org/page', kind: 'link' }, { url: 'https://rg.to/file/example', kind: 'link' }] }],
      jobs: [], total: 1, offset: 0 };
    const opened = await visit(browser, '/subscriptions?tab=rss', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/library-processing', route => route.fulfill({ json: { status: 'idle' } }));
      await page.route('https://images.example.org/**', route => route.fulfill({ contentType: 'image/svg+xml',
        body: route.request().url().includes('main')
          ? '<svg xmlns="http://www.w3.org/2000/svg" width="622" height="350"><rect width="622" height="350" fill="#909090"/></svg>'
          : '<svg xmlns="http://www.w3.org/2000/svg" width="103" height="200"><rect width="103" height="200" fill="#aaaaaa"/></svg>' }));
      await page.route('**/api/rss**', async route => {
        if (route.request().method() === 'POST') {
          const body = route.request().postDataJSON(); posts.push(body);
          if (body.action === 'filter') state.sources[0].hide_unsupported = body.hide_unsupported;
          if (body.action === 'schedule') Object.assign(state.sources[0], { enabled: body.enabled, interval_minutes: body.interval_minutes });
          await route.fulfill({ json: { ok: true, id: 'prepared' } });
        } else await route.fulfill({ json: state });
      });
    });
    try {
      const page = opened.page, article = page.locator('article');
      const interval = page.getByRole('spinbutton', { name: 'Update interval for Example RSS (hours)' });
      assert.equal(await interval.inputValue(), '6');
      await interval.fill('2');
      await page.getByRole('button', { name: 'Save interval', exact: true }).click();
      await page.getByText('Automatic updates', { exact: true }).click();
      await article.locator('img').first().waitFor();
      await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>('article img')].every(image => image.complete && image.naturalWidth > 0));
      assert.equal(await article.locator('img').count(), 3);
      assert.equal(await article.locator('a[href="https://images.example.org/full-preview"]').count(), 1);
      assert.equal(await article.locator('a[href="https://images.example.org/full-preview2"]').count(), 1);
      assert.ok(!(await article.innerText()).includes('This prose must stay hidden.'));
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        const geometry = await layout(page);
        assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
        await article.screenshot({ path: `../build/agent-verification/rss-post-${viewport.name}-${scheme}.png` });
      }
      await page.getByText('Hide unsupported links', { exact: true }).click();
      await article.locator('a[href="https://unsupported.example.org/page"]').waitFor({ state: 'detached' });
      await page.getByRole('button', { name: 'Download with AllDebrid', exact: true }).click();
      assert.ok(posts.some(body => body.action === 'filter' && body.hide_unsupported === true));
      assert.ok(posts.some(body => body.link_index === 1));
      await page.reload();
      await article.locator('img').first().waitFor();
      assert.equal(await interval.inputValue(), '2');
      assert.equal(await page.getByRole('switch', { name: 'Enable Example RSS', exact: true }).isChecked(), false);
      assert.equal(await article.locator('a[href="https://unsupported.example.org/page"]').count(), 0);
      await page.getByRole('switch', { name: /Hide unsupported links/ }).press('Space');
      await article.locator('a[href="https://unsupported.example.org/page"]').waitFor();
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: Following All includes RSS posts and download actions`, async () => {
    const opened = await visit(browser, '/', viewport);
    const page = opened.page;
    await page.route(url => url.pathname === '/api/follow', route => route.fulfill({ json: {
      ok: true, sources: [], groups: [], counts: {}, facets: {}, author_aliases: [], rss_count: 1, offset: 0, has_more: false,
    } }));
    await page.route('**/api/rss**', route => route.fulfill({ json: {
      providers: [{ id: 'alldebrid', label: 'AllDebrid', configured: true, download_folder: '', hosts: ['rg.to'] }],
      sources: [{ id: 1, name: 'Example RSS', enabled: true }], jobs: [], total: 1, offset: 0,
      items: [{ id: 1, source_id: 1, title: 'An RSS post in Following', feed_name: 'Example RSS', published_at: null,
        links: [{ url: 'https://rg.to/file/example', kind: 'link' }], images: {} }],
    } }));
    try {
      await page.goto(new URL('/follow', page.url()).href);
      const rss = page.locator('[data-follow-rss]');
      await rss.getByText('An RSS post in Following', { exact: true }).waitFor();
      await page.waitForFunction(() => document.querySelector('[data-follow-readout]')?.textContent?.includes('Showing 1'));
      assert.equal(await rss.getByRole('button', { name: 'Download with AllDebrid', exact: true }).count(), 1);
      assert.equal(await rss.locator('form').count(), 0);
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      await page.screenshot({ path: `../build/agent-verification/rss-follow-all-${viewport.name}.png`, fullPage: false });
      await page.locator('[data-follow-filter="new"]').click();
      await rss.waitFor({ state: 'detached' });
      await page.locator('[data-follow-filter=""]').click();
      await rss.getByText('An RSS post in Following', { exact: true }).waitFor();
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: RSS link icons prepare and download to the configured folder`, async () => {
    const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
    const source = { url: 'https://rg.to/file/example', kind: 'link' };
    const state = { providers: [{ id: 'alldebrid', label: 'AllDebrid', configured: true, download_folder: '/downloads', hosts: ['rg.to'] }],
      sources: [{ id: 1, name: 'Example RSS', enabled: true, last_error: null }],
      items: [{ id: 1, title: 'A new studio video without a release code', feed_name: 'Example RSS', published_at: '2026-10-24T10:00:00Z',
        links: [source, { url: 'https://unsupported.example.org/item', kind: 'link' }] }],
      jobs: [] as Array<Record<string, unknown>>, total: 1, offset: 0 };
    const opened = await visit(browser, '/subscriptions?tab=rss', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/rss**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() === 'POST') {
          const body = route.request().postDataJSON(); posts.push({ path, body });
          if (path.endsWith('/resolve')) state.jobs = [{ id: 'ready-job', kind: 'resolve', provider: 'alldebrid', entry_id: 1,
            source, status: 'ready', files: [{ filename: 'example.mp4', url: 'https://cdn.example.org/example.mp4', size: 1000 }] }];
          if (path.endsWith('/download') || (path.endsWith('/resolve') && body.auto_download)) state.jobs.push({ id: 'local-job', kind: 'download', provider: 'alldebrid', entry_id: 1,
            status: 'downloading', filename: 'example.mp4', bytes: 500, total: 1000 });
          await route.fulfill({ json: { id: 'ready-job', ok: true } });
        } else await route.fulfill({ json: state });
      });
    });
    try {
      const page = opened.page;
      const icon = page.getByRole('button', { name: 'Download with AllDebrid', exact: true });
      await icon.waitFor({ timeout: 10000 }).catch(async error => {
        assert.fail(`${String(error)}\n${(await page.locator('body').innerText()).slice(0, 4000)}\n${JSON.stringify(opened.problems)}`);
      });
      assert.equal(await icon.count(), 1);
      assert.ok((await icon.locator('..').innerText()).includes('rg.to'));
      await icon.click();
      await page.locator('article').getByRole('progressbar', { name: 'Download progress', exact: true }).waitFor();
      assert.ok(posts.some(post => post.path === '/api/rss/resolve' && post.body.entry_id === 1 && post.body.link_index === 0));
      assert.ok(posts.some(post => post.path === '/api/rss/resolve' && post.body.auto_download === true));
      assert.equal(await page.getByRole('link', { name: 'example.mp4', exact: true }).count(), 1);
      const geometry = await layout(page);
      assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });

  for (const viewport of VIEWPORTS) it(`${viewport.name}: download provider cards save a container folder and show connection success`, async () => {
    const posts: Array<Record<string, unknown>> = [];
    const providers = [{ id: 'alldebrid', label: 'AllDebrid', configured: true, download_folder: '', hosts: ['rg.to'], auto_import: false, max_concurrent_downloads: 3 },
      { id: 'realdebrid', label: 'Real-Debrid', configured: false, download_folder: '', hosts: [], auto_import: false, max_concurrent_downloads: 3 }];
    const opened = await visit(browser, '/settings/downloads', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/configuration/debrid**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() === 'POST') {
          const body = route.request().postDataJSON(); posts.push(body);
          if (path.endsWith('/settings')) Object.assign(providers[0], { download_folder: body.download_folder, auto_import: body.auto_import, max_concurrent_downloads: body.max_concurrent_downloads });
          await route.fulfill({ json: path.endsWith('/check') ? { ok: true, account: 'Example account' } : { providers } });
        } else await route.fulfill({ json: { providers } });
      });
    });
    try {
      const page = opened.page;
      const region = page.getByRole('form', { name: 'AllDebrid', exact: true });
      await region.getByRole('textbox', { name: /download folder/i }).fill('/downloads/videos', { timeout: 10000 }).catch(async error => {
        assert.fail(`${String(error)}\n${await region.ariaSnapshot()}\n${JSON.stringify(opened.problems)}`);
      });
      await region.getByText('Scan and import after download', { exact: true }).click();
      await region.locator('[name="max_concurrent_downloads"]').fill('10');
      await region.getByRole('button', { name: 'Save debrid settings', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[data-action-busy="true"]'));
      await region.getByRole('button', { name: 'Test connection', exact: true }).click();
      await region.getByRole('status').filter({ hasText: 'Connected to AllDebrid.' }).waitFor();
      assert.ok(posts.some(body => body.download_folder === '/downloads/videos'));
      assert.ok(posts.some(body => body.auto_import === true));
      assert.ok(posts.some(body => body.max_concurrent_downloads === 10));
      await page.reload();
      assert.equal(await region.getByRole('switch', { name: /Automatic import for AllDebrid/ }).isChecked(), true);
      assert.equal(await region.locator('[name="max_concurrent_downloads"]').inputValue(), '10');
      const geometry = await layout(page);
      assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
});
