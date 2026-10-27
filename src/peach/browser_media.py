"""将媒体探测结果投影为浏览器可查询的容器与编码描述。"""
import re
import mimetypes

MIME_TYPES = {
    '.mp4': 'video/mp4', '.m4v': 'video/mp4', '.mov': 'video/quicktime',
    '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.ogv': 'video/ogg', '.ogg': 'video/ogg',
    '.avi': 'video/x-msvideo', '.mpg': 'video/mpeg', '.mpeg': 'video/mpeg',
    '.ts': 'video/mp2t', '.mts': 'video/mp2t', '.m2ts': 'video/mp2t', '.3gp': 'video/3gpp',
    '.wmv': 'video/x-ms-wmv', '.asf': 'video/x-ms-asf', '.flv': 'video/x-flv', '.m2v': 'video/mpeg',
}
AUDIO_CODECS = {'mp3': 'mp3', 'opus': 'opus', 'vorbis': 'vorbis', 'flac': 'flac',
                'alac': 'alac', 'ac3': 'ac-3', 'eac3': 'ec-3', 'dts': 'dtsc',
                'pcm_s16le': '1', 'pcm_s24le': '1'}


def source_mime(source):
    return MIME_TYPES.get(source.suffix.lower()) or mimetypes.guess_type(str(source))[0] or ''


def video_codec(profile):
    codec, name, level = profile.video_codec, profile.video_profile.lower(), profile.video_level
    depth = 12 if '12' in profile.pixel_format else 10 if '10' in profile.pixel_format else 8
    if codec == 'h264':
        identifier = {'baseline': 66, 'constrained baseline': 66, 'main': 77, 'extended': 88,
                      'high': 100, 'high 10': 110, 'high 4:2:2': 122, 'high 4:4:4 predictive': 244}.get(name)
        return f'avc1.{identifier:02x}00{(level if level > 0 else 40):02x}' if identifier else 'avc1'
    if codec == 'hevc':
        identifier = 2 if '10' in name else 1
        tag = profile.video_tag if profile.video_tag in ('hvc1', 'hev1') else 'hvc1'
        return f'{tag}.{identifier}.{4 if identifier == 2 else 6}.L{level if level > 0 else 120}.B0'
    if codec == 'av1':
        identifier = {'high': 1, 'professional': 2}.get(name, 0)
        return f'av01.{identifier}.{level if 0 <= level <= 23 else 8:02d}M.{depth:02d}'
    if codec == 'vp9':
        identifier = int(name[-1]) if name and name[-1].isdigit() else 2 if depth > 8 else 0
        return f'vp09.{identifier:02d}.{level if level > 0 else 10:02d}.{depth:02d}'
    if codec in ('vp8', 'theora'):
        return codec
    if codec == 'mpeg4':
        return 'mp4v.20.9'
    return profile.video_tag if re.fullmatch(r'[A-Za-z0-9]{4}', profile.video_tag) else ''


def probe_description(source, profile):
    mime = source_mime(source)
    video = video_codec(profile)
    audio = ('mp4a.40.' + str({'he-aac': 5, 'he-aacv2': 29}.get(profile.audio_profile.lower(), 2))
             if profile.audio_codec == 'aac' else AUDIO_CODECS.get(profile.audio_codec, ''))
    codecs = ','.join(filter(None, (video, audio)))
    known = bool(mime and video and (not profile.audio_codec or audio))
    return {'mime_type': mime, 'content_type': f'{mime}; codecs="{codecs}"' if known else '',
            'video_content_type': f'{mime}; codecs="{video}"' if mime and video else '',
            'audio_content_type': f'{mime.replace("video/", "audio/")}; codecs="{audio}"' if mime and audio else '',
            'video_codec': profile.video_codec, 'audio_codec': profile.audio_codec,
            'width': profile.width, 'height': profile.height, 'framerate': profile.framerate,
            'bitrate': profile.bitrate, 'timestamp_repair': profile.decode_order_timestamps}
