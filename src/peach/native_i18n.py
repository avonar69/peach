"""原生托盘与浏览器共用离线语言目录。"""
from __future__ import annotations

import re
from functools import lru_cache

from . import settings_file
from .stashdb_files import read_record

LANGUAGES = ('en', 'zh-CN', 'zh-TW', 'es', 'fr', 'de', 'pt-BR', 'ja', 'ko', 'vi')


def language():
    value = read_record(settings_file.load_config().directory('state') / 'interface-language.json').get('language')
    return value if value in LANGUAGES else 'en'


@lru_cache(maxsize=10)
def catalog(locale):
    root = settings_file.PROJECT_ROOT
    folder = root / 'i18n' if (root / 'i18n').is_dir() else root / 'frontend/src/i18n'
    english = {**read_record(folder / 'en.generated.json'), **read_record(folder / 'en.json')}
    return english if locale == 'en' else {**english, **read_record(folder / f'{locale}.json')}


def translate(text, locale=None):
    locale = locale or language()
    if locale == 'zh-CN':
        return text
    selected = catalog(locale)
    if text in selected:
        return selected[text]
    for source in ('状态：{0}', '地址：{0}', '运行中 · {0} 项提醒', 'HTTP {0}', 'HTTPS {0}'):
        prefix, suffix = source.split('{0}')
        if text.startswith(prefix) and text.endswith(suffix):
            value = text[len(prefix):len(text) - len(suffix) if suffix else None]
            return selected.get(source, source).replace('{0}', translate(value, locale))
    for pattern, keys, target in templates(locale):
        match = pattern.fullmatch(text)
        if match:
            for key, value in zip(keys, match.groups()):
                target = target.replace('{' + key + '}', selected.get(value, value))
            return target
    return text


@lru_cache(maxsize=10)
def templates(locale):
    result = []
    for source, target in catalog(locale).items():
        keys = re.findall(r'\{(\d+)\}', source)
        if not keys or len(re.sub(r'\{\d+\}', '', source)) < 2:
            continue
        pattern = re.escape(source)
        for key in keys:
            pattern = pattern.replace(re.escape('{' + key + '}'), '(.+?)', 1)
        result.append((re.compile(pattern), keys, target))
    return result


def menu_item(text, *args, **kwargs):
    import pystray
    label = (lambda item: translate(text(item))) if callable(text) else (lambda _item: translate(text))
    return pystray.MenuItem(label, *args, **kwargs)
