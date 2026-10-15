import unittest
from datetime import datetime
from publishing_schedule import next_publish_time


class PublishingScheduleTests(unittest.TestCase):
    def at(self, slot, now):
        return next_publish_time(slot, datetime.fromisoformat(now))

    def test_video_is_five_ist(self):
        self.assertEqual(self.at('video', '2026-10-16T05:00:00+00:00'), '2026-10-16T11:30:00Z')

    def test_ist_has_no_dst_change(self):
        self.assertEqual(self.at('video', '2026-11-02T05:00:00+00:00'), '2026-11-02T11:30:00Z')

    def test_video_skips_weekend_and_missed_slot(self):
        self.assertEqual(self.at('video', '2026-10-16T12:00:00+00:00'), '2026-10-19T11:30:00Z')

    def test_short_is_seven_ist(self):
        self.assertEqual(self.at('short', '2026-10-15T05:00:00+00:00'), '2026-10-15T13:30:00Z')
        self.assertEqual(self.at('short', '2026-11-02T05:00:00+00:00'), '2026-11-02T13:30:00Z')

    def test_late_short_rolls_to_tomorrow(self):
        self.assertEqual(self.at('short', '2026-10-15T13:31:00+00:00'), '2026-10-16T13:30:00Z')

    def test_processing_buffer(self):
        self.assertEqual(self.at('video', '2026-10-16T11:20:00+00:00'), '2026-10-19T11:30:00Z')

    def test_uses_indian_calendar_date(self):
        self.assertEqual(self.at('video', '2026-10-18T20:00:00+00:00'), '2026-10-19T11:30:00Z')

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):
            self.at('short', '2026-10-15T14:00:00')
