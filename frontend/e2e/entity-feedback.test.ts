/* 演员与厂牌的个人评分汇总在桌面及窄屏保持可见。 */
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, layout, visit, VIEWPORTS } from './harness.ts';

describe('实体个人评分', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'en'; mkdirSync('../build/entity-feedback-screens',{recursive:true}); browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) for (const kind of ['performer','studio']) it(`${viewport.name}: ${kind}`, async () => {
    const opened = await visit(browser, '/', viewport);
    const { page } = opened;
    const entity = { id: 90101, kind, canonical_name: 'Example', aliases: [], user_aliases: [],
      asset_count: 12, tags: [], related_performers: [], links: [], metadata: {}, entry_links: [],
      scene_feedback: {average_stars:3.75,rated_count:2,thumbs_up:4,thumbs_down:1} };
    await page.route(/\/api\/entity\?/, route => route.fulfill({json:entity}));
    await page.route(url => ['/api/items','/api/photos'].includes(url.pathname), route => route.fulfill({json:{items:[],total:0,sets:[],has_more:false}}));
    try {
      await page.goto(new URL(`/${kind === 'performer' ? 'performers' : 'studios'}/Example`,page.url()).href);
      const summary = page.locator('[data-scene-feedback]');
      await summary.waitFor();
      assert.equal(await summary.getByRole('img',{name:'Average scene rating: 3.75 / 5',exact:true}).count(),1);
      assert.equal(await summary.getByRole('img',{name:'Thumbs up: 4',exact:true}).count(),1);
      assert.ok((await layout(page)).scrollWidth <= viewport.width + 1);
      const bounds = await summary.boundingBox();
      assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= viewport.width + 1);
      await page.locator('[data-entity-card]').screenshot({path:`../build/entity-feedback-screens/${kind}-${viewport.name}.png`});
      assert.deepEqual(opened.problems.filter(p=>p.startsWith('pageerror')),[]);
    } finally {await opened.close();}
  });
});
