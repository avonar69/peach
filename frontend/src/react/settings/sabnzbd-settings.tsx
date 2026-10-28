import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { apiGet, apiSend } from '../../api';
import { formatTranslation } from '../../i18n';
import { queryClient } from '../query';
import { ErrorText, Footer, Help, Section, Stack } from './section';
import { busyProps, useAction } from './use-action';

interface Settings { url: string; category: string; username?: string; configured: boolean; available?: boolean }

export function SABnzbdSettings({ receipt }: { receipt(message: string): void }) {
  return <NZBProviderSettings provider="sabnzbd" receipt={receipt} />;
}

export function NZBGetSettings({ receipt }: { receipt(message: string): void }) {
  return <NZBProviderSettings provider="nzbget" receipt={receipt} />;
}

function NZBProviderSettings({ provider, receipt }: { provider: 'sabnzbd' | 'nzbget'; receipt(message: string): void }) {
  const URL = `/api/configuration/${provider}`;
  const label = provider === 'sabnzbd' ? 'SABnzbd' : 'NZBGet';
  const text = (suffix: string) => formatTranslation(`${label} ${suffix}`);
  const state = useQuery({ queryKey: [provider + '-settings'], queryFn: ({ signal }) => apiGet<Settings>(URL, signal) });
  const [url, setUrl] = useState(''), [category, setCategory] = useState(''), [key, setKey] = useState('');
  const [username, setUsername] = useState('');
  const [connected, setConnected] = useState(false);
  const action = useAction();
  useEffect(() => {
    if (state.data) { setUrl(state.data.url || ''); setCategory(state.data.category || ''); setUsername(state.data.username || ''); }
  }, [state.data]);
  const save = (remove = false) => void action.run('save', signal => apiSend(`${URL}/settings`, {
    url, category, ...(provider === 'sabnzbd' ? { api_key: key } : { username, password: key }), remove_key: remove,
  }, 'POST', signal), () => {
    setKey(''); setConnected(false); receipt(text('settings saved.'));
    void queryClient.invalidateQueries({ queryKey: [provider + '-settings'] });
    void queryClient.invalidateQueries({ queryKey: ['rss-downloads'] });
  });
  if (state.isPending) return <p role="status">Loading download providers…</p>;
  if (state.isError) return <ErrorText>{String(state.error)}</ErrorText>;
  return <fieldset disabled={state.data.available === false}>
    <Section title={label} onSubmit={event => { event.preventDefault(); save(); }}>
      <Stack>
        <Input label={text('server URL')} value={url} onChange={setUrl} placeholder={provider === 'sabnzbd' ? 'http://sabnzbd:8080' : 'http://nzbget:6789'} />
        {provider === 'nzbget' ? <Input label="NZBGet username" value={username} onChange={setUsername} /> : null}
        <Input label={text(provider === 'sabnzbd' ? 'API key' : 'password')} type="password" value={key} onChange={setKey}
          placeholder={provider === 'sabnzbd' ? state.data.configured ? 'Key saved; leave blank to keep it' : 'Enter your API key'
            : state.data.configured ? 'Password saved; leave blank to keep it' : 'Enter your password'} />
        <Input label={text('category')} value={category} onChange={setCategory} />
        {provider === 'sabnzbd' ? <>
          <Help>Use the full API key from SABnzbd settings. In Docker, use a server address reachable from the Peach container.</Help>
          <Help>NZB files download to the folders configured in SABnzbd.</Help>
          <Help>For SABconnect++, right-click Download NZB and use the extension’s Send to SABnzbd action.</Help>
        </> : <>
          <Help>Use your NZBGet username and password. In Docker, use a server address reachable from the Peach container.</Help>
          <Help>NZB files download to the folders configured in NZBGet.</Help>
        </>}
        {connected ? <p role="status">{text('connection successful.')}</p> : null}
        {action.error ? <ErrorText>{action.error}</ErrorText> : null}
      </Stack>
      <Footer>
        <Button type="submit" disabled={!url.trim() || (provider === 'nzbget' && !username.trim())} {...busyProps(action.busy === 'save')}>{formatTranslation('Save {0} settings', label)}</Button>
        <Button type="button" variant="secondary" disabled={!state.data.configured} {...busyProps(action.busy === 'check')}
          onClick={() => void action.run('check', signal => apiSend(`${URL}/check`, {}, 'POST', signal), () => {
            setConnected(true); receipt(text('connection successful.'));
          })}>Test connection</Button>
        <Button type="button" variant="secondary" disabled={!state.data.configured} {...busyProps(action.busy === 'save')}
          onClick={() => save(true)}>{provider === 'sabnzbd' ? 'Remove API key' : 'Remove password'}</Button>
      </Footer>
    </Section>
  </fieldset>;
}
