"""下载到已配置目录，使用独立临时文件与带验证器的 Range 续传。"""
import os
import re
from pathlib import Path

import httpx

from .jobs import DiskGuard, require_free_space
from .public_download_http import stream


def filename(value, identity):
    leaf = str(value).replace('\\', '/').rsplit('/', 1)[-1]
    leaf = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', leaf).strip(' .')[:180] or 'download.bin'
    path = Path(leaf)
    return f'{path.stem[:140]}-{identity[:8]}{path.suffix[:16]}'


def transfer(task, *, update, active, client=None):
    if not re.fullmatch(r'[0-9a-f]{32}', task['id']):
        raise ValueError('Choose a valid download task.')
    root = Path(task['folder']).resolve()
    if not root.is_dir():
        raise ValueError('The download folder is unavailable. Check the Docker volume mount.')
    part = root / f".peach-{task['id']}.part"
    target = root / filename(task['filename'], task['id'])
    if part.is_symlink() or target.exists() or target.is_symlink():
        raise ValueError('The destination already exists or is a symbolic link.')
    offset = part.stat().st_size if part.exists() else 0
    headers = {'Accept-Encoding': 'identity'}
    if offset and task.get('etag'):
        headers.update(Range=f'bytes={offset}-', **{'If-Range': task['etag']})
    else:
        offset = 0
    require_free_space(root, 0.1)
    guard = DiskGuard(root, 0.1)
    owned = client is None
    client = client or httpx.Client()
    try:
        with stream(client, task['url'], headers=headers) as response:
            if response.status_code not in (200, 206):
                raise ValueError(f'Download failed (HTTP {response.status_code}). Regenerate the link if it expired.')
            resume, done, total, etag = _response_state(response, offset, task)
            update(bytes=done, total=total, etag=etag)
            with part.open('ab' if resume else 'wb') as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    if not active():
                        raise InterruptedError('Download cancelled.')
                    guard.check()
                    output.write(chunk)
                    done += len(chunk)
                    update(bytes=done, total=total, etag=etag)
            if total and done != total:
                raise ValueError('The download ended before the complete file arrived.')
            if task.get('size') and done != task['size']:
                raise ValueError('The downloaded size does not match the provider file size.')
            if not active():
                raise InterruptedError('Download cancelled.')
            # 硬链接以排他方式发布已完成文件；原名文件不被覆盖。
            _publish(part, target, active)
            update(status='complete', path=str(target), bytes=done, total=done)
    finally:
        if owned:
            client.close()


def _publish(part, target, active):
    try:
        os.link(part, target)
    except FileExistsError:
        raise ValueError('The destination file already exists.') from None
    except OSError:
        # 一些容器挂载不支持硬链接，排他创建目标后逐块复制。
        output = target.open('xb')
        guard = DiskGuard(target.parent, 0.1)
        try:
            with output, part.open('rb') as source:
                while chunk := source.read(1024 * 1024):
                    if not active():
                        raise InterruptedError('Download cancelled.')
                    guard.check()
                    output.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    part.unlink()


def _response_state(response, offset, task):
    resume = response.status_code == 206 and offset > 0
    if response.status_code == 206 and not resume:
        raise ValueError('The server returned an unexpected partial download.')
    content_range = response.headers.get('content-range', '')
    if resume and not content_range.startswith(f'bytes {offset}-'):
        raise ValueError('The server returned an invalid download range.')
    done = offset if resume else 0
    total = done + int(response.headers.get('content-length') or 0)
    if resume and re.fullmatch(r'bytes \d+-\d+/\d+', content_range):
        total = int(content_range.rsplit('/', 1)[1])
    etag = response.headers.get('etag') or ''
    if resume and etag and etag != task['etag']:
        raise ValueError('The source file changed during the download. Try again.')
    return resume, done, total, etag
