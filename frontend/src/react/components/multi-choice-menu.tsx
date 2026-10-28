import { Button, Menu, MenuItem, MenuSection, MenuTrigger, Popover } from 'react-aria-components';
import { buttonStyles } from '@/components/base/buttons/button';
import { MENU_ITEM, MENU_ITEM_ACTIVE, MENU_ITEMS_CONTAINER, MENU_POPOVER_SURFACE } from '@/components/base/dropdown/menu-styles';
import { spriteGlyph } from './sprite-glyph';

const CheckIcon = spriteGlyph('check'), ChevronIcon = spriteGlyph('chevron-down');
export function MultiChoiceMenu({ label, symbol, options, selected, onChange, allLabel, onAll, verbatim = false }: {
  label: string; symbol: string; options: { id: string; label: string }[]; selected: string[];
  onChange(keys: Iterable<string>): void; allLabel?: string; onAll?(): void; verbatim?: boolean;
}) {
  const Icon = spriteGlyph(symbol);
  return <MenuTrigger>
    <Button aria-label={label} className={`${buttonStyles.base} ${buttonStyles.size.medium} ${buttonStyles.variant.secondary}`}>
      <Icon className="size-4" /><span className={buttonStyles.label.medium}>{label}</span><ChevronIcon className="size-4" />
    </Button>
    <Popover placement="bottom start" offset={8} containerPadding={8} className={MENU_POPOVER_SURFACE}>
      <Menu aria-label={label} className={MENU_ITEMS_CONTAINER}>
        {allLabel && onAll ? <MenuSection><MenuItem id="all-options" textValue={allLabel} onAction={onAll} className={MENU_ITEM}>{allLabel}</MenuItem></MenuSection> : null}
        <MenuSection selectionMode="multiple" selectedKeys={selected}
          onSelectionChange={keys => onChange(keys === 'all' ? options.map(item => item.id) : [...keys].map(String))}>
          {options.map(item => <MenuItem key={item.id} id={item.id} textValue={item.label}
            className={({ isSelected }) => `${MENU_ITEM} ${isSelected ? MENU_ITEM_ACTIVE : ''}`}>
            {({ isSelected }) => <><span className="size-4">{isSelected ? <CheckIcon className="size-4" /> : null}</span>
              <span data-i18n-ignore={verbatim ? '' : undefined}>{item.label}</span></>}
          </MenuItem>)}
        </MenuSection>
      </Menu>
    </Popover>
  </MenuTrigger>;
}
