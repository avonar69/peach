/* 单条作品或实体复用配置来源及其身份保护。 */
import { RiRefreshLine } from '@remixicon/react';
import { useRef } from 'react';
import { UNSAFE_PortalProvider } from 'react-aria';
import { Button } from '@/components/base/buttons/button';
import { apiSend } from '../../api';
import { translate } from '../../i18n';
import { useAction, busyProps } from '../settings/use-action';
import { ModalFrame } from './modal-frame';
import { Note } from './note';
import { overlayHost } from './overlay-host';

export function MetadataRematch({ kind, id, onSaved, receipt }: {
  kind: 'scene' | 'performer' | 'studio'; id: number; onSaved(): void; receipt(message: string): void;
}) {
  const action = useAction();
  const anchor = useRef<HTMLButtonElement>(null);
  return <>
    <Button ref={anchor} type="button" size="small" variant="secondary" iconOnly leadingIcon={RiRefreshLine}
      aria-label="Rematch metadata" title={translate('Rematch metadata')} {...busyProps(action.busy === 'rematch')}
      onClick={() => void action.run('rematch', signal => apiSend('/api/rematch-metadata', { kind, id }, 'POST', signal), () => {
        onSaved(); receipt(kind === 'scene' ? 'Scene rematching started.' : 'Metadata synced.');
      })} />
    <UNSAFE_PortalProvider getContainer={() => overlayHost(anchor.current)}>
    <ModalFrame isOpen={Boolean(action.error)} onOpenChange={open => { if (!open) action.setError(''); }} width="form" label="Rematch metadata">
      <div className="flex flex-col gap-4 p-5">
        <h2 className="text-title-2-medium">Rematch metadata</h2>
        <Note tone="error">{action.error}</Note>
        <Button type="button" variant="secondary" onClick={() => action.setError('')}>Close</Button>
      </div>
    </ModalFrame>
    </UNSAFE_PortalProvider>
  </>;
}
