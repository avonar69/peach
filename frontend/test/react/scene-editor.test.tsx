/* 场景编辑的字段写入、空演员名单与定向重匹配。 */
import { act } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { SceneEditor } from '../../src/react/item-detail/scene-editor';
import { MetadataRematch } from '../../src/react/components/metadata-rematch';
import { buttonNamed, click, mount, type } from './render';

beforeEach(() => localStorage.setItem('peach.language', 'en'));

it('编辑场景只提交变更字段并保留完整演员名', async () => {
  const posts: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, options?: RequestInit) => {
    if (options?.method === 'POST') { posts.push(JSON.parse(String(options.body))); return new Response(JSON.stringify({ item: { id: 7 } })); }
    return new Response(JSON.stringify({ catalog_title: 'Original', studio: 'Studio', mutation_revision: 5, performers: ['Jane Doe'] }));
  }));
  const saved = vi.fn();
  const host = await mount(<SceneEditor id={7} onSaved={saved} receipt={vi.fn()} />);
  await click(host.querySelector('button[aria-label="Edit scene"]'));
  const dialog = document.querySelector('[role="dialog"]')!;
  await type(dialog.querySelector<HTMLInputElement>('input[type="text"]'), 'New title');
  await act(async () => {
    const textarea = dialog.querySelector('textarea')!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'Clara Fargo\nJane Doe');
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await click(buttonNamed('Save scene', dialog));
  expect(posts).toEqual([{ id: 7, expected_revision: 5, values: { catalog_title: 'New title' }, performers: ['Clara Fargo', 'Jane Doe'] }]);
  expect(saved).toHaveBeenCalledWith({ id: 7 });
});

it('重匹配仅提交当前实体并反馈请求错误', async () => {
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response(JSON.stringify({ error: '请先在来源与订阅中配置 StashDB' }), { status: 400 }));
  vi.stubGlobal('fetch', fetch);
  const host = await mount(<MetadataRematch kind="studio" id={12} onSaved={vi.fn()} receipt={vi.fn()} />);
  await click(host.querySelector('button[aria-label="Rematch metadata"]'));
  expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual({ kind: 'studio', id: 12 });
  expect(document.querySelector('[role="alert"]')?.textContent).toContain('Configure StashDB in Sources & subscriptions first.');
});
