"""共享转码空间预算只管理可再生媒体缓存。"""
import tempfile
import unittest
from pathlib import Path

from peach.transcode_cache import CacheBudget, load, roots, save


class CacheBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.full = self.root / 'files'
        self.hls = self.root / 'segments'
        self.full.mkdir()
        self.hls.mkdir()

    def test_preferences_roundtrip_with_isolated_cache_children(self):
        value = save(self.root, {'folder': str(self.root), 'max_gb': 3})
        self.assertEqual(load(self.root), value)
        self.assertEqual(roots(value, self.full, self.hls),
                         (self.root / 'peach-transcode-cache/files', self.root / 'peach-transcode-cache/segments'))
        for invalid in (0, 1025, True, 1.5):
            with self.assertRaises(ValueError):
                save(self.root, {'max_gb': invalid})

    def test_shared_limit_preserves_active_writes_and_unrelated_files(self):
        old = self.full / '1-source.mp4'
        old.write_bytes(b'x' * 8)
        active = self.hls / 'active.ts'
        active.write_bytes(b'x' * 8)
        unrelated = self.full / 'original.mp4'
        unrelated.write_bytes(b'x' * 100)
        budget = CacheBudget(self.full, self.hls, 10)
        with budget.writing(active):
            self.assertTrue(budget.enforce(force=True))
        self.assertFalse(old.exists())
        self.assertTrue(active.exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual(budget.usage(), 8)

    def test_active_output_larger_than_budget_is_rejected(self):
        active = self.full / '2-source.tmp.mp4'
        active.write_bytes(b'x' * 12)
        budget = CacheBudget(self.full, self.hls, 10)
        with budget.writing(active):
            self.assertFalse(budget.enforce(force=True))
        self.assertTrue(active.exists())

    def test_over_budget_output_is_not_published_as_a_complete_movie(self):
        from peach.transcodes import TranscodeCacheFull, TranscodeService
        temporary = self.full / '3-source.tmp.mp4'
        target = self.full / '3-source.mp4'
        temporary.write_bytes(b'x' * 12)
        service = TranscodeService(None, self.full)
        service.cache_budget = CacheBudget(self.full, self.hls, 10)
        with service.cache_budget.writing(temporary), self.assertRaises(TranscodeCacheFull):
            service._publish_cache(temporary, target, 0)
        self.assertFalse(target.exists())
