import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, settle, visit, VIEWPORTS } from './harness.ts';

describe('视频预览设置', () => {
  let browser: Browser;
  before(async () => { browser = await launch() });
  after(async () => { await browser?.close() });
  for (const viewport of VIEWPORTS) {
    it(`${viewport.name}：自定义间隔、GPU 与转码存储保持独立并适配屏幕`, async () => {
      const thumbnail = { mode: 'off', status: 'idle', interval_seconds: 10, acceleration: 'cpu' };
      const cache = { folder: '', max_gb: 10, used_bytes: 0, active_folder: '/cache', restart_required: false };
      const writes: unknown[] = [];
      const opened = await visit(browser, '/settings/library', viewport, async page => {
        await page.context().addInitScript(() => localStorage.setItem('peach.language', 'en'));
        await page.route('**/api/media-processing', route => route.fulfill({ json: { metadata_only: false } }));
        await page.route('**/api/thumbnail-jobs', async route => {
          if (route.request().method() === 'POST') { const body = route.request().postDataJSON(); writes.push(body); Object.assign(thumbnail, body) }
          await route.fulfill({ json: thumbnail });
        });
        await page.route('**/api/configuration/transcode-cache', async route => {
          if (route.request().method() === 'POST') { const body = route.request().postDataJSON(); writes.push(body); Object.assign(cache, body, { restart_required: true }) }
          await route.fulfill({ json: cache });
        });
      });
      const { page } = opened;
      try {
        await page.locator('#videoThumbnailSetting button').click();
        await page.getByRole('option', { name: 'Custom interval', exact: true }).click();
        await page.getByRole('spinbutton', { name: 'Interval (seconds)', exact: true }).fill('17');
        await page.getByRole('button', { name: 'Apply interval', exact: true }).click();
        await page.locator('#thumbnailAccelerationSetting button').click();
        await page.getByRole('option', { name: 'CUDA (NVIDIA)', exact: true }).click();
        await page.getByRole('textbox', { name: 'Transcode folder', exact: true }).fill('/downloads/peach-cache');
        await page.getByRole('spinbutton', { name: 'Maximum transcode storage (GiB)', exact: true }).fill('20');
        await page.getByRole('button', { name: 'Save transcode storage', exact: true }).click();
        await page.getByText('Restart Peach to use the selected transcode folder. Existing cache files stay in their current folder.', { exact: true }).waitFor();
        assert.deepEqual(writes, [{ mode: 'custom', interval_seconds: 17 }, { action: 'set_acceleration', acceleration: 'cuda' }, { folder: '/downloads/peach-cache', max_gb: 20 }]);
        const measured = await layout(page);
        assert.ok(measured.scrollWidth <= measured.viewportWidth, JSON.stringify(measured));
        assert.deepEqual(measured.offenders, []);
        assert.deepEqual(opened.problems, []);
      } finally { await opened.close() }
    });
    it(`${viewport.name}：总开关持久化并控制时间轴设置，重新开启后时间轴由用户选择`, async () => {
      let disabled = false;
      let timeline = 'coarse';
      const writes: unknown[] = [];
      const opened = await visit(browser, '/settings/library', viewport, async page => {
        await page.route('**/api/media-processing', async route => {
          if (route.request().method() === 'POST') {
            const body = route.request().postDataJSON();
            writes.push(body);
            disabled = body.metadata_only;
            if (disabled) timeline = 'off';
          }
          await route.fulfill({ json: { metadata_only: disabled } });
        });
        await page.route('**/api/thumbnail-jobs', route => route.fulfill({ json: { mode: timeline, status: 'idle' } }));
      });
      const { page } = opened;
      try {
        const toggle = page.getByRole('switch', { name: '生成视频预览', exact: true });
        const interval = page.locator('#videoThumbnailSetting button');
        await toggle.waitFor();
        await settle(page);
        assert.equal(await toggle.isChecked(), true);
        assert.equal(await interval.isDisabled(), false);
        await page.locator('label').filter({ has: toggle }).click();
        await page.getByText('已关闭视频预览生成', { exact: true }).waitFor();
        assert.equal(await toggle.isChecked(), false);
        assert.equal(await interval.isDisabled(), true);
        await page.reload();
        await toggle.waitFor();
        await settle(page);
        assert.equal(await toggle.isChecked(), false);
        assert.equal(await interval.isDisabled(), true);
        assert.match(await interval.innerText(), /关闭/);
        await toggle.focus();
        await page.keyboard.press('Space');
        await page.getByText('已开启视频预览生成', { exact: true }).waitFor();
        assert.equal(await interval.isDisabled(), false);
        assert.match(await interval.innerText(), /关闭/);
        assert.deepEqual(writes, [{ metadata_only: true }, { metadata_only: false }]);
        const measured = await layout(page);
        assert.ok(measured.scrollWidth <= measured.viewportWidth, JSON.stringify(measured));
        assert.deepEqual(measured.offenders, []);
        const artifacts = path.resolve('..', 'build', 'agent-verification', 'media-processing');
        await mkdir(artifacts, { recursive: true });
        await page.screenshot({ path: path.join(artifacts, `${viewport.name}.png`), fullPage: true });
        assert.deepEqual(opened.problems, []);
      } finally { await opened.close() }
    });
  }
});
