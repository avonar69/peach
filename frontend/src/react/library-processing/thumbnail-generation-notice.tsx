import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RiFilmLine } from '@remixicon/react';
import { toast } from 'sonner';
import { Button } from '@/components/base/buttons/button';
import { apiGet, apiSend } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { TaskPopup } from '../components/task-popup';
import { Note } from '../components/note';
import { Fieldset, FieldsetTitle } from '../components/fieldset';
import { useAction } from '../settings/use-action';
import { THUMBNAIL_JOBS_KEY, THUMBNAIL_JOBS_URL } from '../settings-panel/settings-data';
import { ProcessingMode } from './processing-effort';
import type { ProcessingSpeed } from './library-processing';

interface ThumbnailJob { status: string; done: number; total: number; current_frame?: number; current_frames?: number; speed_mode?: ProcessingSpeed }
const ID = 'peach-timeline-generation';

function useThumbnailGeneration() {
  const action = useAction();
  const state = useQuery({ queryKey: THUMBNAIL_JOBS_KEY, refetchOnMount: 'always',
    queryFn: ({ signal }) => apiGet<ThumbnailJob>(THUMBNAIL_JOBS_URL, signal),
    refetchInterval: query => query.state.data?.status === 'running' ? 2000 : 5000 });
  const job = state.data;
  const stop = () => {
    void action.run('stop', signal => apiSend<ThumbnailJob>(THUMBNAIL_JOBS_URL, { mode: 'off' }, 'POST', signal),
      result => { queryClient.setQueryData(THUMBNAIL_JOBS_KEY, result) });
  };
  const speed = (speed_mode: ProcessingSpeed) => {
    void action.run('speed', signal => apiSend<ThumbnailJob>(THUMBNAIL_JOBS_URL, { action: 'set_speed', speed_mode }, 'POST', signal),
      result => { queryClient.setQueryData(THUMBNAIL_JOBS_KEY, result) });
  };
  return { job, action, stop, speed };
}

function ThumbnailActions({ controls }: { controls: ReturnType<typeof useThumbnailGeneration> }) {
  const { job, action, stop, speed } = controls;
  return <div className="flex flex-wrap items-center gap-2">
    <ProcessingMode value={job?.speed_mode || 'low'} busy={!!action.busy} onChange={speed} />
    <Button variant="secondary" size="small" disabled={!!action.busy} onClick={stop}>Stop thumbnail generation</Button>
  </div>;
}

function ThumbnailProgress({ job }: { job: ThumbnailJob }) {
  return <>
    <p>{formatTranslation('{0} of {1} videos', String(job.done), String(job.total))}</p>
    {job.total > 0 ? <progress aria-label="Thumbnail generation progress" max={job.total} value={job.done} /> : null}
    {!!job.current_frames && <p>{formatTranslation('{0} of {1} frames', String(job.current_frame || 0), String(job.current_frames))}</p>}
  </>;
}

export function ThumbnailGenerationCard() {
  const controls = useThumbnailGeneration();
  const { job, action } = controls;
  if (job?.status !== 'running') return null;
  return <Fieldset layout="stack" label="Generating seek thumbnails" footer={<ThumbnailActions controls={controls} />}>
    <FieldsetTitle>Generating seek thumbnails</FieldsetTitle>
    <ThumbnailProgress job={job} />
    {action.error && <Note tone="error">{action.error}</Note>}
  </Fieldset>;
}

/** 时间轴采集独立于馆藏扫描，始终提供实际进度与停止入口。 */
export function ThumbnailGenerationNotice() {
  const [expanded, setExpanded] = useState(true);
  const controls = useThumbnailGeneration();
  const { job, action } = controls;
  useEffect(() => {
    if (job?.status !== 'running') { toast.dismiss(ID); return; }
    toast.custom(() => <div className="peach-react"><TaskPopup title="Generating seek thumbnails" label="Generating seek thumbnails"
      expanded={expanded} toggle={() => setExpanded(value => !value)} measure icon={<RiFilmLine aria-hidden className="size-5 shrink-0" />}
      subtitle={<p className="text-caption-1-regular text-text-secondary">{formatTranslation('{0} of {1} videos', String(job.done), String(job.total))}</p>}
      footer={<ThumbnailActions controls={controls} />}>
      <ThumbnailProgress job={job} />
      {action.error && <Note tone="error">{action.error}</Note>}
    </TaskPopup></div>, { id: ID, toasterId: 'processing', className: 'processing-task-toast', duration: Infinity, dismissible: false });
  }, [job, expanded, action.busy, action.error]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { toast.dismiss(ID) }, []);
  return null;
}
