import { useState } from 'react';
import { SettingsRow } from '@/components/application/settings/settings-rows';
import { Switch } from '@/components/base/switch/switch';
import { apiSend } from '../../api';
import { ErrorText, Help, Rows, Section, Stack } from './section';
import { useAction } from './use-action';

export interface FilenameMatchingPolicy { actors: boolean; studios: boolean }
export function FilenameMatchingSettings({ initial, receipt }: {
  initial: FilenameMatchingPolicy; receipt(message: string): void;
}) {
  const [policy, setPolicy] = useState(initial);
  const action = useAction();
  const change = (key: keyof FilenameMatchingPolicy, value: boolean) => void action.run('save', signal =>
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
    <Stack divided><Help>设置用于后续扫描和推送入库。关闭后保留已有归属；重新扫描可处理现有文件。</Help>
      {action.error ? <ErrorText>{action.error}</ErrorText> : null}</Stack>
  </Section>;
}
