import { useState } from 'react';
import { Button } from '@/components/base/buttons/button';
import { seekConfig, SEEK_ACTIONS, SEEK_DEFAULTS, shortcutFromEvent, validShortcut } from '../../player/playback-preferences';
import type { PanelSettings } from './settings-panel-api';

const labels = { bigForward: 'Big fast forward', smallForward: 'Small fast forward', bigRewind: 'Big rewind', smallRewind: 'Small rewind' };
export function PlaybackSeekSettings({ settings, save }: { settings: PanelSettings; save(): void }) {
  const [config, setConfig] = useState(() => seekConfig(settings.playerSeek, settings.seekSeconds));
  const [error, setError] = useState('');
  const update = (next: typeof config) => { setConfig(next); settings.playerSeek = next; save(); setError(''); };
  return <div data-seek-settings="" className="flex flex-col gap-4">
    {SEEK_ACTIONS.map(action => <div key={action} className="flex flex-wrap items-center justify-between gap-2" data-seek-action={action}>
      <label htmlFor={`seek-${action}`}>{labels[action]}</label>
      <div className="flex flex-wrap items-center gap-2">
        <input key={`${action}:${config[action].seconds}`} id={`seek-${action}`} type="number" min="1" max="3600" step="1" aria-label={`${labels[action]} seconds`}
          onKeyDown={event => { if (event.key === 'Enter') event.currentTarget.blur(); }}
          className="w-20" defaultValue={config[action].seconds} onBlur={event => {
            const seconds = Number(event.currentTarget.value);
            if (!Number.isInteger(seconds) || seconds < 1 || seconds > 3600) { setError('Enter between 1 and 3600 seconds.'); return; }
            update({ ...config, [action]: { ...config[action], seconds } });
          }} />
        <span>seconds</span>
        <input aria-label={`${labels[action]} shortcut`} className="w-36" readOnly value={config[action].shortcut}
          onKeyDown={event => {
            if (event.key === 'Tab') return;
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); event.currentTarget.blur(); setError(''); return; }
            if (['Control', 'Alt', 'Shift', 'Meta'].includes(event.key)) return;
            event.preventDefault(); event.stopPropagation();
            const shortcut = shortcutFromEvent(event);
            if (!validShortcut(shortcut)) { setError('Choose an arrow, letter, number, or function key. Playback and browser shortcuts are reserved.'); return; }
            if (SEEK_ACTIONS.some(other => other !== action && config[other].shortcut === shortcut)) { setError('This shortcut is already assigned.'); return; }
            update({ ...config, [action]: { ...config[action], shortcut } });
          }} />
      </div>
    </div>)}
    <Button type="button" variant="secondary" onClick={() => {
      const next = seekConfig(config);
      for (const action of SEEK_ACTIONS) next[action].shortcut = SEEK_DEFAULTS[action].shortcut;
      update(next);
    }}>Reset seek shortcuts</Button>
    {error ? <p role="alert">{error}</p> : null}
  </div>;
}
