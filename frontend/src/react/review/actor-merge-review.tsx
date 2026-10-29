/* 演员合并只提交当前组里逐项选定的身份，确认后刷新候选和全局计数。 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RiSearchLine, RiUserSearchLine } from '@remixicon/react';
import { Button } from '@/components/base/buttons/button';
import { Checkbox } from '@/components/base/checkbox/checkbox';
import { Input } from '@/components/base/input/input';
import { confirmModal } from '@peach/legacy/ui';
import { apiGet, apiSend, errorMessage } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { EmptyState } from '../components/empty-state';
import { Note } from '../components/note';
import { busyProps } from '../settings/use-action';
import { REVIEW_KEY } from './review';

interface Actor { id: number; name: string; scenes: number; aliases: string[]; has_image: boolean; token: string }
interface Group extends Actor { matches: number }
interface Match extends Actor { reason: string; conflicts: string[] }
interface Listing { total: number; offset: number; groups: Group[] }
interface Detail { actor: Actor; matches: Match[] }
interface Batch { id: string; created_at: string; groups: number; actors: number }
const KEY = ['actor-merge'];

function ActorName({ actor }: { actor: Actor }) {
  return <span className="flex min-w-0 items-center gap-3">
    {actor.has_image ? <img src={`/entity-image?kind=performer&id=${actor.id}&thumb=1`} alt="" loading="lazy" className="size-10 shrink-0 rounded-full object-cover" /> : null}
    <span className="min-w-0 wrap-anywhere"><span data-i18n-ignore="">{actor.name}</span>
      <span className="block text-caption-1-regular text-text-secondary">{formatTranslation('{0} scenes', String(actor.scenes))}</span>
    </span>
  </span>;
}

export function ActorMergeReview({ readOnly, receipt, openEntity }: {
  readOnly: boolean; receipt(message: string): void; openEntity(kind: string, name: string): void;
}) {
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [actorId, setActorId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState('');
  const [hideConflicts, setHideConflicts] = useState(() => localStorage.getItem('peach.actor-merge.hide-conflicts') === '1');
  const [preferred, setPreferred] = useState<{ id: number; name: string } | null>(null);
  const list = useQuery({ queryKey: [...KEY, search, offset, hideConflicts], queryFn: ({ signal }) => apiGet<Listing>(`/api/actor-merge?query=${encodeURIComponent(search)}&offset=${offset}&hide_conflicts=${hideConflicts ? 1 : 0}`, signal) });
  const history = useQuery({ queryKey: [...KEY, 'history'], queryFn: ({ signal }) => apiGet<{ batches: Batch[] }>('/api/actor-merge?mode=history', signal) });
  const detail = useQuery({ queryKey: [...KEY, 'detail', actorId], enabled: actorId !== null,
    queryFn: ({ signal }) => apiGet<Detail>(`/api/actor-merge?actor_id=${actorId}`, signal) });
  const data = detail.data;
  const name = preferred?.id === data?.actor.id ? preferred?.name || '' : data?.actor.name || '';
  const eligible = data?.matches.filter(match => !match.conflicts.length) || [];
  const choose = (id: number) => { setActorId(id); setSelected([]); setProblem(''); };
  const refresh = async () => {
    setActorId(null); setSelected([]); setOffset(0);
    await Promise.all([queryClient.invalidateQueries({ queryKey: KEY }), queryClient.invalidateQueries({ queryKey: REVIEW_KEY })]);
  };
  const automatic = async () => {
    setBusy(true); setProblem('');
    try {
      const plan = await apiGet<{ groups: number; actors: number; token: string }>('/api/actor-merge?mode=automatic');
      if (!plan.actors) { setProblem('No high-confidence actor matches to merge.'); return; }
      await confirmModal({ title: 'Automatically Merge All', confirmLabel: 'Automatically Merge All',
        body: formatTranslation('Merge {0} duplicate actors across {1} groups in the entire library? Actor data and pictures will be backed up, with undo available here.', String(plan.actors), String(plan.groups)),
        onConfirm: async () => {
          await apiSend('/api/actor-merge', { action: 'automatic', expected: plan.token, confirmed: true });
          await refresh(); receipt('High-confidence actors merged.');
        } });
    } catch (cause) { setProblem(errorMessage(cause)); }
    finally { setBusy(false); }
  };
  const undo = (batch: Batch) => {
    void confirmModal({ title: 'Undo actor merge', confirmLabel: 'Undo actor merge',
      body: formatTranslation('Restore {0} actors from this merge? Later edits to affected records may prevent undo.', String(batch.actors)),
      onConfirm: async () => {
        setBusy(true); setProblem('');
        try {
          await apiSend('/api/actor-merge', { action: 'undo', batch_id: batch.id, confirmed: true });
          await refresh(); receipt('Actor merge undone.');
        } catch (cause) { setProblem(errorMessage(cause)); throw cause; }
        finally { setBusy(false); }
      } });
  };
  const merge = () => {
    if (!data || !selected.length || busy) return;
    const chosen = data.matches.filter(match => selected.includes(match.id));
    void confirmModal({ title: 'Merge selected actors', confirmLabel: 'Merge selected actors',
      body: formatTranslation('Merge {0} into {1}? This cannot be undone in the interface. A backup will be saved.', chosen.map(actor => actor.name).join(', '), name),
      onConfirm: async () => {
        setBusy(true); setProblem('');
        try {
          await apiSend('/api/actor-merge', { actor_id: data.actor.id, merge_ids: selected, name, confirmed: true,
            expected: Object.fromEntries([data.actor, ...chosen].map(actor => [String(actor.id), actor.token])) });
          setActorId(null); setSelected([]); setOffset(0);
          await Promise.all([queryClient.invalidateQueries({ queryKey: KEY }), queryClient.invalidateQueries({ queryKey: REVIEW_KEY })]);
          receipt('Selected actors merged.');
        } catch (cause) { setProblem(errorMessage(cause)); throw cause; }
        finally { setBusy(false); }
      } });
  };
  return <section className="flex min-w-0 flex-col gap-4" aria-label="Actor merge">
    <h2 className="text-title-2-medium">Actor merge</h2>
    <Input type="search" leadingIcon={RiSearchLine} label="Search actor merge suggestions" value={search}
      onChange={value => { setSearch(value); setOffset(0); setActorId(null); setSelected([]); }} />
    <Button type="button" variant="secondary" size="small" onClick={() => { setSelected([]); void queryClient.invalidateQueries({ queryKey: KEY }); }}>Refresh suggestions</Button>
    <Checkbox isSelected={hideConflicts} onChange={value => {
      setHideConflicts(value); localStorage.setItem('peach.actor-merge.hide-conflicts', value ? '1' : '0'); setOffset(0); setSelected([]); setActorId(null);
    }}>Hide suggestions with only conflicting source identities</Checkbox>
    <Button type="button" variant="secondary" disabled={readOnly} {...busyProps(busy)} onClick={() => { void automatic(); }}>Automatically Merge All</Button>
    <p className="text-caption-1-regular text-text-secondary">Includes matching aliases and full-name matches. Conflicting identities and fuzzy spelling matches stay for manual review.</p>
    {history.error ? <Note tone="error">{errorMessage(history.error)}</Note> : null}
    {history.data?.batches?.map(batch => <div key={batch.id} className="flex flex-wrap items-center justify-between gap-2">
      <span>{formatTranslation('{0} actors merged · {1}', String(batch.actors), new Date(batch.created_at).toLocaleString())}</span>
      <Button type="button" variant="secondary" disabled={readOnly || busy} onClick={() => undo(batch)}>Undo actor merge</Button>
    </div>)}
    {list.error ? <Note tone="error">{errorMessage(list.error)}</Note> : null}
    {list.isPending ? <div data-skeleton="" aria-label="Loading actor suggestions" className="h-20 rounded-lg bg-background-secondary-default" /> : null}
    {!list.isPending && !list.data?.groups.length && !list.error ? <EmptyState icon={RiUserSearchLine} title="No actor merge suggestions">Similar actor names will appear here for review.</EmptyState> : null}
    <div className="flex min-w-0 flex-col gap-4 lg:flex-row">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {list.data?.groups.map(actor => <button key={actor.id} type="button" aria-pressed={actorId === actor.id} data-actor-merge-group=""
          className={`flex min-w-0 flex-col items-start gap-2 rounded-lg border border-separator-border p-3 text-left ${actorId === actor.id ? 'bg-background-secondary-default' : 'hover:bg-background-primary-hover'}`}
          onClick={() => choose(actor.id)}><span className="flex min-w-0 flex-col items-start gap-1 whitespace-normal">
            <ActorName actor={actor} /><span>{formatTranslation('{0} possible duplicates', String(actor.matches))}</span>
          </span></button>)}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        {detail.isFetching && actorId !== null ? <div data-skeleton="" aria-label="Loading possible matches" className="h-20 rounded-lg bg-background-secondary-default" /> : null}
        {detail.error ? <Note tone="error">{errorMessage(detail.error)}</Note> : null}
        {data && actorId === data.actor.id ? <>
          <h3 className="text-body-medium wrap-anywhere">{formatTranslation('Merge into {0}', data.actor.name)}</h3>
          <Input label="Canonical actor name" value={name} onChange={value => setPreferred({ id: data.actor.id, name: value })} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="small" disabled={readOnly || busy} onClick={() => setSelected(eligible.map(actor => actor.id))}>全选</Button>
            <Button type="button" variant="secondary" size="small" disabled={readOnly || busy} onClick={() => setSelected([])}>取消全选</Button>
            <Button type="button" variant="secondary" size="small" onClick={() => openEntity('performer', data.actor.name)}>View actor</Button>
          </div>
          {data.matches.map(match => <div key={match.id} className="flex min-w-0 flex-col gap-2 rounded-lg border border-separator-border p-3">
            <Checkbox isSelected={selected.includes(match.id)} isDisabled={readOnly || busy || Boolean(match.conflicts.length)}
              onChange={checked => setSelected(previous => checked ? [...previous, match.id] : previous.filter(id => id !== match.id))}
              ><ActorName actor={match} /></Checkbox>
            <p className="text-caption-1-regular text-text-secondary">{match.reason}</p>
            {match.aliases.length ? <p className="break-words text-caption-1-regular" data-i18n-ignore="">{match.aliases.join(', ')}</p> : null}
            {match.conflicts.length ? <Note tone="warning">Conflicting source identities; review separately.</Note> : null}
          </div>)}
          <Button type="button" disabled={readOnly || !name.trim() || !selected.length || selected.length > 2000} {...busyProps(busy)} onClick={merge}>Merge selected actors</Button>
        </> : null}
        {problem ? <Note tone="error">{problem}</Note> : null}
      </div>
    </div>
    {(list.data?.total || 0) > 20 ? <div className="flex flex-wrap justify-between gap-2">
      <Button type="button" variant="secondary" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 20))}>上一页</Button>
      <Button type="button" variant="secondary" disabled={offset + 20 >= (list.data?.total || 0)} onClick={() => setOffset(value => value + 20)}>下一页</Button>
    </div> : null}
  </section>;
}
