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
  expect([...host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].map(input => input.checked)).toEqual([true, true, false]);
  await click(buttonNamed('Deselect all', host));
  expect([...host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].some(input => input.checked)).toBe(false);
  await click(host.querySelector('label:has(input[type="checkbox"])'));
  await click(buttonNamed('Merge selected actors', host));
  expect(posts).toEqual([{ actor_id: 1, merge_ids: [2], name: 'Jane Doe', confirmed: true, expected: { 1: 'one', 2: 'two' } }]);
});

it('只读资料库不能选择或合并演员', async () => {
  const posts = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><ActorMergeReview readOnly receipt={vi.fn()} openEntity={vi.fn()} /></QueryClientProvider>);
  await settle(); await click(host.querySelector('button[aria-pressed]')); await settle();
  expect(buttonNamed('Select all', host)?.disabled).toBe(true);
  expect(buttonNamed('Merge selected actors', host)?.disabled).toBe(true);
  expect(posts).toEqual([]);
});
