/* 演员候选的全选、清空、逐项选择与确认范围。 */
import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as legacyUi from '@peach/legacy/ui';
import { ActorMergeReview } from '../../src/react/review/actor-merge-review';
import { queryClient } from '../../src/react/query';
import { buttonNamed, click, mount, settle } from './render';

notifyManager.setScheduler(callback => callback());
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { queryClient.clear(); localStorage.clear(); });
const actor = { id: 1, name: 'Jane Doe', scenes: 10, aliases: [], has_image: false, token: 'one' };
const matches = [
  { ...actor, id: 2, name: 'Jane Doe Scene', token: 'two', reason: 'Similar actor name', conflicts: [] },
  { ...actor, id: 3, name: 'Jane Doe Beach', token: 'three', reason: 'Similar actor name', conflicts: [] },
  { ...actor, id: 4, name: 'Jane Doe Other', token: 'four', reason: 'Similar actor name', conflicts: ['stashdb:performer'] },
];

function serve() {
  const posts: Record<string, unknown>[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === 'POST') { posts.push(JSON.parse(String(options.body))); return new Response(JSON.stringify({ ok: true })); }
    if (String(url).includes('mode=automatic')) return new Response(JSON.stringify({ groups: 1, actors: 2, token: 'selected-plan' }));
    if (String(url).includes('mode=history')) return new Response(JSON.stringify({ batches: [] }));
    return new Response(JSON.stringify(String(url).includes('actor_id=') ? { actor, matches } : { total: 1, offset: 0, groups: [{ ...actor, matches: 3 }] }));
  }));
  return posts;
}

it('全选排除来源冲突，清空后可单独确认一条候选', async () => {
  const posts = serve();
  type Confirmation = Parameters<typeof legacyUi.confirmModal>[0];
  vi.spyOn(legacyUi, 'confirmModal').mockImplementation((async (options: Confirmation) => {
    await options.onConfirm?.(); return { confirmed: true };
  }) as typeof legacyUi.confirmModal);
  const host = await mount(<QueryClientProvider client={queryClient}><ActorMergeReview readOnly={false} receipt={vi.fn()} openEntity={vi.fn()} /></QueryClientProvider>);
  await settle();
  await click(host.querySelector('button[aria-pressed]'));
  await settle();
  await click(buttonNamed('Select all', host));
  expect([...host.querySelectorAll<HTMLInputElement>('[data-actor-merge-match] input[type="checkbox"]')].map(input => input.checked)).toEqual([true, true, false]);
  await click(buttonNamed('Deselect all', host));
  expect([...host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].some(input => input.checked)).toBe(false);
  await click(host.querySelector('[data-actor-merge-match] label'));
  await click(buttonNamed('Merge selected actors', host));
  expect(posts).toEqual([{ actor_id: 1, merge_ids: [2], name: 'Jane Doe', confirmed: true, expected: { 1: 'one', 2: 'two' } }]);
});

it('逐项忽略候选，选中组的批量请求只包含所选组', async () => {
  const posts = serve();
  vi.spyOn(legacyUi, 'confirmModal').mockImplementation((async (options: Parameters<typeof legacyUi.confirmModal>[0]) => {
    await options.onConfirm?.(); return { confirmed: true };
  }) as typeof legacyUi.confirmModal);
  const host = await mount(<QueryClientProvider client={queryClient}><ActorMergeReview readOnly={false} receipt={vi.fn()} openEntity={vi.fn()} /></QueryClientProvider>);
  await settle(); await click(host.querySelector('button[aria-pressed]')); await settle();
  await click(buttonNamed('Ignore suggestion', host)); await settle();
  expect(posts[0]).toEqual({ action: 'ignore', actor_id: 1, merge_ids: [2], expected: { 1: 'one', 2: 'two' } });
  await click([...host.querySelectorAll('label')].find(label => label.textContent?.includes('Select group: Jane Doe')));
  await click(buttonNamed('Automatically merge selected groups', host)); await settle();
  expect(posts[1]).toEqual({ action: 'automatic', expected: 'selected-plan', confirmed: true, group_ids: [1] });
});

it('只读资料库不能选择或合并演员', async () => {
  const posts = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><ActorMergeReview readOnly receipt={vi.fn()} openEntity={vi.fn()} /></QueryClientProvider>);
  await settle(); await click(host.querySelector('button[aria-pressed]')); await settle();
  expect(buttonNamed('Select all', host)?.disabled).toBe(true);
  expect(buttonNamed('Merge selected actors', host)?.disabled).toBe(true);
  expect(posts).toEqual([]);
});

it('批量确认使用完整计划并可从持久历史撤销，冲突筛选保存在浏览器', async () => {
  const posts: Record<string, unknown>[] = [];
  const gets: string[] = [];
  let merged = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      const body = JSON.parse(String(options.body)); posts.push(body); merged = body.action === 'automatic';
      return new Response(JSON.stringify({ ok: true }));
    }
    gets.push(String(url));
    const value = String(url).includes('mode=automatic') ? { groups: 9, actors: 25, token: 'all-groups' }
      : String(url).includes('mode=history') ? { batches: merged ? [{ id: 'batch', actors: 25, groups: 9, created_at: '2026-10-28T20:00:00Z' }] : [] }
        : { total: 0, offset: 0, groups: [] };
    return new Response(JSON.stringify(value));
  }));
  vi.spyOn(legacyUi, 'confirmModal').mockImplementation((async (options: Parameters<typeof legacyUi.confirmModal>[0]) => {
    await options.onConfirm?.(); return { confirmed: true };
  }) as typeof legacyUi.confirmModal);
  const host = await mount(<QueryClientProvider client={queryClient}><ActorMergeReview readOnly={false} receipt={vi.fn()} openEntity={vi.fn()} /></QueryClientProvider>);
  await settle();
  await click(host.querySelector('label:has(input[type="checkbox"])')); await settle();
  expect(localStorage.getItem('peach.actor-merge.hide-conflicts')).toBe('1');
  expect(gets.some(url => url.includes('hide_conflicts=1'))).toBe(true);
  await click(buttonNamed('Automatically Merge All', host)); await settle();
  expect(posts[0]).toEqual({ action: 'automatic', expected: 'all-groups', confirmed: true });
  await click(buttonNamed('Undo actor merge', host)); await settle();
  expect(posts[1]).toEqual({ action: 'undo', batch_id: 'batch', confirmed: true });
});
