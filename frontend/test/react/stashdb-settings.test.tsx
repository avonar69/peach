/* 实体重新同步只提交演员或厂牌阶段，忙碌任务给出可恢复反馈。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StashDBSettings } from '../../src/react/settings/stashdb-settings';
import { click, mount, settle } from './render';

const send = vi.hoisted(() => vi.fn());
vi.mock('../../src/api', () => ({ apiSend: send, errorMessage: (error: Error) => error.message }));
const policy = { enabled: false, actor_images: true, scene_images: false, correct_cast: false,
  auto_apply: false, api_key_set: true, endpoint: 'https://stashdb.org/graphql' };
beforeEach(() => localStorage.setItem('peach.language', 'en'));
afterEach(() => { send.mockReset(); localStorage.clear(); });

describe('StashDB entity resync', () => {
  it('saves ignored text and requests a scoped StashDB rematch', async () => {
    const initial = { ...policy, ignore_terms: '!' };
    send.mockImplementation((path, body) => Promise.resolve(path.endsWith('/settings') ? initial : { requested_stage: body.stage }));
    const host = await mount(<StashDBSettings initial={initial} receipt={vi.fn()} />);
    await click([...host.querySelectorAll('button')].find(node => node.textContent === 'Rematch affected files with StashDB'));
    await settle();
    expect(send.mock.calls.map(call => call[0])).toEqual(['/api/configuration/stashdb/settings', '/api/library-processing']);
    expect(send.mock.calls[0]![1].ignore_terms).toBe('!');
    expect(send.mock.calls[1]![1]).toEqual({ stage: 'stashdb_ignored' });
  });
  it('starts actor and studio tasks with separate scopes even when automatic scanning is off', async () => {
    send.mockImplementation((_path, body) => Promise.resolve({ requested_stage: body.stage }));
    const receipt = vi.fn();
    const host = await mount(<StashDBSettings initial={policy} receipt={receipt} />);
    for (const label of ['Resync Actors', 'Resync Studios']) {
      const button = [...host.querySelectorAll('button')].find(node => node.textContent === label)!;
      await click(button); await settle();
    }
    expect(send.mock.calls.map(call => call[1])).toEqual([{ stage: 'stashdb_actors' }, { stage: 'stashdb_studios' }]);
    expect(receipt).toHaveBeenCalledTimes(2);
  });
  it('reports an existing scan instead of announcing that resync started', async () => {
    send.mockResolvedValue({ requested_stage: 'all' });
    const receipt = vi.fn();
    const host = await mount(<StashDBSettings initial={policy} receipt={receipt} />);
    await click([...host.querySelectorAll('button')].find(node => node.textContent === 'Resync Actors')!);
    await settle();
    expect(host.textContent).toContain('A scan is already running.');
    expect(receipt).not.toHaveBeenCalled();
  });
});
