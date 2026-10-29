/* 原生全屏、iOS 视频全屏与窗口填充共用显式按钮。 */
export function fullscreenControl(root: HTMLElement, video: HTMLVideoElement, changed: () => void): () => void {
  const button = root.querySelector<HTMLButtonElement>('.vjs-fullscreen-control');
  const nativeVideo = video as HTMLVideoElement & { webkitEnterFullscreen?: () => void };
  const leaveWindow = () => { root.removeAttribute('data-peach-full-window'); root.classList.remove('vjs-fullscreen'); changed() };
  const click = async () => {
    if (root.hasAttribute('data-peach-full-window')) { leaveWindow(); return; }
    if (document.fullscreenElement) { await document.exitFullscreen(); return; }
    try {
      if (root.requestFullscreen && document.fullscreenEnabled !== false) { await root.requestFullscreen(); return; }
      if (nativeVideo.webkitEnterFullscreen) { nativeVideo.webkitEnterFullscreen(); return; }
    } catch { /* 浏览器拒绝时仍提供窗口填充。 */ }
    root.setAttribute('data-peach-full-window', ''); root.classList.add('vjs-fullscreen'); changed();
  };
  const pressed = () => { void click() };
  const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') leaveWindow() };
  button?.addEventListener('click', pressed);
  document.addEventListener('keydown', escape);
  video.addEventListener('webkitbeginfullscreen', changed);
  video.addEventListener('webkitendfullscreen', changed);
  return () => {
    button?.removeEventListener('click', pressed); document.removeEventListener('keydown', escape);
    video.removeEventListener('webkitbeginfullscreen', changed); video.removeEventListener('webkitendfullscreen', changed);
  };
}
