"""可恢复的链接准备与目录下载队列；任务状态保存在本机 state。"""
import hashlib
import json
import threading
import time
from pathlib import Path

from . import debrid_client, debrid_transfer
from .fsutil import atomic_write_text

ACTIVE = ('queued', 'preparing', 'downloading')


class Service:
    def __init__(self, config, *, available=True, after_download=None):
        self.config, self.available = config, available
        self.after_download = after_download
        self.path = config.directory('state') / 'debrid-jobs.json'
        self.lock, self.event, self.stopped = threading.RLock(), threading.Event(), threading.Event()
        self.thread = None
        self.workers = {}
        self.last_saved = 0
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            self.jobs = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.jobs = {}
        for task in self.jobs.values():
            if task.get('status') in ACTIVE:
                task.update(status='queued', next_poll=0)
            if task.get('import_state') in ('running', 'queuing'):
                task.update(import_state='pending', import_next_attempt=0)

    def _save(self):
        atomic_write_text(self.path, json.dumps(self.jobs))

    def _update(self, identity, **values):
        with self.lock:
            job = self.jobs[identity]
            if job.get('status') == 'cancelled':
                if 'remote_id' in values:
                    job['remote_id'] = values['remote_id']
                    self._save()
                raise InterruptedError('Download cancelled.')
            job.update(values, updated_at=time.time())
            if 'bytes' not in values or 'status' in values or time.monotonic() - self.last_saved >= 1:
                self._save()
                self.last_saved = time.monotonic()

    def active(self, identity):
        with self.lock:
            return not self.stopped.is_set() and self.jobs[identity]['status'] != 'cancelled'

    def job(self, identity):
        with self.lock:
            return dict(self.jobs.get(identity, {}))

    def import_progress(self, identity, **values):
        with self.lock:
            self.jobs[identity].update(values, updated_at=time.time())
            self._save()

    def import_active(self, identity):
        return self.active(identity) and not self.job(identity).get('import_cancelled')

    def snapshot(self):
        stamps = {key: debrid_client.key_stamp(self.config, key) for key in debrid_client.PROVIDERS}
        with self.lock:
            rows = [{key: value for key, value in job.items() if key not in ('key_stamp', 'remote_id')}
                for job in self.jobs.values() if job.get('key_stamp') == stamps.get(job['provider'])]
            indexed = {row['id']: row for row in rows}
            for parent in rows:
                if parent.get('kind') != 'resolve':
                    continue
                files = [dict(file) for file in parent.get('files', [])]
                parent['files'] = files
                for index, file in enumerate(files):
                    identity = hashlib.sha256(f"{parent['id']}:{index}:download".encode()).hexdigest()[:32]
                    if identity in indexed:
                        file['download_id'] = identity
                        indexed[identity].update(parent_id=parent['id'], file_index=index)
            return rows

    def submit(self, entry_id, link, provider, *, auto_download=False):
        if not self.available:
            raise ValueError('This library is read-only.')
        if not debrid_client.saved(self.config).get(provider, {}).get('api_key'):
            raise ValueError('Save the debrid API key in Download providers first.')
        identity = hashlib.sha256(f"{entry_id}:{provider}:{link['url']}".encode()).hexdigest()[:32]
        stamp = debrid_client.key_stamp(self.config, provider)
        with self.lock:
            old = self.jobs.get(identity, {})
            if old.get('key_stamp') != stamp:
                old = {}
            if old.get('status') in ACTIVE or (old.get('status') == 'ready' and time.time() - old['updated_at'] < 3600):
                if auto_download:
                    old['auto_download'] = True
                    self._save()
                    self.event.set()
                return old
            if len(self.jobs) >= 1000 and not old:
                raise ValueError('The debrid task queue is full.')
            self.jobs[identity] = {**old, 'id': identity, 'entry_id': entry_id, 'provider': provider,
                'source': link, 'kind': 'resolve', 'status': 'queued', 'error': '',
                'auto_download': bool(auto_download), 'delivery_queued': False,
                'files': old.get('files', []) if old.get('status') != 'ready' else [],
                'key_stamp': stamp, 'next_poll': 0, 'updated_at': time.time()}
            self._save()
        self.start()
        self.event.set()
        return self.jobs[identity]

    def download(self, identity, index):
        with self.lock:
            source = self.jobs.get(identity, {})
            if source.get('key_stamp') != debrid_client.key_stamp(self.config, source.get('provider')):
                raise ValueError('Generate a current debrid link first.')
            files = source.get('files', [])
            if type(index) is not int or index < 0 or index >= len(files) or not files[index].get('url'):
                raise ValueError('Choose a ready debrid download link.')
            folder = debrid_client.saved(self.config).get(source['provider'], {}).get('download_folder')
            if not folder:
                raise ValueError('Set a download folder in Download providers first.')
            key = hashlib.sha256(f'{identity}:{index}:download'.encode()).hexdigest()[:32]
            old = self.jobs.get(key, {})
            if old.get('status') in ACTIVE or (old.get('status') == 'complete' and Path(old.get('path', '')).is_file()):
                return old
            self.jobs[key] = {**old, **files[index], 'id': key, 'kind': 'download', 'folder': folder,
                'parent_id': identity, 'file_index': index,
                'dismissed': False,
                'auto_import': debrid_client.saved(self.config).get(source['provider'], {}).get('auto_import') is True,
                'import_state': '', 'import_error': '', 'import_cancelled': False, 'import_next_attempt': 0,
                'entry_id': source['entry_id'], 'provider': source['provider'], 'key_stamp': source['key_stamp'],
                'status': 'queued', 'error': '', 'next_poll': 0, 'updated_at': time.time()}
            self._save()
        self.start()
        self.event.set()
        return self.jobs[key]

    def cancel(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job:
                raise ValueError('Choose an existing debrid task.')
            if job['status'] in ACTIVE:
                job.update(status='cancelled', updated_at=time.time())
                self._save()
            elif job.get('import_state') in ('pending', 'queuing', 'queued', 'running'):
                job.update(import_cancelled=True, import_state='cancelled', updated_at=time.time())
                self._save()
        self.event.set()
        return {'ok': True}

    def clear_finished(self):
        count = 0
        with self.lock:
            for job in self.jobs.values():
                if job.get('kind') != 'download' or job.get('status') not in ('complete', 'failed', 'cancelled'):
                    continue
                if job.get('import_state') in ('pending', 'queuing', 'queued', 'running') or job.get('dismissed'):
                    continue
                job['dismissed'] = True
                count += 1
            self._save()
        return {'ok': True, 'cleared': count}

    def retry_import(self, identity):
        with self.lock:
            job = self.jobs.get(identity)
            if not job or job.get('status') != 'complete' or not job.get('auto_import'):
                raise ValueError('Choose a completed download with automatic import enabled.')
            job.update(import_state='pending', import_error='', import_cancelled=False, import_next_attempt=0)
            self._save()
        self.start()
        self.event.set()
        return {'ok': True}

    def _queue_import(self, task):
        identity = task['id']
        if not self.after_download:
            return
        self.import_progress(identity, import_state='queuing', import_error='')
        try:
            run_id = self.after_download(self.job(identity))
            with self.lock:
                if self.jobs[identity].get('import_state') == 'queuing':
                    self.jobs[identity].update(import_state='queued' if run_id else 'pending',
                        import_run_id=run_id, import_next_attempt=time.time() + 5)
                    self._save()
        except Exception:
            self.import_progress(identity, import_state='failed', import_error='The download completed, but automatic import failed. Retry the import.')

    def start(self):
        with self.lock:
            if not self.available or (self.thread and self.thread.is_alive()):
                return
            self.stopped.clear()
            self.thread = threading.Thread(target=self._loop, name='PeachDebrid', daemon=True)
            self.thread.start()

    def stop(self):
        self.stopped.set()
        self.event.set()
        if self.thread:
            self.thread.join(2)
        with self.lock:
            workers = list(self.workers.values())
        deadline = time.monotonic() + 2
        for worker in workers:
            worker.join(max(0, deadline - time.monotonic()))

    def _work(self, task):
        try:
            self._run(task)
        finally:
            with self.lock:
                self.workers.pop(task['id'], None)
            self.event.set()

    def _dispatch(self):
        settings = debrid_client.saved(self.config)
        with self.lock:
            running = [self.jobs[identity] for identity in self.workers]
            for job in self.jobs.values():
                if job['id'] in self.workers or job['status'] not in ACTIVE or job.get('next_poll', 0) > time.time():
                    continue
                if job['kind'] == 'download':
                    limit = settings.get(job['provider'], {}).get('max_concurrent_downloads', 3)
                    occupied = sum(item['kind'] == 'download' and item['provider'] == job['provider'] for item in running)
                else:
                    if job.get('auto_download') and not self._download_slot_available(job['provider'], settings):
                        continue
                    limit = 1
                    occupied = sum(item['kind'] != 'download' for item in running)
                if occupied >= limit:
                    continue
                task = dict(job)
                worker = threading.Thread(target=self._work, args=(task,), name='PeachDebridTask', daemon=True)
                self.workers[job['id']] = worker
                running.append(task)
                worker.start()

    def _download_slot_available(self, provider, settings):
        limit = settings.get(provider, {}).get('max_concurrent_downloads', 3)
        occupied = sum(job['kind'] == 'download' and job['provider'] == provider
                       and job['status'] in ACTIVE for job in self.jobs.values())
        return occupied < limit

    def _deliver_ready(self):
        with self.lock:
            ready = [dict(job) for job in self.jobs.values() if job.get('kind') == 'resolve'
                     and job.get('status') == 'ready' and job.get('auto_download')
                     and not job.get('delivery_queued') and len(job.get('files', [])) == 1]
        for task in ready:
            try:
                self.download(task['id'], 0)
                self._update(task['id'], delivery_queued=True)
            except (ValueError, InterruptedError):
                self._update(task['id'], auto_download=False)

    def _loop(self):
        while not self.stopped.is_set():
            self._deliver_ready()
            self._dispatch()
            with self.lock:
                pending = next((dict(job) for job in self.jobs.values() if job.get('status') == 'complete'
                    and job.get('auto_import') and job.get('import_state', 'pending') in ('pending', 'queuing')
                    and job.get('import_next_attempt', 0) <= time.time()), None)
            if pending and self.after_download:
                self._queue_import(pending)
            self.event.wait(1)
            self.event.clear()

    def _run(self, task):
        identity = task['id']
        try:
            if task['key_stamp'] != debrid_client.key_stamp(self.config, task['provider']):
                raise ValueError('The provider account changed. Generate a new link.')
            self._update(identity, status='downloading' if task['kind'] == 'download' else 'preparing')
            if task['kind'] == 'download':
                debrid_transfer.transfer(task, update=lambda **values: self._update(identity, **values),
                                         active=lambda: self.active(identity))
                completed = self.job(identity)
                if completed.get('status') == 'complete' and completed.get('auto_import'):
                    self._queue_import(completed)
            else:
                self._resolve(task)
        except InterruptedError:
            pass
        except ValueError as error:
            with self.lock:
                if self.jobs[identity]['status'] != 'cancelled':
                    self.jobs[identity].update(status='failed', error=str(error)[:400], updated_at=time.time())
                    self._save()
        except Exception:
            with self.lock:
                if self.jobs[identity]['status'] != 'cancelled':
                    # 异常文本可能带有签名 URL；任务只保留固定提示。
                    self.jobs[identity].update(status='failed', error='The debrid task failed. Check the provider account, link and download folder.', updated_at=time.time())
                    self._save()

    def _resolve(self, task):
        identity = task['id']
        client = debrid_client.Client(self.config, task['provider'], active=lambda: self.active(identity))
        try:
            if task['source']['kind'] != 'link' and not task.get('remote_id'):
                task['remote_id'] = client.create_torrent(task['source'])
                self._update(identity, remote_id=task['remote_id'])
            hosts = client.torrent_links(task['remote_id']) if task.get('remote_id') else [task['source']['url']]
            if hosts is None:
                self._update(identity, next_poll=time.time() + 60)
                return
            if not hosts or len(hosts) > 100:
                raise ValueError('This torrent contains no downloadable files or exceeds the file limit.')
            with self.lock:
                previous = {row['host_link']: row for row in self.jobs[identity].get('files', [])}
            files = []
            for host in hosts:
                row = dict(previous.get(host, {'host_link': host}))
                result = client.unlock(host, previous=row, persist=lambda values, row=row: row.update(values)) if not row.get('url') else row
                row.update(result or {})
                files.append(row)
                self._update(identity, files=files)
            ready = all(row.get('url') for row in files)
            self._update(identity, status='ready' if ready else 'preparing', files=files, next_poll=time.time() + 60)
        finally:
            client.close()
