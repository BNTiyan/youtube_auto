#!/usr/bin/env python3
"""
Daily YouTube Upload Scheduler
Automatically uploads N videos per day per channel from a queue.
Tracks what's already been uploaded so it never double-posts.

Usage:
    # Upload now (use with cron for true daily scheduling)
    python scheduler.py --run-now

    # Upload for a specific channel only
    python scheduler.py --run-now --channel "Kids Learning"

    # Preview what would be uploaded (no actual upload)
    python scheduler.py --run-now --dry-run

    # Show queue status for all channels
    python scheduler.py --status

    # Run as a background daemon (uploads at the scheduled time daily)
    python scheduler.py --daemon

    # Reset a video so it gets re-uploaded
    python scheduler.py --reset path/to/video.mp4 --channel "Kids Learning"

Cron setup (upload at 9:00 AM daily):
    crontab -e
    0 9 * * * cd /Users/upenbhava/Documents/youtube_auto && python scheduler.py --run-now >> logs/scheduler.log 2>&1
"""

import os
import sys
import glob
import json
import argparse
from datetime import datetime
from pathlib import Path

# ── Import from youtube_auto ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from youtube_auto import (
    get_youtube_service,
    generate_metadata_with_gemini,
    upload_video,
    ping_google_sitemap,
)
from googleapiclient.errors import HttpError

# ── CONFIG ────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_FILE = "scheduler_config.json"
LOG_DIR = "logs"


# ── LOGGING ───────────────────────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}]  {msg}", flush=True)


def ensure_logs_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


# ── UPLOAD LOG (per-channel state tracking) ───────────────────────────────────

def load_upload_log(log_file: str) -> dict:
    """Returns {video_path: {video_id, title, uploaded_at}}"""
    if os.path.exists(log_file):
        with open(log_file) as f:
            return json.load(f)
    return {}


def save_upload_log(log_file: str, data: dict):
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(data, f, indent=2)


def mark_uploaded(log_file: str, video_path: str, video_id: str, title: str):
    data = load_upload_log(log_file)
    data[os.path.abspath(video_path)] = {
        "video_id":    video_id,
        "title":       title,
        "uploaded_at": datetime.now().isoformat(),
    }
    save_upload_log(log_file, data)


# ── VIDEO QUEUE MANAGEMENT ────────────────────────────────────────────────────

def get_pending_videos(videos_dir: str, log_file: str) -> list[str]:
    """Return sorted list of MP4 paths not yet uploaded."""
    uploaded = set(load_upload_log(log_file).keys())
    exts = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm")
    all_videos = []
    for ext in exts:
        all_videos.extend(glob.glob(os.path.join(videos_dir, ext)))
    all_videos = sorted(set(os.path.abspath(v) for v in all_videos))
    return [v for v in all_videos if v not in uploaded]


def topic_from_filename(filename: str, topic_map: dict) -> str:
    """Derive a descriptive topic string from the video filename."""
    stem = Path(filename).stem.lower().replace("_learning", "").replace("_", " ").strip()
    for key, topic in topic_map.items():
        if key.lower() in stem:
            return topic
    # Fallback: capitalise the stem
    return stem.title()


# ── CHANNEL UPLOAD SESSION ────────────────────────────────────────────────────

def run_channel(channel_cfg: dict, youtube, dry_run: bool = False) -> int:
    """
    Upload up to daily_limit pending videos for one channel.
    Returns the number of videos uploaded.
    """
    name        = channel_cfg["name"]
    videos_dir  = channel_cfg["videos_dir"]
    log_file    = channel_cfg["upload_log"]
    daily_limit = channel_cfg.get("daily_limit", 5)
    niche       = channel_cfg.get("niche", "General")
    tone        = channel_cfg.get("tone", "engaging and informative")
    category_id = channel_cfg.get("category_id", "22")
    privacy     = channel_cfg.get("privacy", "public")
    made_for_kids = channel_cfg.get("made_for_kids", False)
    topic_map   = channel_cfg.get("topic_map", {})

    if not os.path.isdir(videos_dir):
        log(f"⚠️   [{name}] Videos directory not found: {videos_dir}")
        return 0

    pending = get_pending_videos(videos_dir, log_file)
    if not pending:
        log(f"✅  [{name}] Queue empty — nothing to upload today.")
        return 0

    to_upload = pending[:daily_limit]
    log(f"📋  [{name}] Pending: {len(pending)} videos | Uploading: {len(to_upload)} today")
    uploaded_count = 0

    for video_path in to_upload:
        filename = os.path.basename(video_path)
        topic = topic_from_filename(filename, topic_map)

        log(f"  📤  {filename}")
        log(f"      Topic : {topic}")
        log(f"      Niche : {niche}")

        # Generate metadata with Gemini
        try:
            metadata = generate_metadata_with_gemini(
                video_topic=topic,
                niche=niche,
                tone=tone,
            )
        except Exception as e:
            log(f"  ❌  Gemini metadata failed for {filename}: {e}")
            continue

        if dry_run:
            log(f"  ⚠️   DRY RUN — would upload '{filename}'")
            log(f"       Title: {metadata['title']}")
            uploaded_count += 1
            continue

        # Upload
        try:
            video_id = upload_video(
                youtube=youtube,
                video_path=video_path,
                metadata=metadata,
                category_id=category_id,
                privacy=privacy,
                made_for_kids=made_for_kids,
            )
            mark_uploaded(log_file, video_path, video_id, metadata["title"])
            log(f"  ✅  Uploaded → https://www.youtube.com/watch?v={video_id}")
            uploaded_count += 1

        except HttpError as e:
            log(f"  ❌  YouTube API error for {filename}: {e}")
        except Exception as e:
            log(f"  ❌  Upload failed for {filename}: {e}")

    return uploaded_count


# ── STATUS REPORT ─────────────────────────────────────────────────────────────

def show_status(config: dict):
    print("\n" + "=" * 60)
    print("  📊  Upload Queue Status")
    print("=" * 60)

    for channel in config["channels"]:
        name       = channel["name"]
        videos_dir = channel["videos_dir"]
        log_file   = channel["upload_log"]
        daily      = channel.get("daily_limit", 5)

        upload_log = load_upload_log(log_file)
        exts = ("*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm")
        all_videos = []
        for ext in exts:
            all_videos.extend(glob.glob(os.path.join(videos_dir, ext)))
        all_videos = sorted(set(os.path.abspath(v) for v in all_videos))
        pending = [v for v in all_videos if v not in upload_log]

        print(f"\n📺  {name}")
        print(f"    Directory   : {videos_dir}")
        print(f"    Total videos: {len(all_videos)}")
        print(f"    Uploaded    : {len(upload_log)}")
        print(f"    Pending     : {len(pending)}")
        print(f"    Daily limit : {daily}")

        # Estimate days remaining
        if pending and daily > 0:
            days = (len(pending) + daily - 1) // daily
            print(f"    Queue covers: ~{days} day(s)")

        if pending:
            print(f"    Next up     :")
            for v in pending[:5]:
                print(f"      - {os.path.basename(v)}")
            if len(pending) > 5:
                print(f"      ... and {len(pending) - 5} more")

        # Show last 3 uploads
        if upload_log:
            recent = sorted(upload_log.items(), key=lambda x: x[1].get("uploaded_at", ""), reverse=True)[:3]
            print(f"    Recent uploads:")
            for path, info in recent:
                ts = info.get("uploaded_at", "")[:10]
                print(f"      [{ts}] {info.get('title', os.path.basename(path))[:55]}")

    print("\n" + "=" * 60)


# ── RESET (remove a video from the upload log) ────────────────────────────────

def reset_video(video_path: str, channel_cfg: dict):
    log_file = channel_cfg["upload_log"]
    data = load_upload_log(log_file)
    abs_path = os.path.abspath(video_path)
    if abs_path in data:
        del data[abs_path]
        save_upload_log(log_file, data)
        log(f"✅  Removed from upload log: {video_path}")
    else:
        log(f"⚠️   Not found in upload log: {video_path}")


# ── MAIN RUNNER ───────────────────────────────────────────────────────────────

def run_all_channels(config: dict, target_channel: str | None, dry_run: bool):
    """Authenticate once, then process each channel in sequence."""
    channels = config["channels"]
    if target_channel:
        channels = [c for c in channels if c["name"].lower() == target_channel.lower()]
        if not channels:
            log(f"❌  No channel named '{target_channel}' found in config.")
            return

    log("=" * 50)
    log(f"🚀  YouTube Scheduler — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if dry_run:
        log("⚠️   DRY RUN mode — no actual uploads")
    log("=" * 50)

    youtube = None
    if not dry_run:
        youtube = get_youtube_service()

    total_uploaded = 0
    for channel in channels:
        log(f"\n▶  Channel: {channel['name']}")
        count = run_channel(channel, youtube, dry_run=dry_run)
        log(f"   Uploaded {count} video(s) for {channel['name']}")
        total_uploaded += count

    if total_uploaded > 0 and not dry_run:
        # Automatically ping Google Search Console after success
        log("📡  Automated upload successful. Sending ping to Google Search...")
        try:
            ping_google_sitemap()
        except NameError:
            # handle case where function isn't imported correctly if necessary
            pass

    log(f"\n🎉  Session complete. Total uploaded: {total_uploaded}")
    log("=" * 50)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Daily YouTube upload scheduler for multiple channels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scheduler.py --run-now                        # upload all channels
  python scheduler.py --run-now --channel "Kids Learning"
  python scheduler.py --run-now --dry-run              # preview only
  python scheduler.py --status                         # show queue
  python scheduler.py --daemon                         # run daily at scheduled time
  python scheduler.py --reset videos/ai.mp4 --channel "Tech Learning"

Cron (9 AM daily):
  0 9 * * * cd /path/to/youtube_auto && python scheduler.py --run-now >> logs/scheduler.log 2>&1
        """,
    )
    parser.add_argument("--config",   default=DEFAULT_CONFIG_FILE, help="Scheduler config JSON")
    parser.add_argument("--run-now",  action="store_true",  help="Run upload session immediately")
    parser.add_argument("--status",   action="store_true",  help="Show queue status and exit")
    parser.add_argument("--daemon",   action="store_true",  help="Run as background daemon (uses 'schedule' library)")
    parser.add_argument("--dry-run",  action="store_true",  help="Preview uploads without actually uploading")
    parser.add_argument("--channel",  default=None,         help="Target a specific channel by name")
    parser.add_argument("--reset",    metavar="VIDEO_PATH", help="Remove a video from the upload log")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"❌  Config not found: {args.config}")
        print(f"    Create it or run:  cp scheduler_config.json.example {args.config}")
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    ensure_logs_dir()

    # ── Status ────────────────────────────────────────────────────────────
    if args.status:
        show_status(config)
        return

    # ── Reset ─────────────────────────────────────────────────────────────
    if args.reset:
        channels = config["channels"]
        if args.channel:
            channels = [c for c in channels if c["name"].lower() == args.channel.lower()]
        for channel in channels:
            reset_video(args.reset, channel)
        return

    # ── Run Now ───────────────────────────────────────────────────────────
    if args.run_now:
        run_all_channels(config, args.channel, dry_run=args.dry_run)
        return

    # ── Daemon ────────────────────────────────────────────────────────────
    if args.daemon:
        try:
            import schedule
            import time
        except ImportError:
            print("❌  'schedule' library not installed. Run: pip install schedule")
            sys.exit(1)

        schedule_time = config.get("schedule_time", "09:00")
        log(f"🕐  Daemon started. Will upload daily at {schedule_time}")
        log(f"    Press Ctrl+C to stop.")

        def job():
            run_all_channels(config, args.channel, dry_run=args.dry_run)

        schedule.every().day.at(schedule_time).do(job)

        while True:
            schedule.run_pending()
            time.sleep(30)

    # ── No mode selected ──────────────────────────────────────────────────
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
