import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RiDownloadCloud2Line } from '@remixicon/react';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { Switch } from '@/components/base/switch/switch';
import { Select, SelectItem } from '@/components/base/select/select';
import { apiGet, apiSend } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { Note } from '../components/note';
import { Help, Stack } from '../settings/section';
import { busyProps, useAction } from '../settings/use-action';
import type { DebridProvider } from '../settings/debrid-settings';
import { DebridTaskProgress, fileDownload, fileNeedsDownload, trackDebridJob, type DebridJob as Job } from './debrid-progress';

interface Link { url: string; kind: string }
interface Picture { src: string; href: string }
interface Entry { id: number; source_id: number; title: string; feed_name: string; published_at: string | null; links: Link[];
  images?: { main?: Picture; previews?: Picture[] } }
interface Source { id: number; name: string; enabled: boolean; interval_minutes?: number; next_fetch_at?: string | null;
  rss_retention_count?: number | null; rss_retention_unit?: string;
  hide_unsupported?: boolean; last_error: string | null; last_fetched_at: string | null }
interface Data { providers: DebridProvider[]; sources: Source[]; items: Entry[]; jobs: Job[]; total: number; offset: number; read_only?: boolean }
const KEY = ['rss-downloads'];

export function supports(provider: DebridProvider, link: Link, confirmed = false): boolean {
  if (!provider.configured) return false;
  if (link.kind !== 'link') return true;
  if (!provider.hosts?.length) return !confirmed;
  try {
    const host = new URL(link.url).hostname;
    return provider.hosts.some(domain => host === domain || host.endsWith(`.${domain}`));
  } catch { return false; }
}

function PostPicture({ picture, title, preview = false }: { picture?: Picture; title: string; preview?: boolean }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [picture?.src]);
  if (!picture || failed) return null;
  return <a href={picture.href} target="_blank" rel="noopener noreferrer" className="flex min-w-0 flex-col items-start gap-2"
    aria-label={formatTranslation(preview ? 'Open preview for {0}' : 'Open main image for {0}', title)}>
    <img src={picture.src} alt={title} loading="lazy" decoding="async" referrerPolicy="no-referrer"
      className={preview ? 'h-auto max-h-80 max-w-full object-contain' : 'h-auto max-h-96 max-w-full object-contain'}
      onError={() => setFailed(true)} data-i18n-ignore="" />
  </a>;
}

export function RSSDownloads({ readOnly, toast, feedOnly = false, onVisibleCount, download = (url: string) => window.location.assign(url) }: {
  readOnly: boolean; toast(message: string): void; feedOnly?: boolean; onVisibleCount?(count: number): void; download?(url: string): void;
}) {
  const [name, setName] = useState(''), [url, setUrl] = useState(''), [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(() => {
    try { const saved = Number(localStorage.getItem('peach.rss-page-size')); return [10, 20, 50, 100].includes(saved) ? saved : 20; }
    catch { return 20; }
  });
  const [waiting, setWaiting] = useState<string[]>([]);
  const delivered = useRef(new Set<string>());
  const action = useAction();
  const state = useQuery({ queryKey: [...KEY, offset, pageSize], queryFn: ({ signal }) => apiGet<Data>(`/api/rss?offset=${offset}&limit=${pageSize}`, signal), refetchInterval: 3000 });
  const data = state.data;
  useEffect(() => { onVisibleCount?.(data?.items.length || 0); }, [onVisibleCount, data?.items.length]);
  useEffect(() => {
    if (feedOnly && data) void queryClient.invalidateQueries({ queryKey: ['follow-feed'] });
  }, [feedOnly, data?.total]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: KEY }); };
  const send = (kind: string, body: object, message?: string) => {
    void action.run(kind, signal => apiSend(`/api/rss/${kind}`, body, 'POST', signal), () => {
      if (message) toast(message);
      refresh();
    });
  };
  const deliver = async (job: Job, index = 0) => {
    const provider = data?.providers.find(item => item.id === job.provider);
    const file = job.files?.[index];
    if (!file?.url || !provider) return;
    if (provider.download_folder) {
      const result = await apiSend<{ id: string }>('/api/rss/download', { id: job.id, file_index: index }, 'POST');
      trackDebridJob(result.id);
      toast('Download queued.'); refresh();
    } else download(file.url);
  };
  useEffect(() => {
    if (!data) return;
    for (const id of waiting) {
      const job = data.jobs.find(item => item.id === id);
      if (!job || !['ready', 'failed', 'cancelled'].includes(job.status) || delivered.current.has(id)) continue;
      delivered.current.add(id);
      if (job.status === 'ready' && job.files?.length === 1) {
        void deliver(job).catch(() => toast('The download could not be started. Check the folder settings.'));
      } else if (job.status === 'ready') toast('Choose a file below to download.');
      setWaiting(previous => previous.filter(value => value !== id));
    }
  }, [data, waiting]); // eslint-disable-line react-hooks/exhaustive-deps
  const clickDebrid = (entry: Entry, index: number, provider: DebridProvider) => {
    void action.run('resolve', signal => apiSend<{ id: string }>('/api/rss/resolve', {
      entry_id: entry.id, link_index: index, provider: provider.id, auto_download: !!provider.download_folder,
    }, 'POST', signal), result => {
      trackDebridJob(result.id);
      delivered.current.delete(result.id);
      if (!provider.download_folder) setWaiting(previous => [...new Set([...previous, result.id])]);
      refresh();
    });
  };
  if (state.isPending) return <p role="status">Loading RSS feeds…</p>;
  if (state.isError || !data) return <Note tone="error">Could not load RSS feeds.</Note>;
  readOnly = readOnly || !!data.read_only;
  if (feedOnly && !data.items.length) return null;
  const filteredSources = new Set(data.sources.filter(source => source.hide_unsupported).map(source => source.id));
  return <Stack>
    <h2 className="text-title-2-medium">{feedOnly ? 'RSS updates' : 'RSS downloads'}</h2>
    {feedOnly ? <a href="/subscriptions?tab=rss" className="underline">Manage RSS feeds</a> : <>
    <form className="flex flex-col gap-3" onSubmit={event => {
      event.preventDefault();
      void action.run('add', signal => apiSend('/api/rss/source', { action: 'add', name, url }, 'POST', signal), () => {
        setName(''); setUrl(''); toast('RSS feed added.'); refresh();
      });
    }}>
      <Input label="Feed name" value={name} onChange={setName} />
      <Input label="RSS or Atom feed URL" value={url} onChange={setUrl} type="url" />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={readOnly || !url.trim()} {...busyProps(action.busy === 'add')}>Add RSS feed</Button>
        <Button type="button" variant="secondary" disabled={readOnly || !data.sources.length} {...busyProps(action.busy === 'check')}
          onClick={() => send('check', {}, 'RSS update started.')}>Check feeds now</Button>
        <Button type="button" variant="secondary" disabled={!data.jobs.length}
          onClick={() => data.jobs.slice(-10).forEach(job => trackDebridJob(job.id))}>Show download progress</Button>
      </div>
    </form>
    <Help>Use the debrid icon beside a supported link to download with that service. A configured download folder receives the file; otherwise it downloads in your browser.</Help>
    <a href="/settings/downloads" className="underline">Configure download providers</a>
    {action.error ? <Note tone="error">{action.error}</Note> : null}
    {data.sources.map(source => <div key={source.id} className="flex flex-wrap items-center gap-3 border-b border-border-button-default py-3">
      <span className="min-w-0 grow break-words" data-i18n-ignore="">{source.name}</span>
      <Switch aria-label={formatTranslation('Enable {0}', source.name)} isDisabled={readOnly} isSelected={source.enabled}
        onChange={enabled => send('source', { action: 'schedule', id: source.id, enabled,
          interval_minutes: source.interval_minutes ?? 360 })}>Automatic updates</Switch>
      <RSSSchedule key={`${source.id}:${source.interval_minutes}`} source={source} readOnly={readOnly}
        busy={action.busy === 'source'} save={interval_minutes => send('source', {
          action: 'schedule', id: source.id, enabled: source.enabled, interval_minutes }, 'RSS update schedule saved.')} />
      <RSSRetention key={`${source.id}:${source.rss_retention_count}:${source.rss_retention_unit}`}
        source={source} readOnly={readOnly} busy={action.busy === 'source'}
        save={(count, unit) => send('source', { action: 'retention', id: source.id, count, unit }, 'RSS retention saved.')} />
      <Switch aria-label={formatTranslation('Hide unsupported links for {0}', source.name)} isDisabled={readOnly}
        isSelected={!!source.hide_unsupported}
        onChange={hide_unsupported => send('source', { action: 'filter', id: source.id, hide_unsupported })}>
        Hide unsupported links
      </Switch>
      {source.hide_unsupported && !data.providers.some(provider => provider.configured && provider.hosts?.length)
        ? <div className="w-full"><Help>Test a configured debrid provider to load its supported hosts.</Help></div> : null}
      <Button size="small" variant="secondary" disabled={readOnly}
        onClick={() => send('source', { action: 'remove', id: source.id }, 'RSS feed removed.')}>Remove feed</Button>
      {source.last_error ? <p role="alert" className="w-full">{source.last_error}</p> : null}
    </div>)}
    <h3 className="text-title-2-medium">New videos</h3>
    </>}
    {!data.items.length ? <Help>No RSS items yet. Add a feed and check for updates.</Help> : null}
    {data.items.map(entry => <article key={entry.id} className="flex min-w-0 flex-col gap-3 border-b border-border-button-default py-4">
      <h4 className="break-words text-body-medium" data-i18n-ignore="">{entry.title}</h4>
      <p className="text-caption-1-regular" data-i18n-ignore="">{entry.feed_name} {entry.published_at ? new Date(entry.published_at).toLocaleString() : ''}</p>
      {entry.images?.main || entry.images?.previews?.length ? <div className="flex min-w-0 flex-col items-start gap-4">
        <PostPicture picture={entry.images.main} title={entry.title} />
        {entry.images.previews?.length ? <div className="flex max-w-full flex-col gap-2">
          <span className="text-caption-1-regular text-text-secondary">Previews</span>
          <div className="flex min-w-0 flex-wrap items-start gap-3">
            {entry.images.previews.map(picture => <PostPicture key={picture.src} picture={picture} title={entry.title} preview />)}
          </div>
        </div> : null}
      </div> : null}
      {entry.links.map((link, index) => filteredSources.has(entry.source_id) && !data.providers.some(provider => supports(provider, link, true))
        ? null : <div key={link.url} className="flex min-w-0 flex-wrap items-center gap-2">
        <a href={link.url} className="min-w-0 break-all underline" rel="noreferrer" target="_blank" data-i18n-ignore="">{link.url}</a>
        {data.providers.filter(provider => supports(provider, link)).map(provider => <Button key={provider.id} size="small" variant="secondary" iconOnly
          leadingIcon={RiDownloadCloud2Line} title={formatTranslation('Download with {0}', provider.label)} aria-label={formatTranslation('Download with {0}', provider.label)}
          disabled={readOnly} {...busyProps(action.busy === 'resolve')} onClick={() => clickDebrid(entry, index, provider)} />)}
      </div>)}
      {data.jobs.filter(job => job.entry_id === entry.id).map(job => <div key={job.id} className="flex flex-col gap-2">
        <DebridTaskProgress job={job} cancel={id => send('cancel', { id })} readOnly={readOnly} />
        {job.files?.map((file, index) => file.url ? <div key={index} className="flex flex-wrap items-center gap-2">
          <a href={file.url} rel="noreferrer" target="_blank" className="break-all underline" data-i18n-ignore="">{file.filename || file.url}</a>
          {fileNeedsDownload(fileDownload(data.jobs, job, index)) ? <Button size="small" variant="secondary" disabled={readOnly}
            onClick={() => void deliver(job, index).catch(() => toast('The download could not be started. Check the folder settings.'))}>Download file</Button>
            : fileDownload(data.jobs, job, index)?.status === 'complete' ? <span>Download complete</span> : null}
        </div> : null)}
      </div>)}
    </article>)}
    <div className="flex flex-wrap gap-2">
      <Select aria-label="RSS posts per page" selectedKey={String(pageSize)} onSelectionChange={value => {
        setPageSize(Number(value)); setOffset(0);
        try { localStorage.setItem('peach.rss-page-size', String(value)) } catch { /* 当前页面保留选择。 */ }
      }}>
        {[10, 20, 50, 100].map(amount => <SelectItem key={amount} id={String(amount)}>{formatTranslation('{0} posts per page', String(amount))}</SelectItem>)}
      </Select>
      <Button variant="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</Button>
      <Button variant="secondary" disabled={offset + pageSize >= data.total} onClick={() => setOffset(offset + pageSize)}>Next</Button>
    </div>
  </Stack>;
}

function RSSSchedule({ source, readOnly, busy, save }: {
  source: Source; readOnly: boolean; busy: boolean; save(minutes: number): void;
}) {
  const [hours, setHours] = useState(String((source.interval_minutes ?? 360) / 60));
  const minutes = Number(hours) * 60;
  return <form noValidate className="flex min-w-0 flex-wrap items-end gap-2" onSubmit={event => { event.preventDefault();
    if (Number.isInteger(minutes) && minutes >= 15 && minutes <= 10080) save(minutes); }}>
    <Input label="Update interval (hours)" aria-label={formatTranslation('Update interval for {0} (hours)', source.name)}
      type="number" value={hours} onChange={setHours} isDisabled={readOnly} />
    <Button type="submit" size="small" variant="secondary" {...busyProps(busy)}
      disabled={readOnly || !Number.isInteger(minutes) || minutes < 15 || minutes > 10080}>Save interval</Button>
    {source.enabled && source.next_fetch_at ? <span className="w-full text-caption-1-regular">
      {formatTranslation('Next update: {0}', new Date(source.next_fetch_at).toLocaleString())}</span> : null}
  </form>;
}

function RSSRetention({ source, readOnly, busy, save }: {
  source: Source; readOnly: boolean; busy: boolean; save(count: number | null, unit: string): void;
}) {
  const [unit, setUnit] = useState(source.rss_retention_count == null ? 'forever' : source.rss_retention_unit || 'days');
  const [count, setCount] = useState(String(source.rss_retention_count ?? 30));
  const amount = Number(count);
  const limit = unit === 'years' ? 100 : unit === 'months' ? 1200 : 36500;
  const valid = unit === 'forever' || Number.isInteger(amount) && amount >= 1 && amount <= limit;
  return <form noValidate className="flex w-full min-w-0 flex-wrap items-end gap-2" onSubmit={event => {
    event.preventDefault();
    if (valid) save(unit === 'forever' ? null : amount, unit === 'forever' ? 'days' : unit);
  }}>
    <div className="flex flex-col gap-2"><span className="text-caption-1-regular">Keep saved posts</span>
    <Select aria-label={formatTranslation('Retention for {0}', source.name)}
      selectedKey={unit} onSelectionChange={key => setUnit(String(key))} isDisabled={readOnly}>
      <SelectItem id="forever">Forever</SelectItem><SelectItem id="days">Days</SelectItem>
      <SelectItem id="months">Months</SelectItem><SelectItem id="years">Years</SelectItem>
    </Select></div>
    {unit !== 'forever' ? <Input label="Retention amount" aria-label={formatTranslation('Retention amount for {0}', source.name)}
      type="number" value={count} onChange={setCount} isDisabled={readOnly} /> : null}
    <Button type="submit" size="small" variant="secondary" {...busyProps(busy)} disabled={readOnly || !valid}>Save retention</Button>
    <div className="w-full"><Help>Posts stay saved after they leave the feed. Retention starts when first saved; updates do not reset it. Expired posts are removed from the archive; downloaded files are kept.</Help></div>
  </form>;
}
