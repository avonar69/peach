import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, visit, VIEWPORTS } from './harness.ts';
import { stubServer } from './settings-fixture.ts';

describe('RSS archive and debrid progress', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; browser = await launch() });
  after(async () => { await browser?.close() });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: retention persists and the task popup follows navigation and import`, async () => {
    const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
    const state = {
      providers: [{ id: 'alldebrid', label: 'AllDebrid', configured: true, download_folder: '/downloads', hosts: [] }],
      sources: [{ id: 1, name: 'Example RSS', enabled: true, interval_minutes: 360,
        rss_retention_count: null as number | null, rss_retention_unit: 'days' }],
      items: [], total: 0, offset: 0,
      jobs: [{ id: 'file-one', entry_id: 1, provider: 'alldebrid', kind: 'download', status: 'downloading',
        filename: 'Example studio video.mp4', bytes: 25 * 1024 * 1024, total: 100 * 1024 * 1024, import_state: '', import_error: '' }],
    };
    const opened = await visit(browser, '/subscriptions?tab=rss', viewport, async page => {
      await stubServer(page);
      await page.addInitScript(() => localStorage.setItem('peach.debrid-progress', JSON.stringify(['file-one'])));
      await page.route('**/api/library-processing', route => route.fulfill({ json: { status: 'idle' } }));
      await page.route('**/api/rss**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() === 'POST') {
          const body = route.request().postDataJSON(); posts.push({ path, body });
          if (body.action === 'retention') Object.assign(state.sources[0], { rss_retention_count: body.count, rss_retention_unit: body.unit });
          if (path.endsWith('/import')) state.jobs[0].import_state = 'queued';
          if (path.endsWith('/cancel')) state.jobs[0].import_state = 'cancelled';
          await route.fulfill({ json: { ok: true } });
        } else await route.fulfill({ json: state });
      });
    });
    const { page } = opened;
    try {
      const popup = page.locator('[data-processing-dock][aria-label="Debrid downloads"]');
      await popup.waitFor();
      assert.equal(await popup.getByRole('progressbar', { name: 'Download progress' }).getAttribute('value'), String(25 * 1024 * 1024));
      const retention = page.locator('form').filter({ has: page.getByRole('button', { name: 'Save retention', exact: true }) });
      const unit = retention.locator('[aria-haspopup="listbox"]');
      await unit.scrollIntoViewIfNeeded();
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await unit.click();
      await page.screenshot({ path: `../build/agent-verification/retention-open-${viewport.name}.png` });
      await page.getByRole('option', { name: 'Months', exact: true }).click({ timeout: 5000 }).catch(async error => {
        assert.fail(`${String(error)}\n${(await page.locator('body').ariaSnapshot()).slice(-9000)}`);
      });
      await page.getByRole('spinbutton', { name: /Retention amount for Example RSS/ }).fill('3', { timeout: 5000 }).catch(async error => {
        assert.fail(`${String(error)}\n${await retention.ariaSnapshot()}\n${JSON.stringify(await retention.locator('input').evaluateAll(inputs => inputs.map(input => ({ type: input.type, label: input.getAttribute('aria-label'), labelledby: input.getAttribute('aria-labelledby') }))))}`);
      });
      await Promise.all([
        page.waitForResponse(response => new URL(response.url()).pathname === '/api/rss/source' && response.request().method() === 'POST'),
        retention.getByRole('button', { name: 'Save retention', exact: true }).click(),
      ]);
      await page.reload();
      await popup.waitFor();
      assert.equal(await page.getByRole('spinbutton', { name: /Retention amount for Example RSS/ }).inputValue(), '3');
      await page.goto(new URL('/data-cleanup', page.url()).href);
      await popup.waitFor();
      state.jobs[0].status = 'complete'; state.jobs[0].bytes = state.jobs[0].total; state.jobs[0].import_state = 'queued';
      await popup.getByText('Import queued', { exact: true }).waitFor();
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        const geometry = await layout(page);
        assert.ok(geometry.scrollWidth <= geometry.viewportWidth + 1, JSON.stringify(geometry));
        assert.deepEqual(geometry.offenders, []);
        await popup.screenshot({ path: `../build/agent-verification/debrid-popup-${viewport.name}-${scheme}.png` });
      }
      state.jobs[0].import_state = 'failed'; state.jobs[0].import_error = 'Import needs attention';
      await popup.getByRole('button', { name: 'Retry import', exact: true }).click();
      await popup.getByRole('button', { name: 'Cancel import', exact: true }).click();
      await popup.getByText('Import cancelled', { exact: true }).waitFor();
      assert.equal(state.jobs[0].status, 'complete');
      assert.ok(posts.some(post => post.body.action === 'retention' && post.body.count === 3 && post.body.unit === 'months'));
      assert.ok(posts.some(post => post.path === '/api/rss/import'));
      assert.ok(posts.some(post => post.path === '/api/rss/cancel'));
      assert.deepEqual(opened.problems, []);
    } finally { await opened.close() }
  });
});
