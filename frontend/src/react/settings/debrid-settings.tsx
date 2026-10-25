import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { apiGet, apiSend } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { ErrorText, Footer, Help, Section, Stack } from './section';
import { busyProps, useAction } from './use-action';

export interface DebridProvider { id: string; label: string; configured: boolean; download_folder: string; hosts: string[] }
const KEY = ['debrid-settings'];
const URL = '/api/configuration/debrid';

function ProviderSettings({ provider, receipt }: { provider: DebridProvider; receipt(message: string): void }) {
  const [key, setKey] = useState('');
  const [folder, setFolder] = useState(provider.download_folder);
  const [connected, setConnected] = useState(false);
  const action = useAction();
  useEffect(() => setFolder(provider.download_folder), [provider.download_folder]);
  const save = (remove = false) => {
    void action.run('save', signal => apiSend(`${URL}/${provider.id}/settings`, {
      api_key: key, download_folder: folder, ...(remove ? { remove_key: true } : {}),
    }, 'POST', signal), () => {
      setKey(''); setConnected(false); receipt('Debrid settings saved.');
      void queryClient.invalidateQueries({ queryKey: KEY });
      void queryClient.invalidateQueries({ queryKey: ['rss-downloads'] });
    });
  };
  return <Section title={provider.label} onSubmit={event => { event.preventDefault(); save(); }}>
    <Stack>
      <Input type="password" autoComplete="new-password" label="API key" aria-label={`${provider.label} API key`}
        placeholder={provider.configured ? 'Key saved; leave blank to keep it' : 'Enter your API key'} value={key} onChange={setKey} />
      <Help><a href={provider.id === 'alldebrid' ? 'https://alldebrid.com/apikeys/' : 'https://real-debrid.com/apitoken'}
        target="_blank" rel="noreferrer">Get your API key</a></Help>
      <Input label="Download folder" aria-label={`${provider.label} download folder`} value={folder} onChange={setFolder}
        placeholder="/downloads" />
      <Help>For Docker, enter an existing writable folder inside the container, such as /downloads, and mount your host folder there.</Help>
      <Help>A configured folder receives downloads from the debrid icons. Leave it blank to download in your browser.</Help>
      {connected ? <p role="status">{formatTranslation('Connected to {0}.', provider.label)}</p> : null}
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}
    </Stack>
    <Footer>
      <Button type="submit" {...busyProps(action.busy === 'save')}>Save debrid settings</Button>
      <Button type="button" variant="secondary" disabled={!provider.configured} {...busyProps(action.busy === 'check')}
        onClick={() => void action.run('check', signal => apiSend(`${URL}/${provider.id}/check`, {}, 'POST', signal), () => {
          setConnected(true); receipt('Debrid connection successful.');
          void queryClient.invalidateQueries({ queryKey: ['rss-downloads'] });
        })}>Test connection</Button>
      <Button type="button" variant="secondary" disabled={!provider.configured} {...busyProps(action.busy === 'save')}
        onClick={() => save(true)}>Remove API key</Button>
    </Footer>
  </Section>;
}

export function DebridSettings({ receipt }: { receipt(message: string): void }) {
  const state = useQuery({ queryKey: KEY, queryFn: ({ signal }) => apiGet<{ providers: DebridProvider[]; available?: boolean }>(URL, signal) });
  if (state.isPending) return <p role="status">Loading debrid providers…</p>;
  if (state.isError) return <ErrorText>{String(state.error)}</ErrorText>;
  return <fieldset disabled={state.data.available === false} className="flex min-w-0 flex-col gap-6">
    {state.data.providers.map(provider => <ProviderSettings key={provider.id} provider={provider} receipt={receipt} />)}
  </fieldset>;
}
