import { Button, Menu, MenuItem, MenuTrigger, Popover } from 'react-aria-components';
import { buttonStyles } from '@/components/base/buttons/button';
import { MENU_ITEM, MENU_ITEM_ACTIVE, MENU_ITEMS_CONTAINER, MENU_POPOVER_SURFACE } from '@/components/base/dropdown/menu-styles';
import { ACTOR_GENDERS } from '../../actor-genders';
import { spriteGlyph } from '../components/sprite-glyph';

const GenderIcon = spriteGlyph('user-round');
const CheckIcon = spriteGlyph('check');
const ChevronIcon = spriteGlyph('chevron-down');
export function ActorGenderFilter({ value, onChange }: { value: string; onChange(keys: Iterable<string>): void }) {
  const selected = value === 'all' ? ACTOR_GENDERS.map(([key]) => key) : value.split(',');
  return <MenuTrigger>
    <Button aria-label="Actor genders" className={`${buttonStyles.base} ${buttonStyles.size.medium} ${buttonStyles.variant.secondary}`}>
      <GenderIcon className="size-4" /><span className={buttonStyles.label.medium}>Actor genders</span><ChevronIcon className="size-4" />
    </Button>
    <Popover placement="bottom start" offset={8} containerPadding={8} className={MENU_POPOVER_SURFACE}>
      <Menu aria-label="Actor genders" selectionMode="multiple" selectedKeys={selected}
        onSelectionChange={keys => onChange(keys === 'all' ? ACTOR_GENDERS.map(([key]) => key) : [...keys].map(String))}
        className={MENU_ITEMS_CONTAINER}>
        {ACTOR_GENDERS.map(([key, label]) => <MenuItem key={key} id={key} textValue={label}
          className={({ isSelected }) => `${MENU_ITEM} ${isSelected ? MENU_ITEM_ACTIVE : ''}`}>
          {({ isSelected }) => <><span className="size-4">{isSelected ? <CheckIcon className="size-4" /> : null}</span>{label}</>}
        </MenuItem>)}
      </Menu>
    </Popover>
  </MenuTrigger>;
}
