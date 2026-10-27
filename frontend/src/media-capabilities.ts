/** 仅在客户端报告支持 8/10-bit AV1 MP4 时请求原片；实际失败仍可回退。 */
export function nativeAv1Supported(): boolean {
  const video = document.createElement('video');
  return ['av01.0.08M.08', 'av01.0.08M.10'].every(codec => !!video.canPlayType(`video/mp4; codecs="${codec}"`));
}
