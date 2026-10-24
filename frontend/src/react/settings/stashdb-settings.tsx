import { useState, type FormEvent } from 'react';
import { SettingsRow } from '@/components/application/settings/settings-rows';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { Switch } from '@/components/base/switch/switch';
import { apiSend } from '../../api';
import { ErrorText, Footer, Help, Rows, Section, Stack } from './section';
import { busyProps, useAction } from './use-action';
import { LIBRARY_PROCESSING_URL } from '../library-processing/library-processing';

export interface StashDBPolicy {
  enabled: boolean; actor_images: boolean; scene_images: boolean; correct_cast: boolean; auto_apply: boolean;
  api_key_set: boolean; endpoint: string;
  ignore_terms?: string; minimum_confidence?: number;
  skip_failed?: boolean; only_new_media?: boolean;
}
const OPTIONS = [
  ['enabled', 'Enable StashDB during metadata scans'], ['actor_images', 'Scrape actor photos'],
  ['scene_images', 'Scrape scene pictures'], ['correct_cast', 'Correct filename actor assignments using matched StashDB scenes'],
  ['auto_apply', 'Automatically apply strong, unique scene matches'],
  ['skip_failed', 'Skip previously failed or unmatched StashDB searches'],
  ['only_new_media', 'Only match newly added media'],
] as const;
export function StashDBSettings({ initial, receipt, readOnly = false }: {
  initial: StashDBPolicy; receipt(message: string): void; readOnly?: boolean;
}) {
  const [policy, setPolicy] = useState(initial);
  const [apiKey, setApiKey] = useState('');
  const [account, setAccount] = useState<string | null>(null);
  const action = useAction();
  const save = (event: FormEvent) => {
    event.preventDefault();
    const body = { ...Object.fromEntries(OPTIONS.map(([key]) => [key, Boolean(policy[key])])),
      ignore_terms: policy.ignore_terms || '', minimum_confidence: policy.minimum_confidence ?? 85,
      ...(apiKey ? { api_key: apiKey.trim() } : {}) };
    void action.run('save', signal => apiSend<StashDBPolicy>('/api/configuration/stashdb/settings', body, 'POST', signal), saved => {
      setPolicy(saved); setApiKey(''); receipt('StashDB settings saved');
    });
  };
  return <Section title="StashDB" onSubmit={save}>
    <Stack>
      <Help>Scene pictures off: match existing actors and studios only, once per identity. Scene searches and cast correction require scene pictures to be enabled.</Help>
      <Help>Library filename matching reads actor and studio names from local filenames. StashDB cast correction uses a matched scene to correct those actor assignments.</Help>
      <Input label="StashDB API key" aria-label="StashDB API key" type="password" autoComplete="new-password"
        placeholder={policy.api_key_set ? 'Key saved; leave blank to keep it' : 'Enter your StashDB API key'} value={apiKey} onChange={setApiKey} />
      <Help><a href="https://guidelines.stashdb.org/docs/faq_getting-started/stashdb/accessing-stashdb/" target="_blank" rel="noreferrer">Get your StashDB API key</a></Help>
    </Stack>
    <Rows>{OPTIONS.map(([key, label]) => <SettingsRow key={key} label={label}>
      <Switch aria-label={label} isSelected={Boolean(policy[key])} isDisabled={readOnly || key === 'correct_cast' && !policy.scene_images}
        onChange={value => setPolicy(previous => ({ ...previous, [key]: value }))} />
    </SettingsRow>)}</Rows>
    <Stack>
      <Help>New-media-only starts when enabled. Existing videos stay available for manual matching. Turn it off to include older videos.</Help>
      <Help>Skipping failed searches lasts until matching hints or search options change. Manual preview always searches again.</Help>
      <label className="flex flex-col gap-2 text-body-2-medium"><span>Ignore filename text when matching</span>
        <textarea rows={3} maxLength={2000} value={policy.ignore_terms || ''} disabled={readOnly}
          className="w-full rounded-xl bg-background-tertiary-default p-3 text-body-regular text-text-primary"
          onChange={event => setPolicy(previous => ({ ...previous, ignore_terms: event.target.value }))} /></label>
      <Help>One literal character, word or phrase per line. Matching ignores case. Your filenames stay unchanged.</Help>
      <Input label="Minimum automatic match confidence (%)" type="number"
        value={String(policy.minimum_confidence ?? 85)} isDisabled={readOnly}
        onChange={value => setPolicy(previous => ({ ...previous, minimum_confidence: Number(value) }))} />
      <Help>Choose 50–100%. Default: 85%. Unique matches and agreement between scene details are still required.</Help>
    </Stack>
    <Stack><Help>Cast corrections replace filename and previous StashDB assignments. Manual assignments remain.</Help>
      <Help>Automatic matching fills missing pictures. Review a match to replace pictures yourself.</Help>
      {readOnly ? <Help>This library is read-only.</Help> : null}
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}
      {account !== null ? <p role="status"><span>StashDB connection successful.</span> <span data-i18n-ignore="">{account}</span></p> : null}
    </Stack>
    <Footer>
      <Button type="submit" {...busyProps(action.busy === 'save')}>Save StashDB settings</Button>
      <Button type="button" variant="secondary" disabled={!policy.api_key_set} {...busyProps(action.busy === 'check')}
        onClick={() => void action.run('check', signal => apiSend<{ ok: boolean; account: string }>('/api/configuration/stashdb/check', {}, 'POST', signal),
          result => { if (!result.ok) throw new Error('StashDB account access is unavailable.'); setAccount(result.account || ''); receipt('StashDB connection successful.'); })}>Test connection</Button>
      <Button type="button" variant="secondary" disabled={!policy.api_key_set} {...busyProps(action.busy === 'remove')}
        onClick={() => void action.run('remove', signal => apiSend<StashDBPolicy>('/api/configuration/stashdb/settings',
          { api_key: '', enabled: false }, 'POST', signal), saved => { setPolicy(saved); setAccount(null); receipt('StashDB key removed'); })}>Remove API key</Button>
    </Footer>
    <Stack divided>
      <Help>Save your settings, then start a metadata scan. Open Manual review for uncertain matches.</Help>
      <div><Button type="button" variant="secondary" disabled={!policy.api_key_set || !policy.enabled || readOnly}
        {...busyProps(action.busy === 'scan')} onClick={() => void action.run('scan',
          signal => apiSend(LIBRARY_PROCESSING_URL, { stage: 'metadata' }, 'POST', signal),
          () => receipt('Metadata scan started. Follow its progress in Data management.'))}>Run metadata scan with StashDB</Button></div>
      <a href="/review?category=stashdb" className="underline">Review StashDB matches</a>
    </Stack>
  </Section>;
}
