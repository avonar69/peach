import { QueryClientProvider, notifyManager } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { StashDBReview } from '../../src/react/review/stashdb-review';
import { queryClient } from '../../src/react/query';
import { mount, click, buttonNamed } from './render';

notifyManager.setScheduler(callback => callback());
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { queryClient.clear(); localStorage.clear(); });

function serve() {
  const posts: { path: string; body: unknown }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      posts.push({ path, body: JSON.parse(String(options.body)) });
      return new Response(JSON.stringify({ candidates: [{ id: 'remote', title: 'Candidate scene', score: .65, reasons: ['Duration matches'], url: 'https://stashdb.org/scenes/remote' }], review_required: false }));
    }
    return new Response(JSON.stringify([{ id: 9, label: 'Pending scene' }]));
  }));
  return posts;
}

it('作品内复核直接查询当前作品候选', async () => {
  const posts = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><StashDBReview sceneId={9} sceneName="Local scene"
    readOnly={false} receipt={vi.fn()} onCount={vi.fn()} /></QueryClientProvider>);
  expect(posts).toContainEqual({ path: '/api/configuration/stashdb/preview', body: { asset_id: 9 } });
  expect(host.textContent).toContain('Candidate scene');
  expect(buttonNamed('Apply selected match', host)).toBeTruthy();
  expect(buttonNamed('Find library items', host)).toBeNull();
});

it('队列重跑只提交待复核项目', async () => {
  const posts = serve();
  const host = await mount(<QueryClientProvider client={queryClient}><StashDBReview readOnly={false} receipt={vi.fn()} onCount={vi.fn()} /></QueryClientProvider>);
  await click(buttonNamed('Rerun pending StashDB matches', host));
  expect(posts).toContainEqual({ path: '/api/library-processing', body: { stage: 'stashdb_review', asset_ids: [9] } });
});
