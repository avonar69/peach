import { useEffect, type ReactNode, type Ref } from 'react';
import { RiArrowDownSLine, RiArrowUpSLine } from '@remixicon/react';
import { Button } from '@/components/base/buttons/button';
import { cx } from '@/utils/cx';

/** 常驻后台任务共用标题、折叠、状态色与操作区。 */
export function TaskPopup({ panelRef, label, title, subtitle, icon, tone = 'neutral', expanded, toggle, children, footer, measure = false }: {
  panelRef?: Ref<HTMLElement>; label: string; title: ReactNode; subtitle?: ReactNode; icon: ReactNode;
  tone?: 'neutral' | 'warning' | 'error'; expanded: boolean; toggle(): void; children: ReactNode; footer: ReactNode;
  measure?: boolean;
}) {
  useEffect(() => {
    if (!measure) return;
    const update = () => {
      const panels = [...document.querySelectorAll<HTMLElement>('#toasts [data-processing-dock]')];
      if (panels.length) document.documentElement.style.setProperty('--processing-toast-space',
        `${panels.reduce((height, panel) => height + panel.getBoundingClientRect().height + 8, 4)}px`);
      else document.documentElement.style.removeProperty('--processing-toast-space');
    };
    const observer = new ResizeObserver(update);
    for (const panel of document.querySelectorAll('#toasts [data-processing-dock]')) observer.observe(panel);
    update();
    return () => { observer.disconnect(); queueMicrotask(update) };
  }, [measure]);
  return <aside ref={panelRef} data-processing-dock="" data-processing-tone={tone} aria-label={label}
    role={tone === 'error' ? 'alert' : 'status'}
    className={cx('flex min-w-0 flex-col gap-3 border bg-background-primary-default p-4',
      tone === 'error' ? 'border-current/35 text-text-error-primary'
        : tone === 'warning' ? 'border-current/35 text-status-yellow-text' : 'border-border-button-default text-text-primary')}>
    <div className="flex min-w-0 items-center gap-3">
      {icon}
      <div className="min-w-0 flex-1">
        <p className="text-body-medium">{title}</p>{subtitle}
      </div>
      <Button size="small" variant="secondary" iconOnly leadingIcon={expanded ? RiArrowDownSLine : RiArrowUpSLine}
        aria-label={expanded ? '收起任务详情' : '展开任务详情'} aria-expanded={expanded} onClick={toggle} />
    </div>
    {expanded ? <div className={cx('flex min-w-0 flex-col gap-2 border-t pt-3',
      tone === 'error' ? 'border-border-error-default/20' : tone === 'warning' ? 'border-current/20' : 'border-separator-border')}>
      {children}
    </div> : null}
    <div className="flex flex-wrap items-center justify-between gap-2">{footer}</div>
  </aside>;
}
