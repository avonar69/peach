/* 单次快速应用只使用缓存得分，不写入来源偏好。 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { confirmModal } from '@peach/legacy/ui';
import { apiSend } from '../../api';
import { translate } from '../../i18n';
import { CONFIGURATION_KEY, fetchConfiguration } from '../settings/configuration';
import { ErrorText, Help } from '../settings/section';
import { busyProps, useAction } from '../settings/use-action';

const EXPLANATION = 'Uses saved scores without searching again. This threshold applies only to quick matching; regular matching keeps its configured threshold.';

export function StashDBQuick({ readOnly, queued, started }: {
  readOnly: boolean; queued: boolean; started(): void;
}) {
  const configuration = useQuery({ queryKey: CONFIGURATION_KEY, queryFn: ({ signal }) => fetchConfiguration(signal) });
  const [input, setInput] = useState<string | null>(null);
  const [days, setDays] = useState('7');
  const value = input ?? String(configuration.data?.stashdb?.minimum_confidence ?? 85);
  const minimum = Number(value);
  const valid = value.trim() !== '' && Number.isInteger(minimum) && minimum >= 0 && minimum <= 100;
  const action = useAction();
  return <div className="flex min-w-0 flex-col gap-2">
    <Input label="Quick match threshold (%)" type="number" value={value} onChange={setInput} isDisabled={readOnly} />
    <Help>{EXPLANATION}</Help>
    <div><Button type="button" variant="secondary" disabled={readOnly || !queued || !valid || Boolean(action.busy)}
      {...busyProps(action.busy === 'quick')} onClick={() => void confirmModal({
        title: 'Quick StashDB matching', confirmLabel: 'Quick StashDB matching',
        body: `${minimum}% · ${translate(EXPLANATION)}`,
        onConfirm: () => action.run('quick', signal => apiSend('/api/library-processing', {
          stage: 'stashdb_quick', quick_threshold: minimum,
        }, 'POST', signal), started),
      })}>Quick StashDB matching</Button></div>
    {action.error ? <ErrorText>{action.error}</ErrorText> : null}
    <Input label="Recently added videos (days)" type="number" value={days} onChange={setDays} isDisabled={readOnly} />
    <div><Button type="button" variant="secondary" disabled={readOnly || Boolean(action.busy) || !Number.isInteger(Number(days)) || Number(days) < 1 || Number(days) > 36500}
      {...busyProps(action.busy === 'recent')} onClick={() => void action.run('recent', signal => apiSend('/api/library-processing', {
        stage: 'stashdb_recent', recent_days: Number(days),
      }, 'POST', signal), started)}>Match recently added videos with StashDB</Button></div>
  </div>;
}
