/* 演员资料使用来源快照与手工覆盖，编辑后刷新同一份实体查询。 */
import { useState } from 'react';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { apiSend } from '../../api';
import { ModalFrame } from '../components/modal-frame';
import { useAction, busyProps } from '../settings/use-action';
import type { FactRow } from './entity-hero';
import { translate } from '../../i18n';

export const ACTOR_FIELDS = [
  ['career_start_year', 'Career start year'], ['career_end_year', 'Career end year'],
  ['birth_date', 'Birthdate'], ['height', 'Height (cm)'], ['measurements', 'Measurements'],
  ['breast_type', 'Breast type'], ['nationality', 'Nationality'], ['ethnicity', 'Ethnicity'],
  ['eye_color', 'Eye color'], ['hair_color', 'Hair color'],
] as const;
type Field = typeof ACTOR_FIELDS[number][0];
export type ActorDetails = Partial<Record<Field, string | number>> & { age?: number; edited_fields?: string[] };

export function actorFactRows(details: ActorDetails): FactRow[] {
  const values = ACTOR_FIELDS.filter(([key]) => !key.startsWith('career_')).map(([key, label]) => {
    let text = String(details[key] || '');
    if (key === 'birth_date' && text && details.age !== undefined) text += ` (${translate('{0} years old').replace('{0}', String(details.age))})`;
    if (['breast_type', 'ethnicity', 'eye_color', 'hair_color'].includes(key)) text = translate(text.toLowerCase().replaceAll('_', ' '));
    const glyph = key === 'birth_date' ? 'cake' : key === 'nationality' || key === 'ethnicity' ? 'globe'
      : key === 'eye_color' ? 'eye' : key === 'height' || key === 'measurements' ? 'ruler' : 'user-round';
    return { glyph, label, parts: [{ text: text || '—', tone: 'plain' as const }] };
  });
  const start = details.career_start_year, end = details.career_end_year;
  return [{ glyph: 'calendar-range', label: 'Career', parts: [{
    text: start || end ? `${translate(end ? 'Retired' : 'Active')} (${start || '—'} – ${end || translate('Present')})` : '—', tone: 'plain' as const }] }, ...values];
}

export function ActorDetailsEditor({ entityId, details, onSaved, receipt }: {
  entityId: number; details: ActorDetails; onSaved(): void; receipt(message: string): void;
}) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<ActorDetails>({});
  const action = useAction();
  const save = (reset = false) => {
    const changed = Object.fromEntries(ACTOR_FIELDS.filter(([key]) => reset || String(values[key] || '') !== String(details[key] || ''))
      .map(([key]) => [key, reset ? null : String(values[key] || '')]));
    void action.run('save', signal => apiSend('/api/actor-details', { entity_id: entityId, values: changed }, 'POST', signal), () => {
      setOpen(false); onSaved(); receipt('Actor details saved.');
    });
  };
  return <>
    <Button type="button" variant="secondary" onClick={() => { setValues(details); action.setError(''); setOpen(true); }}>Edit actor info</Button>
    <ModalFrame isOpen={open} onOpenChange={setOpen} width="form" label="Edit actor info">
      <form className="flex min-w-0 flex-col gap-4 p-5" onSubmit={event => { event.preventDefault(); save(); }}>
        <h2 className="text-title-2-medium">Edit actor info</h2>
        {ACTOR_FIELDS.map(([key, label]) => <Input key={key} label={label}
          type={key === 'birth_date' ? 'date' : key === 'height' || key.startsWith('career_') ? 'number' : 'text'}
          value={String(values[key] || '')} onChange={value => setValues(previous => ({ ...previous, [key]: value }))} />)}
        {action.error ? <p role="alert">{action.error}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => save(true)} {...busyProps(action.busy === 'save')}>Use synced info</Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" {...busyProps(action.busy === 'save')}>Save actor info</Button>
        </div>
      </form>
    </ModalFrame>
  </>;
}
