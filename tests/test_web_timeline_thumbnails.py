"""时间轴预览的档位与采集任务端点。"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from peach import task_runs, timeline_sheets, web_timeline_thumbnails


class ModeFileTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="timeline-mode-"))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.path = self.root / "timeline-thumbnails.json"

    def test_an_unreadable_setting_means_the_job_stays_off(self):
        """这条链会写盘也会读片子，不能靠猜来开。"""
        self.assertEqual(web_timeline_thumbnails.read_mode(self.path), "off")
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual(web_timeline_thumbnails.read_mode(self.path), "off")
        self.path.write_text(json.dumps({"mode": "hourly"}), encoding="utf-8")
        self.assertEqual(web_timeline_thumbnails.read_mode(self.path), "off")

    def test_the_chosen_density_survives_a_restart(self):
        web_timeline_thumbnails.write_mode("coarse", self.path)
        self.assertEqual(web_timeline_thumbnails.read_mode(self.path), "coarse")


class ThumbnailJobEndpointTests(unittest.TestCase):
    def test_custom_interval_roundtrip_and_invalid_input(self):
        resolver = MagicMock()
        resolver.return_value.ffmpeg.return_value.path = 'ffmpeg'
        with patch.object(web_timeline_thumbnails, 'FFmpegResolver', resolver):
            result = web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {'mode': 'custom', 'interval_seconds': 17})
        self.assertEqual(result['mode'], 'custom')
        self.assertEqual(result['interval_seconds'], 17)
        self.assertEqual(self.contract.thumbnail_job.start.call_args.kwargs['recovery']['interval_seconds'], 17)
        for value in (0, 3601, True, 1.5):
            with self.assertRaises(ValueError):
                web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {'mode': 'custom', 'interval_seconds': value})

    def test_acceleration_saves_without_starting_a_job(self):
        for value in ('cpu', 'cuda', 'vulkan'):
            result = web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {'action': 'set_acceleration', 'acceleration': value})
            self.assertEqual(result['acceleration'], value)
        self.contract.thumbnail_job.start.assert_not_called()
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="timeline-endpoint-"))
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.contract = MagicMock()
        self.contract.timeline_root = self.root / "sheets"
        self.contract.db_path = self.root / "ledger.db"
        self.contract.thumbnail_job.snapshot.return_value = {}
        patcher = patch.object(web_timeline_thumbnails, "MODE_PATH",
                               self.root / "timeline-thumbnails.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_unknown_density_is_refused_before_anything_starts(self):
        with self.assertRaises(ValueError):
            web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {"mode": "every-second"})
        self.contract.thumbnail_job.start.assert_not_called()
        self.assertEqual(web_timeline_thumbnails.read_mode(), "off")

    def test_speed_is_persisted_independently_without_starting_or_stopping_a_job(self):
        web_timeline_thumbnails.write_mode('precise')
        self.assertEqual(web_timeline_thumbnails.q_thumbnail_jobs(self.contract, {})['speed_mode'], 'low')
        for mode in ('high', 'standard', 'low'):
            state = web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {'action': 'set_speed', 'speed_mode': mode})
            self.assertEqual(state['speed_mode'], mode)
            self.assertEqual(state['mode'], 'precise')
            self.assertEqual(web_timeline_thumbnails._speed_control().mode, mode)
        self.contract.thumbnail_job.start.assert_not_called()
        self.contract.thumbnail_job.stop.assert_not_called()
        with self.assertRaises(ValueError):
            web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {'action': 'set_speed', 'speed_mode': 'invalid'})

    def test_terminal_job_or_task_record_stops_frame_extraction(self):
        web_timeline_thumbnails.write_mode('precise')
        self.contract.thumbnail_job.snapshot.return_value = {'job_id': 'one', 'status': 'running', 'run_id': 7}
        self.contract.task_runs.get.return_value.active = True
        with patch.object(web_timeline_thumbnails, 'metadata_only', return_value=False):
            self.assertTrue(web_timeline_thumbnails._active(self.contract, 'one'))
            self.contract.task_runs.get.return_value.active = False
            self.assertFalse(web_timeline_thumbnails._active(self.contract, 'one'))
            self.contract.thumbnail_job.snapshot.return_value['status'] = 'complete'
            self.assertFalse(web_timeline_thumbnails._active(self.contract, 'one'))

    def test_disabled_density_stops_frame_extraction(self):
        self.contract.thumbnail_job.snapshot.return_value = {'job_id': 'one', 'status': 'running'}
        self.assertFalse(web_timeline_thumbnails._active(self.contract, 'one'))

    def test_turning_it_off_stops_the_run_and_keeps_the_sheets(self):
        """几 GB 的产物删不删是另一件事，走数据管理页那条清理链。"""
        web_timeline_thumbnails.write_mode("precise")
        made = timeline_sheets.sheet_path(self.contract.timeline_root, 3, 0)
        made.parent.mkdir(parents=True)
        made.write_bytes(b"sheet")
        state = web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {"mode": "off"})
        self.contract.thumbnail_job.stop.assert_called_once_with(resume=False)
        self.assertEqual(state["mode"], "off")
        self.assertTrue(made.is_file())

    def test_choosing_a_density_starts_the_run_and_reports_it(self):
        resolver = MagicMock()
        resolver.return_value.ffmpeg.return_value.path = "ffmpeg"
        with patch.object(web_timeline_thumbnails, "FFmpegResolver", resolver):
            state = web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {"mode": "coarse"})
        self.assertEqual(state["mode"], "coarse")
        self.assertEqual(state["intervals"]["coarse"], 30)
        started = self.contract.thumbnail_job.start.call_args
        self.assertTrue(started.kwargs["restart"])
        self.assertEqual(started.kwargs["initial"]["interval"], 30)

    def test_the_run_reports_its_count_where_the_activity_page_reads_it(self):
        """进度只在活动页上看：任务中心读 `checked` / `total` 和那一行 `stage`。"""
        resolver = MagicMock()
        resolver.return_value.ffmpeg.return_value.path = "ffmpeg"
        with patch.object(web_timeline_thumbnails, "FFmpegResolver", resolver):
            web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {"mode": "coarse"})
        started = self.contract.thumbnail_job.start.call_args
        self.assertEqual((started.kwargs["initial"]["checked"], started.kwargs["initial"]["stage"]),
                         (0, "采集缩略图"))
        work = started.args[0]

        def generate(*_args, report, **_kwargs):
            report(total=12, done=5, made=5, skipped=0, failed=0, stopped="")
            return {"total": 12, "done": 12, "made": 11, "skipped": 1, "failed": 0, "stopped": ""}

        with patch.object(timeline_sheets, "generate_library", side_effect=generate),                 patch.object(web_timeline_thumbnails, "DiskGuard"):
            work("job-1")
        updates = [call.kwargs for call in self.contract.thumbnail_job.update.call_args_list]
        self.assertEqual([(u["checked"], u["total"]) for u in updates], [(5, 12), (12, 12)])
        self.assertEqual(updates[-1]["status"], "complete")
        self.assertEqual(task_runs.task_label("timeline-thumbnails"), "视频缩略图采集")

    def test_without_ffmpeg_the_density_cannot_be_turned_on(self):
        resolver = MagicMock()
        resolver.return_value.ffmpeg.return_value = None
        with patch.object(web_timeline_thumbnails, "FFmpegResolver", resolver):
            with self.assertRaises(ValueError):
                web_timeline_thumbnails.w_thumbnail_jobs(self.contract, {"mode": "precise"})
        self.contract.thumbnail_job.start.assert_not_called()

    def test_a_video_with_no_sheets_reports_an_empty_index(self):
        """页面据此决定要不要画这一层；空对象就是退回九宫格。"""
        self.assertEqual(web_timeline_thumbnails.q_timeline(self.contract, {"id": "7"}), {})
        self.assertEqual(web_timeline_thumbnails.q_timeline(self.contract, {}), {})

    def test_a_video_with_sheets_reports_the_interval_and_frame_count(self):
        directory = timeline_sheets.sheet_dir(self.contract.timeline_root, 7)
        directory.mkdir(parents=True)
        (directory / "meta.json").write_text(
            json.dumps({"interval": 30, "frames": 120, "sheets": 2, "columns": 10}),
            encoding="utf-8")
        index = web_timeline_thumbnails.q_timeline(self.contract, {"id": "7"})
        self.assertEqual((index["interval"], index["frames"]), (30, 120))


if __name__ == "__main__":
    unittest.main()
