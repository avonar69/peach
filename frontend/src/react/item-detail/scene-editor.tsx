/* 场景编辑独立读取原始资料及 revision，展示标题不反写原始字段。 */
import { useRef, useState } from 'react';
import { UNSAFE_PortalProvider } from 'react-aria';
import { RiEditLine } from '@remixicon/react';
import { Button } from '@/components/base/buttons/button';
import { Input } from '@/components/base/input/input';
import { apiGet, apiSend } from '../../api';
import { translate } from '../../i18n';
import { ModalFrame } from '../components/modal-frame';
import { overlayHost } from '../components/overlay-host';
import { Note } from '../components/note';
import { useAction, busyProps } from '../settings/use-action';
import type { DetailItem } from './item-detail';

const FIELDS = [['catalog_title', '标题'], ['original_title', '原标题'], ['code', '番号'],
  ['release_date', '发行日期'], ['studio', '厂牌'], ['series', '系列']] as const;
type Scene = Partial<Record<typeof FIELDS[number][0], string | null>> & { mutation_revision: number; performers: string[] };

async function encoded(file: File | undefined): Promise<string | undefined> {
  if (!file) return undefined;
  if (file.size > 6_000_000) throw new Error(translate('Image must be no larger than 6 MB.'));
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(translate('Could not read image.')));
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.readAsDataURL(file);
  });
}

export function SceneEditor({ id, onSaved, receipt }: { id: number; onSaved(item: DetailItem): void; receipt(message: string): void }) {
  const [open, setOpen] = useState(false);
  const [original, setOriginal] = useState<Scene | null>(null);
  const [values, setValues] = useState<Scene | null>(null);
  const [actors, setActors] = useState('');
  const [cover, setCover] = useState<File>();
  const [thumbnail, setThumbnail] = useState<File>();
  const action = useAction();
  const anchor = useRef<HTMLButtonElement>(null);
  const edit = () => {
    setOriginal(null); setValues(null); setCover(undefined); setThumbnail(undefined); setOpen(true);
    void action.run('load', signal => apiGet<Scene>(`/api/scene-metadata?id=${id}`, signal), scene => {
      setOriginal(scene); setValues(scene); setActors(scene.performers.join('\n'));
    });
  };
  const save = () => {
    if (!values || !original) return;
    void action.run('save', async signal => {
      const names = [...new Set(actors.split(/[\n,;]/).map(name => name.trim()).filter(Boolean))];
      return apiSend<{ item: DetailItem }>('/api/scene-metadata', {
        id, expected_revision: original.mutation_revision,
        values: Object.fromEntries(FIELDS.filter(([key]) => (values[key] || '') !== (original[key] || '')).map(([key]) => [key, values[key] || ''])),
        ...(JSON.stringify(names) !== JSON.stringify(original.performers) ? { performers: names } : {}),
        cover: await encoded(cover), thumbnail: await encoded(thumbnail),
      }, 'POST', signal);
    }, result => { onSaved(result.item); setOpen(false); receipt('Scene details saved.'); });
  };
  return <>
    <Button ref={anchor} type="button" size="small" variant="secondary" iconOnly leadingIcon={RiEditLine}
      aria-label="Edit scene" title={translate('Edit scene')} onClick={edit} />
    <UNSAFE_PortalProvider getContainer={() => overlayHost(anchor.current)}>
    <ModalFrame isOpen={open} onOpenChange={setOpen} width="form" label="Edit scene">
      <form className="flex min-w-0 flex-col gap-4 p-5" onSubmit={event => { event.preventDefault(); save(); }}>
        <h2 className="text-title-2-medium">Edit scene</h2>
        {values ? <>
          {FIELDS.map(([key, label]) => <Input key={key} label={label} type={key === 'release_date' ? 'date' : 'text'}
            value={values[key] || ''} onChange={value => setValues(previous => previous ? { ...previous, [key]: value } : previous)} />)}
          <label className="flex min-w-0 flex-col gap-2"><span>Actors, one per line</span>
            <textarea aria-label="Actors, one per line" rows={5} className="min-w-0 rounded-lg border border-separator-border p-3"
              value={actors} onChange={event => setActors(event.target.value)} /></label>
          <label className="flex min-w-0 flex-col gap-2"><span>Cover image</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Cover image" className="min-w-0 max-w-full"
              onChange={event => setCover(event.target.files?.[0])} /></label>
          <label className="flex min-w-0 flex-col gap-2"><span>Thumbnail image</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Thumbnail image" className="min-w-0 max-w-full"
              onChange={event => setThumbnail(event.target.files?.[0])} /></label>
        </> : action.error ? null : <p role="status">Loading scene details…</p>}
        {action.error ? <Note tone="error">{action.error}</Note> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
          <Button type="submit" disabled={!values} {...busyProps(action.busy === 'save')}>Save scene</Button>
        </div>
      </form>
    </ModalFrame>
    </UNSAFE_PortalProvider>
  </>;
}
