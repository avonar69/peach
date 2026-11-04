/* 半星评分在桌面与手机使用同一份百分制写入契约。 */
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
import { after, before, describe, it } from 'node:test';
import type { Browser } from 'playwright-core';
import { launch, VIEWPORTS } from './harness.ts';
import { ITEM, openItemPage } from './item-fixture.ts';

describe('半星评分', () => {
  let browser: Browser;
  before(async () => { process.env.PEACH_E2E_LANGUAGE = 'zh-CN'; mkdirSync('../build/half-star-screens', { recursive: true }); browser = await launch(); });
  after(async () => { await browser?.close(); });
  for (const viewport of VIEWPORTS) it(`${viewport.name}: 半星写入与清除`, { timeout: 60_000 }, async () => {
    const opened = await openItemPage(browser, `/assets/${ITEM.plain}`, viewport);
    try {
      const { page } = opened;
      const picker = page.locator('#detailRating [data-rating-select]');
      await picker.selectOption('3.5');
      await page.locator('#detailRating [data-rating-value]', { hasText: '3.5 星' }).waitFor();
      assert.equal(await page.locator('#detailRating [data-star-half]').count(), 1);
      assert.equal(await page.locator('#detailRating [data-on="true"]').count(), 3);
      assert.ok(opened.stub.writes.some(write => write.url === '/api/feedback' && write.body.value === 70));
      const fits = await page.locator('#detailRating').evaluate(node => {
        const bounds = node.getBoundingClientRect(); return bounds.left >= 0 && bounds.right <= innerWidth;
      });
      assert.ok(fits);
      await page.locator('#detailRating').screenshot({ path: `../build/half-star-screens/${viewport.name}.png` });
      await picker.selectOption('0');
      await page.locator('#detailRating [data-rating-value]', { hasText: '未评分' }).waitFor();
      assert.ok(opened.stub.writes.some(write => write.url === '/api/feedback' && write.body.value === 0));
    } finally { await opened.close(); }
  });
});
