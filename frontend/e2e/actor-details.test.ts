/* 演员资料的桌面与手机布局、编辑和多词别名行为。 */
import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, visit, VIEWPORTS } from './harness.ts';

describe('Actor profile details', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; browser = await launch(); });
  after(async () => { await browser.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: edit actor info and preserve spaces in aliases`, async () => {
    const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
    const entity = { id: 90101, kind: 'performer', canonical_name: 'Example Actor', aliases: [], user_aliases: [],
      asset_count: 97, tags: [], related_performers: [], links: [], metadata: {}, entry_links: [],
      actor_details: { birth_date: '1996-01-12', age: 30, career_start_year: 2015, height: 170,
        measurements: '34C / 24 / 36', breast_type: 'NATURAL', nationality: 'US', ethnicity: 'CAUCASIAN', eye_color: 'BLUE', hair_color: 'BLONDE' } };
    const opened = await visit(browser, '/', viewport);
    const page = opened.page;
    await page.route(/\/api\/entity\?/, route => route.fulfill({ json: entity }));
    await page.route(url => ['/api/items', '/api/photos'].includes(url.pathname), route => route.fulfill({ json: { items: [], total: 0, sets: [], has_more: false } }));
    await page.route('**/api/actor-details', async route => {
      const body = route.request().postDataJSON(); posts.push({ path: '/api/actor-details', body });
      Object.assign(entity.actor_details, body.values);
      await route.fulfill({ json: { ok: true } });
    });
    await page.route('**/api/entity-alias', async route => {
      const body = route.request().postDataJSON(); posts.push({ path: '/api/entity-alias', body });
      await route.fulfill({ json: { ok: true, added: true, alias: body.alias } });
    });
    try {
      await page.goto(new URL('/performers/Example%20Actor', page.url()).href);
      await page.getByRole('button', { name: 'Edit actor info', exact: true }).waitFor();
      assert.ok((await page.locator('[data-entity-facts]').innerText()).includes('1996-01-12 (30 years old)'));
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      for (const scheme of ['light', 'dark'] as const) {
        await page.emulateMedia({ colorScheme: scheme });
        await page.locator('[data-entity-card]').screenshot({ path: `../build/agent-verification/actor-details-${viewport.name}-${scheme}.png` });
      }
      await page.getByRole('button', { name: 'Edit actor info', exact: true }).click();
      await page.getByLabel('Height (cm)', { exact: true }).fill('172');
      await page.getByRole('button', { name: 'Save actor info', exact: true }).click();
      await page.getByRole('dialog', { name: 'Edit actor info' }).waitFor({ state: 'detached' });
      assert.ok(posts.some(post => post.path === '/api/actor-details' && (post.body.values as Record<string, unknown>).height === '172'));
      await page.locator('[data-namepick-toggle]').click();
      await page.locator('[data-namepick-alias]').click();
      const field = page.locator('dialog [name=alias]');
      await field.pressSequentially('Chloe, Clara Fargo, Larissa');
      assert.equal(await field.inputValue(), 'Chloe, Clara Fargo, Larissa');
      await page.locator('dialog [data-modal-confirm]').click();
      await page.locator('dialog [name=alias]').waitFor({ state: 'detached' });
      assert.deepEqual(posts.filter(post => post.path === '/api/entity-alias').map(post => post.body.alias), ['Chloe', 'Clara Fargo', 'Larissa']);
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
});
