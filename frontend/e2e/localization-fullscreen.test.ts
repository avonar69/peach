/* 英文界面覆盖与超宽屏全屏画面，使用临时演示馆藏。 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import type { Browser, Page } from 'playwright-core';
import { launch, layout, requiredEnv, settle, visit, VIEWPORTS } from './harness.ts';
import { stubServer } from './settings-fixture.ts';

const screenshots = process.env.PEACH_E2E_SCREENSHOTS || path.resolve('../build/localization-screenshots');
async function audit(page: Page, selector: string) {
  const untranslated = await page.locator(selector).evaluateAll(roots => {
    const problems: string[] = [];
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode, parent = node.parentElement;
        if (!parent || !parent.checkVisibility() || parent.closest('[data-i18n-ignore],[data-item-title],[data-middle-truncate],code,textarea')) continue;
        const text = node.textContent?.trim() || '';
        if (/[\u3400-\u9fff]/.test(text) && text !== '简体中文') problems.push(text);
      }
      for (const element of root.querySelectorAll('[title],[aria-label],[placeholder]')) {
        if (!(element as HTMLElement).checkVisibility()) continue;
        for (const attribute of ['title', 'aria-label', 'placeholder']) {
          const text = element.getAttribute(attribute) || '';
          if (/[\u3400-\u9fff]/.test(text) && !text.includes('语言')) problems.push(`${attribute}: ${text}`);
        }
      }
    }
    return [...new Set(problems)];
  });
  assert.deepEqual(untranslated, [], `Untranslated UI in ${selector}: ${untranslated.join(' | ')}`);
}

describe('English interface and ultrawide fullscreen', () => {
  let browser: Browser;
  before(async () => {
    process.env.PEACH_E2E_LANGUAGE = 'en';
    await mkdir(screenshots, { recursive: true });
    browser = await launch();
  });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: taste, organize and task summaries are localized`, async () => {
    const opened = await visit(browser, '/taste', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/taste?*', async route => {
        const data = await (await route.fetch()).json();
        data.analysis = { headline: '证据还不足以形成稳定口味结论。', confidence: { level: 'low', label: '仍在学习' } };
        await route.fulfill({ json: data });
      });
      await page.route('**/api/organize', route => route.fulfill({ json: {
        status: 'idle', locations: [{ location: 'local', roots: ['R:/Demo'] }], templates: {}, last_batch: '',
        presets: [{ label: '番号 标题', file: '{number}[ {title}]', dir: '' },
          { label: '厂牌分目录', file: '{number}', dir: '{studio}' }],
        placeholders: [{ key: 'number', label: '番号' }, { key: 'actors', label: '出演者' }],
      } }));
      await page.route('**/api/tasks', route => route.fulfill({ json: { available: true, running: [], skipped: [], finished: [{
        id: 9001, task_key: 'taste-refresh', task_label: '口味分析', trigger: 'manual', status: 'succeeded', host: 'test',
        started_at: '2026-10-23T12:00:00Z', finished_at: '2026-10-23T12:00:48Z', elapsed_seconds: 48,
        progress_current: 0, progress_total: 0, progress_label: '', error: '', parent_run_id: null, root_run_id: null,
        followup_key: '', followup_depth: 0, result_summary: { stage: 'dashboard', message: '部分浏览记录未取得',
          checked: 0, eta_scope: 'full_job', stashdb_applied: 4, stashdb_review: 2 },
      }] } }));
    });
    try {
      const page = opened.page;
      await page.getByText('There is not enough evidence to form a stable taste profile.', { exact: true }).waitFor();
      await page.screenshot({ path: path.join(screenshots, `taste-${viewport.name}.png`), fullPage: true });
      await page.goto(new URL('/data-cleanup', page.url()).href);
      const organize = page.getByRole('region', { name: 'Organize', exact: true });
      await organize.getByRole('button', { name: 'Release code and title', exact: true }).waitFor();
      assert.doesNotMatch(await organize.innerText(), /[\u3400-\u9fff]/);
      assert.ok((await organize.innerText()).includes('{number}'));
      await page.screenshot({ path: path.join(screenshots, `organize-${viewport.name}.png`), fullPage: true });
      await page.goto(new URL('/tasks', page.url()).href);
      await page.getByText('StashDB applied 4', { exact: false }).waitFor();
      await audit(page, '#main');
      assert.doesNotMatch(await page.locator('#main').innerText(), /eta_scope|dashboard|stashdb_applied|speed_mode/);
      await page.screenshot({ path: path.join(screenshots, `tasks-${viewport.name}.png`), fullPage: true });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });

  for (const viewport of VIEWPORTS) it(`${viewport.name}: backend scan steps, orientation filters and diagnostics`, { timeout: 120_000 }, async () => {
    const opened = await visit(browser, '/', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/library-processing', route => route.fulfill({ json: {
        status: 'running', job_id: 'localization-test', stage: 'previews', total: 7, checked: 2,
        eta_seconds_min: 30240, eta_seconds_max: 48240, eta_initial: true, eta_scope: '整趟任务', scanned: 7,
        current_action: 'generating_preview', current_asset_name: 'Example.{1}.mp4', waited_seconds: 2,
        steps: [
          { id: 'scan', label: '扫描文件', status: 'complete' },
          { id: 'sidecars', label: '检查配套文件', status: 'complete' },
          { id: 'previews', label: '读取媒体属性与生成预览', status: 'current' },
          { id: 'metadata', label: '采集外部资料与封面', status: 'pending' },
        ],
      } }));
      await page.route('**/api/diagnostics', async route => {
        const report = await (await route.fetch()).json();
        report.checks.ffmpeg = { label: 'FFmpeg / OpenSSL', status: 'warning', reason: '未找到：openssl', action: '更新媒体工具', target: '/settings/maintenance', details: {} };
        for (const [key, label] of [['identification', '识别失败'], ['metadata', '补资料失败'], ['cover', '缺封面'], ['duration', '缺时长']]) {
          report.library.groups[key] = { label, status: 'ok', count: key === 'identification' || key === 'metadata' ? null : 0, items: [], truncated: false };
        }
        report.sources = [{ source: 'minnano-av', label: 'みんなのAV', status: 'unchecked', reason: '尚无检查或解析记录，可在来源和凭证中检查连接', last_success_at: null, cooldown_until: null }];
        await route.fulfill({ json: report });
      });
    });
    try {
      const { page } = opened;
      await page.locator('[data-processing-step="current"]').waitFor();
      await page.waitForFunction(() => document.querySelector('[data-processing-step="current"]')?.textContent?.includes('Read media properties'));
      await audit(page, '[data-processing-dock]');
      assert.match(await page.locator('[data-processing-dock]').innerText(), /8\.4–13\.4 hours/);
      assert.match(await page.locator('[data-processing-dock]').innerText(), /Generate video preview/);
      assert.match(await page.locator('[data-processing-dock]').innerText(), /Example\.\{1\}\.mp4/);
      await page.goto(new URL('/data-cleanup', page.url()).href);
      await page.getByRole('button', { name: 'More synchronization methods', exact: true }).waitFor();
      assert.doesNotMatch(await page.locator('#main').innerText(), /Health成|Small时|整趟任务|粗估/);
      assert.equal(await page.locator('[data-sidebar-chip-label]').filter({ hasText: '横屏' }).count(), 0);
      await page.goto(new URL('/settings/diagnostics', page.url()).href);
      await page.locator('[data-diagnostic-source]').waitFor();
      await settle(page);
      await audit(page, '.ui-configpage');
      assert.doesNotMatch(await page.title(), /[\u3400-\u9fff]/);
      await page.screenshot({ path: path.join(screenshots, `diagnostics-${viewport.name}.png`), fullPage: true });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });

  for (const viewport of VIEWPORTS) it(`${viewport.name}: stop scan is shared by the page and popup`, async () => {
    let state = { status: 'running', job_id: 'stop-test', stage: 'StashDB actor and studio matching', checked: 2, total: 10 };
    const posts: unknown[] = [];
    const opened = await visit(browser, '/data-cleanup', viewport, async page => {
      await stubServer(page);
      await page.route('**/api/library-processing', async route => {
        if (route.request().method() === 'POST') {
          posts.push(route.request().postDataJSON());
          state = { ...state, status: 'cancelled' };
        }
        await route.fulfill({ json: state });
      });
    });
    try {
      const { page } = opened;
      await page.locator('#main').getByRole('button', { name: 'Stop scan', exact: true }).waitFor();
      await page.locator('[data-processing-dock]').getByRole('button', { name: 'Stop scan', exact: true }).waitFor();
      await page.locator('#main').getByRole('button', { name: 'Stop scan', exact: true }).click();
      await page.getByText('Completed work has been kept. Start a new scan when ready.', { exact: true }).waitFor();
      assert.deepEqual(posts, [{ action: 'stop', job_id: 'stop-test' }]);
      await page.locator('[data-processing-dock]').waitFor({ state: 'hidden' });
      assert.equal(await page.getByRole('button', { name: 'Stop scan', exact: true }).count(), 0);
      const geometry = await layout(page);
      assert.ok(geometry.scrollWidth <= viewport.width + 1);
      await audit(page, '#main');
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });

  it('offers all ten languages and renders each bundled locale', { timeout: 120_000 }, async () => {
    for (const language of ['es', 'fr', 'de', 'pt-BR', 'ja', 'ko', 'vi', 'zh-TW']) {
      process.env.PEACH_E2E_LANGUAGE = language;
      const opened = await visit(browser, '/settings/maintenance', VIEWPORTS[0]);
      try {
        await opened.page.locator('.ui-board-local-nav').waitFor();
        await settle(opened.page);
        assert.equal(await opened.page.locator('html').getAttribute('lang'), language);
        assert.ok((await opened.page.locator('.ui-board-local-nav').innerText()).trim());
        assert.ok(!(await opened.page.locator('.ui-board-local-nav').innerText()).includes('系统诊断'));
      } finally { await opened.close(); }
    }
    process.env.PEACH_E2E_LANGUAGE = 'en';
    const opened = await visit(browser, '/settings/maintenance', VIEWPORTS[0]);
    try {
      const page = opened.page;
      await page.getByRole('button', { name: /Language/ }).click();
      assert.equal(await page.getByRole('option').count(), 10);
      await page.getByRole('option', { name: 'Español', exact: true }).click();
      await page.waitForFunction(() => document.documentElement.lang === 'es');
      await page.reload();
      await page.waitForFunction(() => document.documentElement.lang === 'es');
    } finally { await opened.close(); }
  });

  for (const viewport of VIEWPORTS) it(`${viewport.name}: tutorial, top bar, settings tabs and dropdowns`, { timeout: 120_000 }, async () => {
    const opened = await visit(browser, '/?onboarding=1', viewport, async page => {
      const server = await stubServer(page);
      server.settings.postSetupTutorialDone = false;
      await page.route('**/api/post-setup-tutorial', route => route.fulfill({ json: {
        library: { total: 7 }, scraping: { sources: [] }, taste: { history_sources: 0 },
        follow: { sources: [] }, credentials: { providers: [] }, review: { counts: {} },
      } }));
    });
    try {
      const page = opened.page;
      await page.locator('#settingsBtn').waitFor({ state: 'attached' });
      await page.locator('#postSetupTutorial h2').waitFor();
      await settle(page);
      await page.waitForFunction(() => document.querySelector('#postSetupTutorial h2')?.textContent === 'Finish setting up Peach');
      await audit(page, '#postSetupTutorial,[data-catalog-summary],[data-entity-sorts],#toasts');
      await page.screenshot({ path: path.join(screenshots, `home-${viewport.name}.png`), fullPage: true });
      await page.locator('#settingsBtn').dispatchEvent('click');
      const panel = page.locator('#settingsPanel');
      await panel.waitFor();
      for (const tab of ['Appearance & navigation', 'Browsing & playback', 'JAV & new releases', 'Search & recommendations', 'Content display']) {
        await panel.getByRole('tab', { name: tab, exact: true }).click();
        await settle(page, '#settingsPanel');
        await audit(page, '#settingsPanel');
      }
      await panel.getByRole('tab', { name: 'Browsing & playback', exact: true }).click();
      await panel.locator('#defaultSortSetting button').first().dispatchEvent('click');
      await page.locator('[role="listbox"]:visible').last().waitFor();
      await audit(page, '#settingsPanel,[role="listbox"]:visible');
      await page.keyboard.press('Escape');
      await panel.getByRole('tab', { name: 'Appearance & navigation', exact: true }).click();
      await page.screenshot({ path: path.join(screenshots, `settings-${viewport.name}.png`), fullPage: true });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });

  it('5120x1440: full frame, native resolution, crop choice and persistence', { timeout: 120_000 }, async () => {
    const viewport = { name: 'ultrawide', width: 5120, height: 1440, mobile: false };
    const opened = await visit(browser, `/assets/${requiredEnv('PEACH_E2E_ITEM')}`, viewport);
    try {
      const page = opened.page;
      const video = page.locator('#stage video.vjs-tech');
      await video.waitFor({ state: 'attached' });
      await page.waitForFunction(() => (document.querySelector('#stage video') as HTMLVideoElement)?.videoWidth > 0);
      await video.evaluate((node: HTMLVideoElement) => { node.pause(); });
      const root = page.locator('#stage .video-js');
      assert.equal(await root.getAttribute('data-fullscreen-sizing'), 'fit');
      await page.locator('#stage .vjs-fullscreen-control').click();
      await page.waitForFunction(() => !!document.fullscreenElement);
      const geometry = await video.evaluate(node => {
        const element = node as HTMLVideoElement, style = getComputedStyle(node), rect = node.getBoundingClientRect();
        return { fit: style.objectFit, width: rect.width, height: rect.height, intrinsicWidth: element.videoWidth, intrinsicHeight: element.videoHeight };
      });
      assert.equal(geometry.fit, 'contain');
      assert.equal(geometry.width, 5120);
      assert.equal(geometry.height, 1440);
      assert.ok(geometry.intrinsicWidth > 0 && geometry.intrinsicHeight > 0);
      await page.screenshot({ path: path.join(screenshots, 'ultrawide-fit.png') });
      await page.locator('#stage .vjs-peach-settings-toggle').dispatchEvent('click');
      await page.locator('[data-player-sizing-view]').click();
      await page.getByRole('menuitemradio', { name: 'Original resolution', exact: true }).click();
      assert.equal(await video.evaluate(node => getComputedStyle(node).objectFit), 'scale-down');
      await page.locator('#stage .vjs-peach-settings-toggle').dispatchEvent('click');
      await page.screenshot({ path: path.join(screenshots, 'ultrawide-original.png') });
      await page.locator('#stage .vjs-peach-settings-toggle').dispatchEvent('click');
      await page.locator('[data-player-sizing-view]').click();
      await audit(page, '.vjs-peach-settings-menu');
      await page.getByRole('menuitemradio', { name: 'Fill screen (crop)', exact: true }).click();
      assert.equal(await video.evaluate(node => getComputedStyle(node).objectFit), 'cover');
      await page.locator('[data-player-sizing-view]').click();
      await page.getByRole('menuitemradio', { name: 'Original resolution', exact: true }).click();
      await page.evaluate(() => document.exitFullscreen());
      await page.reload({ waitUntil: 'load' });
      await page.locator('#stage .video-js[data-fullscreen-sizing="original"]').waitFor({ state: 'attached' });
      await page.locator('#stage video.vjs-tech').click({ button: 'right' });
      await page.locator('#playerMenu').waitFor();
      await audit(page, '#playerMenu,[data-trace-label],#oBtn');
      await page.screenshot({ path: path.join(screenshots, 'player-context-menu.png') });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
});
