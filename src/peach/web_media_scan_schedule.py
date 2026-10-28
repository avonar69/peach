"""到期媒体目录的统一处理任务入口。"""
from . import media_scan_schedule, settings_file
from .web_library_processing import ACTIVE, _current, w_library_processing


def check_due(contract, *, now=None):
    due = media_scan_schedule.due_roots(settings_file.active(), now=now)
    if not due or _current(contract).get('status') in ACTIVE:
        return {'checked': 0, 'added': 0}
    result = w_library_processing(contract, {'stage': 'find_new', 'scan_roots': due})
    return {'checked': len(due), 'added': 0, 'job_id': result.get('job_id')}
