/* 桌面及手机验证作品弹层里的编辑与重匹配入口。 */
import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, VIEWPORTS } from './harness.ts';
import { ITEM, openItemPage } from './item-fixture.ts';

describe('Scene metadata controls', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: edit and rematch only the current scene`, async () => {
    const opened = await openItemPage(browser, `/assets/${ITEM.plain}`, viewport);
    const page = opened.page;
    const posts: Array<Record<string, unknown>> = [];
    const item = await page.evaluate(async id => (await fetch(`/api/item?id=${id}`)).json(), ITEM.plain);
    await page.route('**/api/scene-metadata*', async route => {
      if (route.request().method() === 'GET') {
        await route.fulfill({ json: { catalog_title: 'Original title', original_title: '', code: '', studio: 'Original Studio',
          series: '', release_date: '2026-10-22', mutation_revision: 8, performers: ['Jane Doe'] } });
      } else {
        const body = route.request().postDataJSON(); posts.push(body);
        await route.fulfill({ json: { ok: true, item: { ...item, title: body.values.catalog_title, catalog_title: body.values.catalog_title } } });
      }
    });
    await page.route('**/api/rematch-metadata', async route => {
      posts.push(route.request().postDataJSON());
      await route.fulfill({ json: { status: 'running', requested_stage: 'rematch' } });
    });
    try {
      const tools = page.locator('[data-title-tools]');
      await tools.getByRole('button', { name: 'Edit scene', exact: true }).click();
      const dialog = page.getByRole('dialog', { name: 'Edit scene', exact: true });
      await dialog.getByLabel('Title', { exact: true }).fill('Manually edited scene');
      await dialog.getByLabel('Actors, one per line', { exact: true }).fill('Clara Fargo\nJane Doe');
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      const box = await dialog.boundingBox();
      assert.ok(box && box.x >= 0 && box.x + box.width <= viewport.width + 1);
      await dialog.screenshot({ path: `../build/agent-verification/scene-editor-${viewport.name}.png` });
      await dialog.getByRole('button', { name: 'Save scene', exact: true }).click();
      await dialog.waitFor({ state: 'detached' });
      assert.deepEqual(posts[0], { id: ITEM.plain, expected_revision: 8, values: { catalog_title: 'Manually edited scene' }, performers: ['Clara Fargo', 'Jane Doe'] });
      await tools.getByRole('button', { name: 'Rematch metadata', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('[data-title-tools] [aria-busy="true"]'));
      assert.deepEqual(posts[1], { kind: 'scene', id: ITEM.plain });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror') && !problem.includes('VIDEOJS')), []);
    } finally { await opened.close(); }
  });
});
