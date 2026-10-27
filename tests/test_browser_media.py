"""浏览器按片源实际容器、编码、音频和 profile 协商直读。"""
import unittest
from pathlib import Path

from peach.browser_media import probe_description
from peach.transcodes import TranscodeService, _MediaProfile


class BrowserMediaTests(unittest.TestCase):
    def test_hevc_main10_probe_describes_the_source_not_a_generic_mp4(self):
        profile = _MediaProfile('hevc', 'yuv420p10le', 'aac', video_profile='Main 10',
                                video_level=153, width=3840, height=2160, framerate=30, bitrate=4000000)
        result = probe_description(Path('movie.mp4'), profile)
        self.assertEqual(result['content_type'], 'video/mp4; codecs="hvc1.2.4.L153.B0,mp4a.40.2"')
        self.assertEqual(result['width'], 3840)

    def test_supported_source_combinations_are_not_limited_to_av1(self):
        for suffix, video, audio, pixel in [('.mp4', 'hevc', 'aac', 'yuv420p10le'),
                ('.mp4', 'h264', 'eac3', 'yuv420p'), ('.mp4', 'av1', 'opus', 'yuv420p10le'),
                ('.webm', 'vp9', 'opus', 'yuv420p10le'), ('.webm', 'vp8', 'vorbis', 'yuv420p'),
                ('.ogv', 'theora', 'vorbis', 'yuv420p'), ('.mov', 'h264', 'alac', 'yuv420p')]:
            with self.subTest(suffix=suffix, video=video, audio=audio):
                profile = _MediaProfile(video, pixel, audio)
                self.assertTrue(TranscodeService._browser_compatible(Path('movie' + suffix), profile, native_play=True))
                self.assertFalse(TranscodeService._browser_compatible(Path('movie' + suffix), profile, native_play=False))

    def test_unknown_audio_and_broken_timestamps_do_not_bypass_conversion(self):
        for profile in (_MediaProfile('hevc', 'yuv420p10le', 'unknown'),
                        _MediaProfile('h264', 'yuv420p', 'aac', decode_order_timestamps=True)):
            self.assertFalse(TranscodeService._browser_compatible(Path('movie.mp4'), profile, native_play=True))

    def test_profile_projection_handles_unavailable_numeric_probe_fields(self):
        fields = TranscodeService._browser_profile_fields({'r_frame_rate': '0/0', 'level': 'N/A', 'bit_rate': 'N/A'}, {}, {})
        self.assertEqual(fields['framerate'], 0)
        self.assertEqual(fields['video_level'], -1)
        self.assertEqual(fields['bitrate'], 0)
