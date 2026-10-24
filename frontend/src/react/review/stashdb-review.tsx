/* StashDB 的排队复核与手工查找共用同一入口；选项仍由来源配置保存。 */
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { Select, SelectItem } from '@/components/base/select/select';
import { confirmModal } from '@peach/legacy/ui';
import { apiGet, apiSend } from '../../api';
import { translate } from '../../i18n';
import { LoadingDots } from '../components/loading-dots';
import { ErrorText, Help, Section, Stack } from '../settings/section';
import { busyProps, useAction } from '../settings/use-action';

interface Candidate { id: string; title: string; date?: string; studio?: string; actors?: string[];
  score: number; reasons: string[]; disambiguation?: string; url: string }
interface Preview { candidates: Candidate[]; token?: string; review_required: boolean; truncated?: boolean }
interface Choice { id: number; label: string; preview?: Preview }

export function StashDBReview({ readOnly, receipt, onCount }: {
  readOnly: boolean; receipt(message: string): void; onCount(count: number): void;
}) {
  const client = useQueryClient();
  const queue = useQuery({ queryKey: ['stashdb-review'],
    queryFn: ({ signal }) => apiGet<Choice[]>('/api/configuration/stashdb/review', signal) });
  const [kind, setKind] = useState<'scene' | 'actor'>('scene');
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<Choice[] | null>(null);
  const [selected, setSelected] = useState<Choice | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const action = useAction();
  const choices = found ?? queue.data ?? [];
  useEffect(() => { onCount(queue.data?.length || 0); }, [queue.data, onCount]);
  const target = () => kind === 'actor' ? { performer_id: selected!.id } : { asset_id: selected!.id };
  const refresh = () => {
    setSelected(null); setPreview(null);
    void client.invalidateQueries({ queryKey: ['stashdb-review'] });
    void client.invalidateQueries({ queryKey: ['review'] });
  };
  const apply = (candidate: Candidate) => void confirmModal({
    title: 'Apply StashDB match', confirmLabel: 'Apply match',
    body: `${selected?.label} → ${candidate.title}. ${translate('Apply the saved image and cast options to this library item.')}`,
    onConfirm: async () => {
      const result = await apiSend<{ actor_photos: number; scene_picture?: boolean; skipped?: number }>(
        '/api/configuration/stashdb/apply', { ...target(), stashdb_id: candidate.id, token: preview?.token });
      refresh();
      receipt(result.skipped ? 'Already up to date.' : translate('StashDB match applied. Actor photos: {0}. Scene pictures: {1}.')
        .replace('{0}', String(result.actor_photos || 0)).replace('{1}', result.scene_picture ? '1' : '0'));
    },
  });
  return <Section title="StashDB matches">
    <Stack>
      <Help>Review queued scene matches or find a scene or actor in your library. Picture and cast options come from Sources & subscriptions.</Help>
      <a href="/settings/subscriptions" className="underline">Configure StashDB</a>
      <Select aria-label="StashDB match type" selectedKey={kind} onSelectionChange={key => {
        if (key !== 'scene' && key !== 'actor') return;
        setKind(key); setFound(key === 'scene' ? null : []); setSelected(null); setPreview(null);
      }}><SelectItem id="scene" textValue="Scene">Scene</SelectItem><SelectItem id="actor" textValue="Actor">Actor</SelectItem></Select>
      <Input label="Find a scene or actor in your library" value={query} onChange={setQuery} />
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" {...busyProps(action.busy === 'library')}
          onClick={() => void action.run('library', signal => apiGet<Choice[]>(`/api/configuration/stashdb/library?kind=${kind}&query=${encodeURIComponent(query)}`, signal),
            rows => { setFound(rows); setSelected(null); setPreview(null); })}>Find library items</Button>
        <Button type="button" variant="secondary" {...busyProps(queue.isFetching)} onClick={() => {
          setKind('scene'); setFound(null); refresh();
        }}>Review matches from metadata scans</Button>
      </div>
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}
      {queue.isError ? <ErrorText>{String(queue.error.message)}</ErrorText> : null}
      {queue.isPending ? <LoadingDots label="Loading StashDB reviews…" /> : null}
      {!queue.isPending && !choices.length ? <Help>No StashDB matches are waiting for review.</Help> : null}
      {choices.length ? <div className="flex max-h-60 flex-col gap-2 overflow-y-auto">{choices.map(choice =>
        <Button key={choice.id} type="button" variant="secondary" aria-pressed={selected?.id === choice.id}
          onClick={() => { setSelected(choice); setPreview(choice.preview || null); }}><span data-i18n-ignore="">{choice.label}</span></Button>)}</div> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={!selected} {...busyProps(action.busy === 'preview')}
          onClick={() => void action.run('preview', signal => apiSend<Preview>('/api/configuration/stashdb/preview', target(), 'POST', signal), setPreview)}>Preview StashDB matches</Button>
        {kind === 'scene' && selected?.preview ? <Button type="button" variant="secondary" disabled={readOnly}
          {...busyProps(action.busy === 'dismiss')} onClick={() => void action.run('dismiss', signal => apiSend(
            '/api/configuration/stashdb/dismiss', { asset_id: selected.id, token: preview?.token }, 'POST', signal), () => {
            refresh(); receipt('StashDB scene matches dismissed.');
          })}>Dismiss scene matches</Button> : null}
      </div>
      {preview?.truncated ? <Help>More results exist. Refine the local title, date, studio, or actors before applying a match.</Help> : null}
      {preview && !preview.candidates.length ? <Help>No StashDB match found. Check the scene title, studio, date, and actors.</Help> : null}
      {preview?.candidates.map(candidate => <article key={candidate.id} className="flex flex-col gap-2 rounded-lg border border-separator-border p-3">
        <a href={candidate.url} target="_blank" rel="noreferrer" data-i18n-ignore="">{candidate.title}{candidate.disambiguation ? ` (${candidate.disambiguation})` : ''}</a>
        <p data-i18n-ignore="">{[candidate.studio, candidate.date, candidate.actors?.join(', ')].filter(Boolean).join(' · ')}</p>
        <p>Match score: {Math.round(candidate.score * 100)}%</p>
        <ul>{candidate.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
        <Button type="button" disabled={readOnly} onClick={() => apply(candidate)}>Apply selected match</Button>
      </article>)}
    </Stack>
  </Section>;
}
