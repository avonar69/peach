import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RiDownloadCloud2Line } from '@remixicon/react';
import { toast } from 'sonner';
import { Button } from '@/components/base/buttons/button';
import { LinkButton } from '@/components/base/buttons/link-button';
import { apiGet, apiSend, errorMessage } from '../../api';
import { formatTranslation, translate } from '../../i18n';
import { queryClient } from '../query';
import { TaskPopup } from '../components/task-popup';
import { useOverlayScrollbar } from '../components/overlay-scrollbar';
import { Note } from '../components/note';
import { useAction } from '../settings/use-action';
import type { DebridProvider } from '../settings/debrid-settings';

export interface DebridJob { id: string; entry_id: number; provider: string; kind: string; status: string; error?: string;
  source?: { url: string; kind: string }; files?: Array<{ url?: string; filename?: string; size?: number; download_id?: string }>;
  parent_id?: string; file_index?: number;
  dismissed?: boolean;
  filename?: string; bytes?: number; total?: number; path?: string;
  import_state?: string; import_error?: string; imported_asset_id?: number }
interface ProgressData { jobs: DebridJob[]; providers: DebridProvider[]; read_only?: boolean }
const KEY = ['debrid-jobs'];
const STORAGE = 'peach.debrid-progress';
const EVENT = 'peach-debrid-progress';
const TOAST = 'peach-debrid-downloads';
const importing = (job: DebridJob) => ['pending', 'queuing', 'queued', 'running'].includes(job.import_state || '');
const active = (job: DebridJob) => ['queued', 'preparing', 'downloading'].includes(job.status) || importing(job);
export function fileDownload(jobs: DebridJob[], parent: DebridJob, index: number): DebridJob | undefined {
  return jobs.find(job => job.id === parent.files?.[index]?.download_id
    || job.kind === 'download' && job.parent_id === parent.id && job.file_index === index);
}
export function fileNeedsDownload(job?: DebridJob): boolean {
  return !job || job.status === 'failed' || job.status === 'cancelled';
}
const statusLabels: Record<string, string> = { queued: 'Queued', preparing: 'Preparing download', downloading: 'Downloading',
  ready: 'Ready', complete: 'Download complete', cancelled: 'Cancelled', failed: 'Download failed' };
const importLabels: Record<string, string> = { pending: 'Import queued', queuing: 'Import queued', queued: 'Import queued',
  running: 'Importing new media', complete: 'Import complete', failed: 'Import failed', skipped: 'Import skipped', cancelled: 'Import cancelled' };

function tracked(): string[] {
  try {
    const values: unknown = JSON.parse(localStorage.getItem(STORAGE) || '[]');
    return Array.isArray(values) ? values.filter(value => typeof value === 'string').slice(-100) : [];
  } catch { return []; }
}

function saveTracked(ids: string[]) {
  try { localStorage.setItem(STORAGE, JSON.stringify(ids)) } catch { /* 当前页面仍可观察进度。 */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: ids }));
}

export function trackDebridJob(id: string) {
  saveTracked([...new Set([...tracked(), id])].slice(-100));
  void queryClient.invalidateQueries({ queryKey: KEY });
}

export function DebridTaskProgress({ job, cancel, readOnly, compact = false }: {
  job: DebridJob; cancel(id: string): void; readOnly: boolean; compact?: boolean;
}) {
  return <div className="flex min-w-0 flex-wrap items-center gap-2 text-caption-1-regular">
    <span>{translate(statusLabels[job.status] || job.status)}</span>
    {job.kind === 'download' && job.total ? <progress aria-label="Download progress" max={job.total} value={job.bytes || 0} /> : null}
    {job.filename && !compact ? <span className="break-all" data-i18n-ignore="">{job.filename}</span> : null}
    {job.kind === 'download' && job.total ? <span>{formatTranslation('{0} of {1} MB',
      ((job.bytes || 0) / 1024 / 1024).toFixed(1), (job.total / 1024 / 1024).toFixed(1))}</span> : null}
    {job.path && !compact ? <span className="break-all" data-i18n-ignore="">{job.path}</span> : null}
    {job.error ? <span role="alert">{job.error}</span> : null}
    {job.import_state ? <span>{translate(importLabels[job.import_state] || job.import_state)}</span> : null}
    {job.import_error ? <span role="alert">{job.import_error}</span> : null}
    {active(job) ? <Button size="small" variant="secondary" disabled={readOnly} onClick={() => cancel(job.id)}>
      {importing(job) && job.status === 'complete' ? 'Cancel import' : 'Cancel download'}</Button> : null}
  </div>;
}

function DownloadPanel({ jobs, providers, readOnly, problem }: {
  jobs: DebridJob[]; providers: DebridProvider[]; readOnly: boolean; problem: string;
}) {
  const [expanded, setExpanded] = useState(true);
  const action = useAction();
  const scroller = useOverlayScrollbar<HTMLDivElement>();
  const running = jobs.filter(active).length;
  const finished = jobs.some(job => job.kind === 'download' && !active(job) && ['complete', 'failed', 'cancelled'].includes(job.status));
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: KEY });
    void queryClient.invalidateQueries({ queryKey: ['rss-downloads'] }); };
  return <TaskPopup label="Debrid downloads" title="Debrid downloads" expanded={expanded} toggle={() => setExpanded(!expanded)} measure
    tone={problem || jobs.some(job => job.status === 'failed' || job.import_state === 'failed') ? 'error' : 'neutral'}
    icon={<RiDownloadCloud2Line aria-hidden className="size-5 shrink-0" />}
    subtitle={<p className="text-caption-1-regular text-text-secondary">{formatTranslation('Active downloads: {0}', String(running))}</p>}
    footer={<div className="flex flex-wrap items-center gap-2">
      <LinkButton href="/subscriptions?tab=rss" variant="secondary" size="small">View RSS downloads</LinkButton>
      <Button size="small" variant="secondary" disabled={readOnly || !finished || !!action.busy} onClick={() => {
        void action.run('clear-finished', signal => apiSend('/api/rss/clear-finished', {}, 'POST', signal), refresh);
      }}>Clear finished</Button>
    </div>}>
    {problem || action.error ? <Note tone="error">{problem || action.error}</Note> : null}
    <div ref={scroller} className="flex max-h-64 min-w-0 flex-col gap-3 overflow-auto overscroll-contain">
      {jobs.map(job => <div key={job.id} className="flex min-w-0 flex-col gap-2">
        <span className="break-words text-body-2-medium" data-i18n-ignore="">{job.filename || job.files?.[0]?.filename
          || providers.find(provider => provider.id === job.provider)?.label || job.provider}</span>
        <DebridTaskProgress job={job} compact readOnly={readOnly} cancel={id => {
          void action.run('cancel', signal => apiSend('/api/rss/cancel', { id }, 'POST', signal), refresh);
        }} />
        {job.import_state === 'failed' || job.import_state === 'cancelled' ? <Button size="small" variant="secondary" disabled={readOnly}
          onClick={() => { void action.run('import', signal => apiSend('/api/rss/import', { id: job.id }, 'POST', signal), refresh) }}>Retry import</Button> : null}
        {job.kind === 'resolve' && job.status === 'ready' ? job.files?.map((file, index) => file.url ? <div key={index}>
          {providers.find(provider => provider.id === job.provider)?.download_folder
            ? !fileNeedsDownload(fileDownload(jobs, job, index))
              ? <span>{translate(statusLabels[fileDownload(jobs, job, index)!.status] || 'Queued')}</span>
              : <Button size="small" variant="secondary" disabled={readOnly} onClick={() => {
              void action.run('download', signal => apiSend<{ id: string }>('/api/rss/download', { id: job.id, file_index: index }, 'POST', signal),
                result => { trackDebridJob(result.id); refresh() });
            }}>Download file</Button>
            : <a className="break-all underline" href={file.url} target="_blank" rel="noopener noreferrer" data-i18n-ignore="">{file.filename || translate('Download file')}</a>}
        </div> : null) : null}
      </div>)}
    </div>
  </TaskPopup>;
}

/** 挂在路由根，下载状态与浮层跨页面保留，刷新后恢复本机观察清单。 */
export function DebridDownloadDock() {
  const [ids, setIds] = useState(tracked);
  useEffect(() => {
    const update = (event: Event) => setIds(event instanceof CustomEvent ? event.detail : tracked());
    window.addEventListener(EVENT, update); window.addEventListener('storage', update);
    return () => { window.removeEventListener(EVENT, update); window.removeEventListener('storage', update) };
  }, []);
  const state = useQuery({ queryKey: KEY, enabled: !!ids.length,
    queryFn: ({ signal }) => apiGet<ProgressData>('/api/rss/jobs', signal),
    refetchInterval: query => !query.state.data || query.state.data.jobs.some(active) ? 2000 : false });
  const data = state.data;
  useEffect(() => {
    const chosen = data?.jobs.filter(job => ids.includes(job.id)) || [];
    const related = data?.jobs.filter(job => ids.includes(job.id) || job.kind === 'download'
      && chosen.some(parent => job.parent_id === parent.id || parent.files?.some(file => file.download_id === job.id))) || [];
    const jobs = related.filter(job => !job.dismissed && (job.kind !== 'resolve' || !job.files?.length
      || !job.files.every((_, index) => fileDownload(data?.jobs || [], job, index))));
    if (!ids.length || !jobs.length && !state.isError) { toast.dismiss(TOAST); return; }
    const running = jobs.some(active);
    const needsAttention = state.isError || jobs.some(job => ['ready', 'failed'].includes(job.status) || job.import_state === 'failed');
    toast.custom(() => <div className="peach-react"><DownloadPanel jobs={jobs} providers={data?.providers || []}
      readOnly={!!data?.read_only} problem={state.isError ? errorMessage(state.error) : ''} /></div>, {
      id: TOAST, toasterId: 'processing', className: 'processing-task-toast',
      duration: running || needsAttention ? Infinity : 8000, dismissible: !running, closeButton: !running,
      onDismiss: () => saveTracked([]), onAutoClose: () => saveTracked([]),
    });
  }, [ids, data, state.isError, state.error]);
  useEffect(() => () => { toast.dismiss(TOAST) }, []);
  return null;
}
