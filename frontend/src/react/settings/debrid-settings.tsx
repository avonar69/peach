import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { Switch } from '@/components/base/switch/switch';
import { apiGet, apiSend } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { ErrorText, Footer, Help, Section, Stack } from './section';
import { busyProps, useAction } from './use-action';

export interface DebridProvider { id: string; label: string; configured: boolean; download_folder: string; hosts: string[]; auto_import?: boolean; max_concurrent_downloads?: number }
const KEY = ['debrid-settings'];
const URL = '/api/configuration/debrid';
interface SettingsData { providers: DebridProvider[]; available?: boolean }

function ProviderSettings({ provider, receipt }: { provider: DebridProvider; receipt(message: string): void }) {
  const [key, setKey] = useState('');
  const [folder, setFolder] = useState(provider.download_folder);
  const [autoImport, setAutoImport] = useState(!!provider.auto_import);
  const [concurrency, setConcurrency] = useState(String(provider.max_concurrent_downloads ?? 3));
  const [connected, setConnected] = useState(false);
  const action = useAction();
  useEffect(() => setFolder(provider.download_folder), [provider.download_folder]);
  useEffect(() => setAutoImport(!!provider.auto_import), [provider.auto_import]);
  useEffect(() => setConcurrency(String(provider.max_concurrent_downloads ?? 3)), [provider.max_concurrent_downloads]);
  const save = (remove = false, requested = Number(concurrency)) => {
    void action.run('save', async signal => {
      await apiSend(`${URL}/${provider.id}/settings`, {
      api_key: key, download_folder: folder, auto_import: autoImport, max_concurrent_downloads: requested, ...(remove ? { remove_key: true } : {}),
      }, 'POST', signal);
      const confirmed = await apiGet<SettingsData>(URL, signal);
      if (!remove && confirmed.providers.find(item => item.id === provider.id)?.max_concurrent_downloads !== requested) {
        throw new Error('The download limit was not saved. Reload settings and try again.');
      }
      queryClient.setQueryData(KEY, confirmed);
    }, () => {
      setKey(''); setConnected(false); receipt('Debrid settings saved.');
      void queryClient.invalidateQueries({ queryKey: KEY });
      void queryClient.invalidateQueries({ queryKey: ['rss-downloads'] });
    });
  };
  return <Section title={provider.label} onSubmit={event => {
    event.preventDefault();
    save(false, Number(new FormData(event.currentTarget).get('max_concurrent_downloads') ?? concurrency));
  }}>
    <Stack>
      <Input type="password" autoComplete="new-password" label="API key" aria-label={`${provider.label} API key`}
        placeholder={provider.configured ? 'Key saved; leave blank to keep it' : 'Enter your API key'} value={key} onChange={setKey} />
      <Help><a href={provider.id === 'alldebrid' ? 'https://alldebrid.com/apikeys/' : 'https://real-debrid.com/apitoken'}
        target="_blank" rel="noreferrer">Get your API key</a></Help>
      <Input label="Download folder" aria-label={`${provider.label} download folder`} value={folder} onChange={value => {
        setFolder(value); if (!value.trim()) setAutoImport(false);
      }}
        placeholder="/downloads" />
      <Help>For Docker, enter an existing writable folder inside the container, such as /downloads, and mount your host folder there.</Help>
      <Help>A configured folder receives downloads from the debrid icons. Leave it blank to download in your browser.</Help>
      <Input label="Maximum concurrent downloads" aria-label={formatTranslation('Concurrent downloads for {0}', provider.label)}
        name="max_concurrent_downloads" type="number" value={concurrency} onChange={setConcurrency} />
      <Help>Each provider downloads up to this many files at once. Waiting files start automatically. Default: 3.</Help>
      <Switch aria-label={formatTranslation('Automatic import for {0}', provider.label)} isDisabled={!folder.trim()}
        isSelected={autoImport} onChange={setAutoImport}>Scan and import after download</Switch>
      <Help>Automatic import processes only the completed video. Choose a download folder inside a configured media library, using the container path in Docker.</Help>
      {connected ? <p role="status">{formatTranslation('Connected to {0}.', provider.label)}</p> : null}
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}
    </Stack>
    <Footer>
      <Button type="submit" disabled={!Number.isInteger(Number(concurrency)) || Number(concurrency) < 1 || Number(concurrency) > 10}
        {...busyProps(action.busy === 'save')}>Save debrid settings</Button>
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
