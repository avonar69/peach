/* 卡片与紧凑列表共用观看状态及评分。 */
import { RiEyeLine, RiStarFill, RiThumbUpFill } from '@remixicon/react';
import type { MediaItem } from '../catalog-grid/types';
import './media-badges.css';

export function MediaBadges({ item, compact = false }: { item: MediaItem; compact?: boolean }) {
  const rating = Math.min(5, Math.max(0, Number(item.rating) || 0));
  return <>
    {item.feedback === 'seen' || Number(item.play_count) > 0 ? <span data-media-status="watched" title="看过"><RiEyeLine aria-hidden /></span> : null}
    {rating > 0 ? <span data-media-status="rating" title="Rating"><RiStarFill aria-hidden /><b>{rating}</b></span> : null}
    {!compact && item.liked ? <span data-media-status="liked" title="喜欢"><RiThumbUpFill aria-hidden /></span> : null}
  </>;
}
