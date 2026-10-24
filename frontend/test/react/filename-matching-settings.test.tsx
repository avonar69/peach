import { expect, it, vi } from 'vitest';
import { FilenameMatchingSettings } from '../../src/react/settings/filename-matching-settings';
import { click, mount, pending, settle } from './render';

it('saves independent actor and studio switches after server confirmation', async () => {
  const saved = pending<{ actors: boolean; studios: boolean }>();
  const receipt = vi.fn();
  const requests: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    requests.push(JSON.parse(String(init?.body)));
    return { ok: true, json: () => saved.answer };
  }));
  const host = await mount(<FilenameMatchingSettings initial={{ actors: false, studios: false }} receipt={receipt} />);
  const controls = host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
  await click(controls[1]);
  await settle();
  expect(requests).toEqual([{ actors: false, studios: true }]);
  expect(receipt).not.toHaveBeenCalled();
  await saved.release({ actors: false, studios: true });
  await settle();
  expect(controls[0]?.checked).toBe(false);
  expect(controls[1]?.checked).toBe(true);
  expect(receipt).toHaveBeenCalledWith('已保存文件名匹配设置');
});

it('keeps the saved policy and shows the error when a change fails', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 400, json: async () => ({ detail: '保存失败' }) })));
  const receipt = vi.fn();
  const host = await mount(<FilenameMatchingSettings initial={{ actors: true, studios: false }} receipt={receipt} />);
  await click(host.querySelector<HTMLInputElement>('input[type="checkbox"]'));
  await settle();
  expect(host.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked).toBe(true);
  expect(receipt).not.toHaveBeenCalled();
  expect(host.textContent).toContain('保存失败');
});
