/* 演员合并的桌面与手机布局、选择范围及最终确认。 */
import assert from 'node:assert/strict';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, visit, VIEWPORTS } from './harness.ts';

describe('Actor merge review', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: choose candidates, clear selection, confirm a single merge`, async () => {
    const opened = await visit(browser, '/', viewport);
    const page = opened.page;
    const actor = { id: 1, name: 'Jane Doe', scenes: 12, aliases: ['Clara Fargo'], token: 'one', has_image: false };
    const matches = [
      { ...actor, id: 2, name: 'Jane Doe Scene', token: 'two', reason: 'Name contains another actor name', conflicts: [] },
      { ...actor, id: 3, name: 'Jane Doe Morning Scene', token: 'three', reason: 'Name contains another actor name', conflicts: [] },
      { ...actor, id: 4, name: 'Jane Doe Other', token: 'four', reason: 'Similar actor name', conflicts: ['stashdb:performer'] },
    ];
    const posts: unknown[] = [];
    let merged = false;
    let batch = false;
    await page.route('**/api/review*', route => route.fulfill({ json: { counts: { actor_merge: 1 }, sections: {}, sources: [], genre_tags: [] } }));
    await page.route('**/api/actor-merge*', async route => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON();
        posts.push(body); merged = true;
        if (body.action) batch = body.action === 'automatic';
        await route.fulfill({ json: { ok: true, id: 1, name: actor.name, merged_ids: [2] } });
      } else {
        const params = new URL(route.request().url()).searchParams;
        if (params.get('mode') === 'automatic') {
          await route.fulfill({ json: { groups: 3, actors: 5, token: 'frozen-plan' } }); return;
        }
        if (params.get('mode') === 'history') {
          await route.fulfill({ json: { batches: batch ? [{ id: 'batch', groups: 3, actors: 5, created_at: '2026-10-28T20:00:00Z' }] : [] } }); return;
        }
        await route.fulfill({ json: params.has('actor_id')
          ? { actor, matches } : { total: merged ? 0 : 1, offset: 0, groups: merged ? [] : [{ ...actor, matches: 3 }] } });
      }
    });
    try {
      await page.goto(new URL('/review?category=actor_merge', page.url()).href);
      await page.getByRole('button', { name: /Jane Doe.*possible duplicates/s }).click();
      assert.ok(await page.locator('[data-actor-merge-group]').evaluate(node => node.clientHeight >= node.scrollHeight - 1));
      const section = page.getByRole('region', { name: 'Actor merge', exact: true });
      await section.getByRole('button', { name: 'Select all', exact: true }).click();
      assert.equal(await section.locator('input[type=checkbox]:checked').count(), 2);
      await section.getByRole('button', { name: 'Deselect all', exact: true }).click();
      assert.equal(await section.locator('input[type=checkbox]:checked').count(), 0);
      await section.getByText('Jane Doe Scene', { exact: true }).click();
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      await section.screenshot({ path: `../build/agent-verification/actor-merge-${viewport.name}.png` });
      await section.getByRole('button', { name: 'Merge selected actors', exact: true }).click();
      const confirm = page.locator('dialog [data-modal-confirm]');
      await confirm.waitFor();
      assert.equal(posts.length, 0);
      await confirm.click();
      await page.getByText('No actor merge suggestions', { exact: true }).waitFor();
      assert.deepEqual(posts, [{ actor_id: 1, merge_ids: [2], name: 'Jane Doe', confirmed: true, expected: { 1: 'one', 2: 'two' } }]);
      await section.getByText('Hide suggestions with only conflicting source identities', { exact: true }).click();
      assert.equal(await page.evaluate(() => localStorage.getItem('peach.actor-merge.hide-conflicts')), '1');
      await section.getByRole('button', { name: 'Automatically Merge All', exact: true }).click();
      await confirm.waitFor();
      assert.equal(posts.length, 1);
      await confirm.click();
      await section.getByRole('button', { name: 'Undo actor merge', exact: true }).waitFor();
      assert.deepEqual(posts[1], { action: 'automatic', expected: 'frozen-plan', confirmed: true });
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      await section.screenshot({ path: `../build/agent-verification/actor-batch-${viewport.name}.png` });
      await section.getByRole('button', { name: 'Undo actor merge', exact: true }).click();
      await confirm.waitFor(); await confirm.click();
      await section.getByRole('button', { name: 'Undo actor merge', exact: true }).waitFor({ state: 'hidden' });
      assert.deepEqual(posts[2], { action: 'undo', batch_id: 'batch', confirmed: true });
      assert.deepEqual(opened.problems.filter(problem => problem.startsWith('pageerror')), []);
    } finally { await opened.close(); }
  });
});
