import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { SettingsRow } from '@/components/application/settings/settings-rows';
import { Input } from '@/components/base/input/input';
import { Button } from '@/components/base/buttons/button';
import { apiGet, apiSend, errorMessage } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { ErrorText, Help, Rows, Section } from './section';
import { useAction } from './use-action';

const URL = '/api/configuration/transcode-cache';
const KEY = ['transcode-cache-settings'] as const;
interface CacheSettings { folder: string; max_gb: number; used_bytes: number; active_folder: string; restart_required: boolean }

export function TranscodeCacheSettings() {
  const state = useQuery({ queryKey: KEY, queryFn: ({ signal }) => apiGet<CacheSettings>(URL, signal), refetchOnMount: 'always' });
  const [folder, setFolder] = useState('');
  const [limit, setLimit] = useState('10');
  const action = useAction();
  useEffect(() => { if (state.data) { setFolder(state.data.folder); setLimit(String(state.data.max_gb)) } }, [state.data]);
  return <Section title="Transcode storage">
    <Rows>
      <SettingsRow label="Transcode folder" description="Use an absolute server or Docker container path. Leave blank for the default cache. Changing the folder requires restarting Peach.">
        <Input aria-label="Transcode folder" value={folder} onChange={setFolder} isDisabled={!state.data || !!action.busy} />
      </SettingsRow>
      <SettingsRow label="Maximum transcode storage (GiB)" description="Shared by converted MP4 files and HLS segments. Old cache entries are removed as needed; original media stays unchanged.">
        <Input aria-label="Maximum transcode storage (GiB)" type="number" value={limit} onChange={setLimit} isDisabled={!state.data || !!action.busy} />
      </SettingsRow>
    </Rows>
    {state.data && <Help>{formatTranslation('Cache used: {0} GiB', (state.data.used_bytes / 1073741824).toFixed(2))} · {state.data.active_folder}</Help>}
    {state.data?.restart_required && <Help>Restart Peach to use the selected transcode folder. Existing cache files stay in their current folder.</Help>}
    <Button size="small" variant="secondary" disabled={!state.data || !!action.busy || !Number.isInteger(Number(limit)) || Number(limit) < 1 || Number(limit) > 1024}
      onClick={() => { void action.run('save', signal => apiSend<CacheSettings>(URL, { folder, max_gb: Number(limit) }, 'POST', signal), saved => queryClient.setQueryData(KEY, saved)) }}>Save transcode storage</Button>
    {(action.error || state.error) && <ErrorText>{action.error || errorMessage(state.error)}</ErrorText>}
  </Section>;
}
