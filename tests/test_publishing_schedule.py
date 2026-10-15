import unittest
from datetime import datetime
from publishing_schedule import next_publish_time


class PublishingScheduleTests(unittest.TestCase):
    def at(self, slot, now):
        return next_publish_time(slot, datetime.fromisoformat(now))

    def test_summer_video_is_five_eastern(self):
        self.assertEqual(self.at('video', '2026-10-16T14:00:00+00:00'), '2026-10-16T21:00:00Z')

    def test_winter_video_handles_dst(self):
        self.assertEqual(self.at('video', '2026-11-02T14:00:00+00:00'), '2026-11-02T22:00:00Z')

    def test_video_skips_weekend_and_missed_slot(self):
        self.assertEqual(self.at('video', '2026-10-16T22:00:00+00:00'), '2026-10-19T21:00:00Z')

    def test_short_is_seven_eastern(self):
        self.assertEqual(self.at('short', '2026-10-15T14:00:00+00:00'), '2026-10-15T23:00:00Z')
        self.assertEqual(self.at('short', '2026-11-02T14:00:00+00:00'), '2026-11-03T00:00:00Z')

    def test_late_short_rolls_to_tomorrow(self):
        self.assertEqual(self.at('short', '2026-10-15T23:01:00+00:00'), '2026-10-16T23:00:00Z')

    def test_processing_buffer(self):
        self.assertEqual(self.at('video', '2026-10-16T20:50:00+00:00'), '2026-10-19T21:00:00Z')

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            self.at('short', '2026-10-15T14:00:00')
