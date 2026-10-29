/* Peach 配置中的采集档位与来源更新偏好，读写复用设置接口和查询缓存。 */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';

import { appSettingsStore } from '@peach/appearance';
import { SettingsRow } from '@/components/application/settings/settings-rows';
import { Select, SelectItem } from '@/components/base/select/select';
import { Switch } from '@/components/base/switch/switch';
import { Input } from '@/components/base/input/input';
import { Button } from '@/components/base/buttons/button';
import { confirmModal } from '@peach/legacy/ui';

import { FOLLOW_INITIAL_RANGE_OPTIONS } from '../../application/initial-follow-ranges';
import { apiSend, errorMessage } from '../../api';
import { queryClient } from '../query';
import { useAction } from './use-action';
import { boundedPreference } from '../../number-setting';
import {
  FOLLOW_SCHEDULE_KEY, SETTINGS_KEY, THUMBNAIL_JOBS_KEY, fetchFollowSchedule, fetchSettings, fetchThumbnailJobs,
  useSaveFollowSchedule, useSaveSettings, useSaveThumbnailMode,
} from '../settings-panel/settings-data';
import { ErrorText, Help, Rows, Section, Stack } from './section';

const THUMBNAIL_OPTIONS = [['off', 'Off'], ['precise', '每 10 秒一张'], ['coarse', '每 30 秒一张'], ['custom', 'Custom interval']] as const;

export function VideoThumbnailRow({ epoch = 0 }: { epoch?: number }) {
  return <Section title="时间轴缩略图"><VideoThumbnailControls epoch={epoch} /></Section>;
}

export function VideoThumbnailControls({ epoch = 0, disabled = false }: { epoch?: number; disabled?: boolean }) {
  const status = useQuery({ queryKey: THUMBNAIL_JOBS_KEY, queryFn: ({ signal }) => fetchThumbnailJobs(signal), refetchOnMount: 'always' });
  const save = useSaveThumbnailMode();
  const acceleration = useAction();
  const [custom, setCustom] = useState(false);
  const [interval, setInterval] = useState('10');
  const [regeneration, setRegeneration] = useState('upgrade');
  useEffect(() => { if (status.data?.interval_seconds) setInterval(String(status.data.interval_seconds)) }, [status.data?.interval_seconds]);
  const reset = save.reset;
  useEffect(() => { reset() }, [epoch, reset]);
  const data = status.data;
  const error = save.error || status.error;
  return (
    <>
      <Rows>
        <SettingsRow label="Timeline regeneration scope">
          <div className="min-w-0 flex-1">
          <Select aria-label="Timeline regeneration scope" selectedKey={regeneration} onSelectionChange={key => { if (key !== null) setRegeneration(String(key)) }}>
            <SelectItem id="upgrade">Only missing or more widely spaced thumbnails</SelectItem>
            <SelectItem id="all">Regenerate all timeline thumbnails</SelectItem>
          </Select>
          </div>
        </SettingsRow>
        <SettingsRow label="时间轴预览" description="Off stops generation and keeps existing previews. Smaller intervals create more images.">
          <div id="videoThumbnailSetting">
            <Select aria-label="缩略图采集间隔" selectedKey={custom ? 'custom' : data?.mode || 'off'}
              isDisabled={disabled || !data || status.isFetching || save.isPending}
              onSelectionChange={(key) => { if (key === 'custom') setCustom(true); else if (key !== null) { setCustom(false); save.mutate({ mode: String(key), regeneration }) } }}>
              {THUMBNAIL_OPTIONS.map(([key, label]) => <SelectItem key={key} id={key}>{label}</SelectItem>)}
            </Select>
          </div>
        </SettingsRow>
        {(custom || data?.mode === 'custom') && <SettingsRow label="Interval (seconds)" description="1–3600 seconds">
          <div className="flex flex-wrap items-center gap-2">
            <Input aria-label="Interval (seconds)" type="number" value={interval} onChange={setInterval} isDisabled={disabled || save.isPending} />
            <Button size="small" variant="secondary" disabled={disabled || save.isPending || !Number.isInteger(Number(interval)) || Number(interval) < 1 || Number(interval) > 3600}
              onClick={() => save.mutate({ mode: 'custom', interval_seconds: Number(interval), regeneration })}>Apply interval</Button>
          </div>
        </SettingsRow>}
        <SettingsRow label="Thumbnail acceleration" description="GPU decoding may fall back to CPU. Seeking and disk speed can limit the benefit.">
          <div id="thumbnailAccelerationSetting">
          <Select aria-label="Thumbnail acceleration" selectedKey={data?.acceleration || 'cpu'} isDisabled={disabled || !data || !!acceleration.busy}
            onSelectionChange={key => { if (key !== null) void acceleration.run('save', signal => apiSend('/api/thumbnail-jobs', { action: 'set_acceleration', acceleration: String(key) }, 'POST', signal), saved => queryClient.setQueryData(THUMBNAIL_JOBS_KEY, saved)) }}>
            <SelectItem id="cpu">CPU</SelectItem><SelectItem id="cuda">CUDA (NVIDIA)</SelectItem><SelectItem id="vulkan">Vulkan (experimental)</SelectItem>
          </Select>
          </div>
        </SettingsRow>
      </Rows>
      <Stack divided><div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={disabled || !data || data.mode === 'off' || save.isPending}
          onClick={() => save.mutate({ mode: data?.mode || 'off', interval_seconds: data?.interval_seconds, regeneration })}>Generate timeline thumbnails</Button>
        <Button type="button" variant="secondary" disabled={disabled || !!acceleration.busy} onClick={() => { void confirmModal({ title: 'Delete generated timeline thumbnails', confirmLabel: 'Delete generated timeline thumbnails',
          body: 'Delete all generated timeline thumbnails? Generation will stop. Media files and scene covers will remain.',
          onConfirm: async () => { const saved = await apiSend('/api/thumbnail-jobs', { action: 'delete_all', confirmed: true }); queryClient.setQueryData(THUMBNAIL_JOBS_KEY, saved); } }); }}>Delete generated timeline thumbnails</Button>
      </div></Stack>
      {save.isPending || data?.status === 'running'
        ? <Stack divided><Help role="status">{save.isPending ? '正在保存…' : '正在采集，进度在活动页查看。'}</Help></Stack>
        : null}
      {error ? <Stack divided><ErrorText>{errorMessage(error)}</ErrorText></Stack> : null}
      {acceleration.error && <ErrorText>{acceleration.error}</ErrorText>}
    </>
  );
}

export function FollowPreferenceRows({ receipt }: { receipt(message: string): void }) {
  const store = appSettingsStore();
  useSyncExternalStore(store.subscribe, store.version);
  const settings = useQuery({ queryKey: SETTINGS_KEY, queryFn: ({ signal }) => fetchSettings(signal), refetchOnMount: 'always' });
  const initial = useSaveSettings();
  const initialDays = settings.data?.followInitialDays ?? store.value.followInitialDays;
  const error = initial.error || settings.error;
  return (
    <Section title="关注采集">
      <Rows>
        <FollowScheduleRow />
        <SettingsRow label="首次采集范围">
          <div id="followInitialDaysSetting">
            <Select aria-label="首次采集范围" selectedKey={String(initialDays)}
              isDisabled={settings.isFetching || initial.isPending}
              onSelectionChange={(key) => {
                if (key === null) return;
                initial.mutate({ followInitialDays: Number(key) }, { onSuccess: (saved) => {
                  if (typeof saved.followInitialDays === 'number') store.value.followInitialDays = saved.followInitialDays;
                  store.save();
                  receipt('已保存首次采集范围');
                } });
              }}>
              {FOLLOW_INITIAL_RANGE_OPTIONS.map(([key, label]) => <SelectItem key={key} id={key}>{label}</SelectItem>)}
            </Select>
          </div>
        </SettingsRow>
        <SettingsRow label="头像刷新">每 3 个月</SettingsRow>
        <SettingsRow label="favicon 刷新">每年</SettingsRow>
      </Rows>
      {error ? <Stack divided><ErrorText>{errorMessage(error)}</ErrorText></Stack> : null}
    </Section>
  );
}

function FollowScheduleRow() {
  const status = useQuery({ queryKey: FOLLOW_SCHEDULE_KEY, queryFn: ({ signal }) => fetchFollowSchedule(signal), refetchOnMount: 'always' });
  const save = useSaveFollowSchedule();
  const data = status.data;
  const remembered = useRef(boundedPreference(Number(localStorage.getItem('peach.number.followScheduleSetting')), 15, 10080, 60));
  const [draft, setDraft] = useState('60');
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    if (data?.enabled) {
      remembered.current = data.interval_minutes;
      setDraft(String(data.interval_minutes));
    }
  }, [data]);
  const blocked = !data?.available || status.isFetching || save.isPending;
  const commit = () => {
    const minutes = Number(draft);
    if (!Number.isInteger(minutes) || minutes < 15 || minutes > 10080) { setInvalid(true); return }
    setInvalid(false);
    if (!data?.enabled || blocked || minutes === data.interval_minutes) return;
    remembered.current = minutes;
    localStorage.setItem('peach.number.followScheduleSetting', String(minutes));
    save.mutate(minutes);
  };
  const error = save.error || status.error;
  return (
    <>
      <SettingsRow label="自动检查更新">
        <div id="followScheduleSetting" className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <Switch aria-label="自动检查更新" isSelected={data?.enabled === true} isDisabled={blocked}
            onChange={(on) => {
              localStorage.setItem('peach.number.followScheduleSetting', String(remembered.current));
              save.mutate(on ? remembered.current : 0);
            }} />
          {data?.enabled ? <div className="flex items-center gap-2">
            <Input type="number" inputMode="numeric" name="follow-interval" autoComplete="off"
              aria-label="自动检查间隔" size="small" className="w-24"
              value={draft} onChange={(value) => { setDraft(value); setInvalid(false) }} onBlur={commit}
              onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); commit() } }}
              isDisabled={blocked} isInvalid={invalid} />
            <span className="text-body-2-regular text-text-secondary">分钟</span>
          </div> : null}
        </div>
      </SettingsRow>
      {invalid ? <Stack><ErrorText>请输入 15–10080 的整数（分钟）。</ErrorText></Stack> : null}
      {save.isPending || data?.running
        ? <Stack><Help role="status">{save.isPending ? '正在保存…' : '正在检查来源更新…'}</Help></Stack> : null}
      {error ? <Stack><ErrorText>{errorMessage(error)}</ErrorText></Stack> : null}
    </>
  );
}
