/* StashDB 复核与播放器偏好：合成馆藏、假 API，不访问真实来源。 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, requiredEnv, visit, VIEWPORTS } from './harness.ts';
import { stubServer } from './settings-fixture.ts';

const screenshots = process.env.PEACH_E2E_SCREENSHOTS || path.resolve('../build/stashdb-playback-screenshots');
const remote = '11111111-1111-4111-8111-111111111111';
describe('StashDB review and playback preferences', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; await mkdir(screenshots, { recursive: true }); browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: source settings, smart-match evidence and scene review`, { timeout: 120_000 }, async () => {
    const posts: Array<{ action: string; body: Record<string, unknown> }> = [];
    let queued = true;
    const queuedPreview = { token: 'test-review-token', review_required: true, candidates: [{ id: remote,
      title: 'Queued matched scene', score: .9, reasons: ['Studio matches'], url: `https://stashdb.org/scenes/${remote}` }] };
    let policy = { enabled: false, actor_images: true, scene_images: true, correct_cast: false, auto_apply: false,
      api_key_set: true, endpoint: 'https://stashdb.org/graphql' };
    const opened = await visit(browser, '/settings/subscriptions', viewport, async page => {
      page.setDefaultTimeout(12_000);
      await stubServer(page);
      await page.route('**/api/review*', async route => {
        const data = await (await route.fetch()).json();
        data.counts = { stashdb: queued ? 1 : 0 };
        await route.fulfill({ json: data });
      });
      await page.route('**/api/configuration', async route => {
        const data = await (await route.fetch()).json(); data.stashdb = policy;
        await route.fulfill({ json: data });
      });
      await page.route('**/api/configuration/stashdb/**', async route => {
        const action = new URL(route.request().url()).pathname.split('/').at(-1)!;
        const body = route.request().postDataJSON() || {};
        if (route.request().method() === 'POST') posts.push({ action, body });
        if (action === 'apply' || action === 'dismiss') queued = false;
        const json = action === 'library' ? [{ id: 1, label: 'Example library scene' }]
          : action === 'review' ? queued ? [{ id: 1, label: 'Queued library scene', preview: queuedPreview }] : []
          : action === 'settings' ? (policy = { ...policy, ...body })
          : action === 'preview' ? { token: 'test-review-token', review_required: false,
            candidates: [{ id: remote, title: 'Example matched scene', date: '2026-10-22', studio: 'Example Studio', actors: ['Jane Doe'],
              score: .95, reasons: ['Studio matches', 'Release date matches', 'Actor names or aliases match'], url: `https://stashdb.org/scenes/${remote}` }] }
          : action === 'check' ? { ok: true, account: 'Test account' } : { ok: true, actor_photos: 1, scene_picture: true };
        await route.fulfill({ json });
      });
      await page.route('**/api/library-processing', async route => {
        if (route.request().method() === 'POST') posts.push({ action: 'scan', body: route.request().postDataJSON() });
        await route.fulfill({ json: { status: 'running', job_id: 'stashdb-scan', stage: 'StashDB matching' } });
      });
    });
    try {
      const page = opened.page;
      await page.getByLabel('StashDB API key', { exact: true }).waitFor();
      await page.getByLabel('Ignore filename text when matching', { exact: true }).fill('!\n[extra]');
      await page.getByLabel('Minimum automatic match confidence (%)', { exact: true }).fill('90');
      for (const label of ['Skip previously failed or unmatched StashDB searches', 'Only match newly added media']) {
        await page.getByRole('switch', { name: label, exact: true }).locator('xpath=ancestor::label[1]').click();
      }
      const correction = page.getByRole('switch', { name: 'Correct filename actor assignments using matched StashDB scenes', exact: true }).locator('xpath=ancestor::label[1]');
      await correction.evaluate(node => node.scrollIntoView({ block: 'center' }));
      await correction.click();
      await page.getByRole('switch', { name: 'Enable StashDB during metadata scans', exact: true }).locator('xpath=ancestor::label[1]').click();
      await page.getByRole('button', { name: 'Save StashDB settings', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[data-action-busy="true"]'));
      await page.getByRole('button', { name: 'Test connection', exact: true }).click();
      await page.getByText('Test account', { exact: true }).waitFor();
      await page.getByRole('status').filter({ hasText: 'StashDB connection successful.' }).first().waitFor();
      await page.route('**/api/configuration/stashdb/check', route => route.fulfill({ json: { ok: true, account: '' } }));
      await page.getByRole('button', { name: 'Test connection', exact: true }).click();
      await page.waitForFunction(() => {
        const result = document.querySelector('p[role="status"]');
        return result?.textContent?.trim() === 'StashDB connection successful.';
      });
      assert.ok(posts.some(post => post.action === 'settings' && post.body.correct_cast === true && post.body.auto_apply === false));
      assert.ok(posts.some(post => post.action === 'settings' && post.body.ignore_terms === '!\n[extra]' && post.body.minimum_confidence === 90));
      assert.ok(posts.some(post => post.action === 'settings' && post.body.skip_failed === true && post.body.only_new_media === true));
      assert.ok(posts.every(post => !Object.hasOwn(post.body, 'api_key')));
      await page.getByRole('button', { name: 'Run metadata scan with StashDB', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[data-action-busy="true"]'));
      assert.ok(posts.some(post => post.action === 'scan' && post.body.stage === 'metadata'));
      await page.screenshot({ path: path.join(screenshots, `stashdb-settings-${viewport.name}.png`), fullPage: true });
      await page.getByRole('link', { name: 'Review StashDB matches', exact: true }).click();
      await page.getByRole('tab', { name: /StashDB matches/ }).waitFor();
      assert.match(page.url(), /review\?category=stashdb/);
      await page.getByRole('button', { name: 'Queued library scene', exact: true }).waitFor();
      await page.getByRole('button', { name: 'Find library items', exact: true }).click();
      await page.getByRole('button', { name: 'Example library scene', exact: true }).click();
      await page.getByRole('button', { name: 'Preview StashDB matches', exact: true }).click();
      await page.getByText('Release date matches', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Apply selected match', exact: true }).click();
      await page.getByRole('dialog', { name: 'Apply StashDB match', exact: true }).getByRole('button', { name: 'Apply match', exact: true }).click();
      await page.waitForFunction(() => ![...document.querySelectorAll('dialog[open]')].some(dialog => dialog.textContent?.includes('Apply StashDB match')));
      assert.ok(posts.some(post => post.action === 'apply' && post.body.asset_id === 1 && post.body.stashdb_id === remote && post.body.token === 'test-review-token'));
      queued = true;
      await page.getByRole('button', { name: 'Review matches from metadata scans', exact: true }).click();
      await page.getByRole('button', { name: 'Queued library scene', exact: true }).click();
      await page.getByRole('button', { name: 'Dismiss scene matches', exact: true }).click();
      await page.getByText('No StashDB matches are waiting for review.', { exact: true }).waitFor();
      assert.ok(posts.some(post => post.action === 'dismiss' && post.body.asset_id === 1 && post.body.token === 'test-review-token'));
      await page.goto(new URL('/data-cleanup', page.url()).href);
      await page.route('**/api/libraries', route => route.fulfill({ json: { libraries: [{ id: 'test', name: 'Test library', icon: 'local', metered: false }] } }));
      await page.reload();
      await page.getByRole('button', { name: 'Start repair', exact: true }).click();
      const repairDialog = page.getByRole('dialog', { name: /Repair media library/ });
      await repairDialog.waitFor();
      assert.doesNotMatch(await repairDialog.innerText(), /[\u3400-\u9fff]/);
      await page.screenshot({ path: path.join(screenshots, `repair-translated-${viewport.name}.png`), fullPage: true });
      await repairDialog.getByRole('button', { name: 'Cancel', exact: true }).click();
      const manualReview = page.locator('[data-cleanup-go="review"]');
      await manualReview.getByText('0 items to be reviewed', { exact: true }).waitFor();
      queued = true;
      await page.reload();
      await manualReview.getByText('1 items to be reviewed', { exact: true }).waitFor();
      await manualReview.click();
      await page.getByRole('tab', { name: /StashDB matches.*1/ }).waitFor();
      assert.ok((await layout(page)).scrollWidth <= viewport.width);
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
      await page.screenshot({ path: path.join(screenshots, `stashdb-${viewport.name}.png`), fullPage: true });
    } finally { await opened.close(); }
  });

  for (const viewport of VIEWPORTS) it(`${viewport.name}: four seek preferences and optional wheel volume`, { timeout: 120_000 }, async () => {
    const opened = await visit(browser, `/assets/${requiredEnv('PEACH_E2E_ITEM')}`, viewport, async page => {
      page.setDefaultTimeout(12_000);
      await stubServer(page);
      await page.addInitScript(() => {
        const saved = JSON.parse(localStorage.getItem('peach.settings.v1') || '{}');
        if (typeof saved.miniplayer !== 'boolean') localStorage.setItem('peach.settings.v1', JSON.stringify({ ...saved, detailAutoplay: false, miniplayer: false }));
      });
    });
    try {
      const page = opened.page, video = page.locator('#stage video.vjs-tech');
      await video.waitFor({ state: 'attached' });
      await page.waitForFunction(() => (document.querySelector('#stage video') as HTMLVideoElement)?.readyState >= 1);
      await video.evaluate((node: HTMLVideoElement) => {
        node.pause(); Object.defineProperty(node, 'duration', { configurable: true, value: 1000 });
        Object.defineProperty(node, 'currentTime', { configurable: true, writable: true, value: 100 });
      });
      for (const [key, expected] of [['ArrowUp', 160], ['ArrowDown', 40], ['ArrowRight', 110], ['ArrowLeft', 90]] as const) {
        await video.evaluate((node: HTMLVideoElement) => { node.currentTime = 100; });
        await page.keyboard.press(key);
        assert.equal(await video.evaluate((node: HTMLVideoElement) => node.currentTime), expected);
      }
      await page.keyboard.press('Escape');
      await page.locator('#stage').waitFor({ state: 'hidden' });
      await page.locator('#settingsBtn').dispatchEvent('click');
      const panel = page.locator('#settingsPanel');
      await panel.getByRole('tab', { name: 'Browsing & playback', exact: true }).click();
      await panel.getByRole('spinbutton', { name: 'Big fast forward seconds', exact: true }).fill('123');
      await panel.getByRole('textbox', { name: 'Big fast forward shortcut', exact: true }).focus();
      await page.keyboard.press('Shift+g');
      await panel.locator('#scrollVolumeSetting').check();
      const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('peach.settings.v1')!));
      assert.equal(saved.playerSeek.bigForward.seconds, 123);
      assert.equal(saved.playerSeek.bigForward.shortcut, 'Shift+g');
      assert.equal(saved.scrollVolume, true);
      const bounds = await panel.evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
      assert.ok(bounds.scroll <= bounds.client + 1, JSON.stringify(bounds));
      await page.screenshot({ path: path.join(screenshots, `playback-${viewport.name}.png`), fullPage: true });
      await page.keyboard.press('Escape');
      await page.goto(new URL(`/assets/${requiredEnv('PEACH_E2E_ITEM')}`, page.url()).href);
      await video.waitFor({ state: 'attached' });
      await page.waitForFunction(() => (document.querySelector('#stage video') as HTMLVideoElement)?.readyState >= 1);
      await video.evaluate((node: HTMLVideoElement) => {
        node.pause(); Object.defineProperty(node, 'duration', { configurable: true, value: 1000 });
        Object.defineProperty(node, 'currentTime', { configurable: true, writable: true, value: 100 }); node.volume = .5;
      });
      await page.keyboard.press('Shift+g');
      assert.equal(await video.evaluate((node: HTMLVideoElement) => node.currentTime), 223,
        JSON.stringify(await page.evaluate(() => ({ settings: JSON.parse(localStorage.getItem('peach.settings.v1')!),
          focus: document.activeElement?.outerHTML, panel: document.querySelector('#settingsPanel')?.getAttribute('hidden') }))));
      const wheel = await video.evaluate((node: HTMLVideoElement) => {
        const event = new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true }); node.dispatchEvent(event);
        return { prevented: event.defaultPrevented, volume: node.volume };
      });
      assert.equal(wheel.prevented, true); assert.ok(Math.abs(wheel.volume - .55) < .001);
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
});
