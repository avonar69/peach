import { useState } from 'react';
import { SettingsRow } from '@/components/application/settings/settings-rows';
import { Switch } from '@/components/base/switch/switch';
import { Button } from '@/components/base/buttons/button';
import { apiSend } from '../../api';
import { ErrorText, Help, Rows, Section, Stack } from './section';
import { busyProps, useAction } from './use-action';
import { LIBRARY_PROCESSING_URL } from '../library-processing/library-processing';

export interface FilenameMatchingPolicy { actors: boolean; studios: boolean; ignore_terms?: string }
export function FilenameMatchingSettings({ initial, receipt }: {
  initial: FilenameMatchingPolicy; receipt(message: string): void;
}) {
  const [policy, setPolicy] = useState(initial);
  const action = useAction();
  const change = (key: 'actors' | 'studios', value: boolean) => void action.run('save', signal =>
    apiSend<FilenameMatchingPolicy>('/api/configuration/filename-matching', { ...policy, [key]: value }, 'POST', signal), saved => {
      setPolicy(saved); receipt('已保存文件名匹配设置');
    });
  return <Section title="文件名自动匹配">
    <Rows>
      <SettingsRow label="自动匹配演员" description="扫描时匹配已知演员；从日期后的姓名或 actors 字段创建演员。">
        <Switch aria-label="自动匹配演员" isSelected={policy.actors} isDisabled={!!action.busy} onChange={value => change('actors', value)} />
      </SettingsRow>
      <SettingsRow label="自动匹配厂牌" description="Match or create studios from the filename prefix before the date.">
        <Switch aria-label="自动匹配厂牌" isSelected={policy.studios} isDisabled={!!action.busy} onChange={value => change('studios', value)} />
      </SettingsRow>
    </Rows>
    <Stack divided>
      <label className="flex flex-col gap-2 text-body-2-medium"><span>Ignore filename text when matching</span>
        <textarea rows={3} maxLength={2000} value={policy.ignore_terms || ''} disabled={!!action.busy}
          className="w-full rounded-xl bg-background-tertiary-default p-3 text-body-regular text-text-primary"
          onChange={event => setPolicy(previous => ({ ...previous, ignore_terms: event.target.value }))} /></label>
      <Help>One literal character, word or phrase per line. Matching ignores case. Your filenames stay unchanged.</Help>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" {...busyProps(action.busy === 'save')} onClick={() => void action.run('save',
          signal => apiSend<FilenameMatchingPolicy>('/api/configuration/filename-matching', policy, 'POST', signal),
          saved => { setPolicy(saved); receipt('已保存文件名匹配设置'); })}>Save filename matching settings</Button>
        <Button type="button" variant="secondary" disabled={!policy.ignore_terms?.trim() || !(policy.actors || policy.studios)}
          {...busyProps(action.busy === 'rematch')} onClick={() => void action.run('rematch', async signal => {
            const saved = await apiSend<FilenameMatchingPolicy>('/api/configuration/filename-matching', policy, 'POST', signal);
            setPolicy(saved);
            const job = await apiSend<{ requested_stage?: string }>(LIBRARY_PROCESSING_URL, { stage: 'filename_ignored' }, 'POST', signal);
            if (job.requested_stage !== 'filename_ignored') throw new Error('A scan is already running. Stop it or wait for it to finish, then start resync.');
            return job;
          }, () => receipt('Filename rematching started. Follow its progress in Data management.'))}>Rematch affected filenames</Button>
      </div>
      <Help>Saves these settings and rematches only filenames containing at least one ignored term. Manual assignments remain.</Help>
    </Stack>
    <Stack divided><Help>设置用于后续扫描和推送入库。关闭后保留已有归属；重新扫描可处理现有文件。</Help>
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}</Stack>
  </Section>;
}
