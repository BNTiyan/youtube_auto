#!/usr/bin/env python3
"""
YouTube Auto-Upload Script with AI-Generated Descriptions & Hashtags
Uses local Ollama or optional Gemini for titles, descriptions, and hashtags.
Uses YouTube Data API v3 to upload the video.

Requirements:
    pip install google-auth google-auth-oauthlib google-api-python-client google-generativeai

Setup:
    1. Go to https://console.cloud.google.com → Create Project → Enable "YouTube Data API v3"
    2. Create OAuth 2.0 credentials (Desktop App) → Download as client_secrets.json
    3. Get your Gemini API key from https://aistudio.google.com/
    4. Place client_secrets.json in the same folder as this script
"""

import os
import sys
import json
import argparse
import time
import glob
import re
from llm_client import generate_json, provider_name
from publishing_schedule import next_publish_time
import requests
import httplib2

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# ─── GOOGLE SITEMAP PING ─────────────────────────────────────────────────────

def ping_google_sitemap(sitemap_url="https://bts.navadishatechnologies.org/sitemap.xml"):
    """
    Notify Google that the sitemap has been updated.
    This encourages Google to re-crawl the site.
    """
    ping_url = f"https://www.google.com/ping?sitemap={sitemap_url}"
    print(f"\n📡  Pinging Google with updated sitemap: {sitemap_url}")
    try:
        response = requests.get(ping_url, timeout=10)
        if response.status_code == 200:
            print("✅  Google successfully notified!")
        else:
            print(f"⚠️   Google ping returned status: {response.status_code}")
    except Exception as e:
        print(f"❌  Failed to ping Google: {e}")


# ─── CONFIG ──────────────────────────────────────────────────────────────────

CLIENT_SECRETS_FILE = "client_secrets.json"   # OAuth2 credentials from Google Cloud
TOKEN_FILE          = "youtube_token.json"     # Saved OAuth token (auto-created)
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")  # or paste key directly
YOUTUBE_SCOPES      = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",   # needed for videos.update()
]

# ─── YOUTUBE AUTH ─────────────────────────────────────────────────────────────

def get_youtube_service():
    """Authenticate and return a YouTube API service object."""
    creds = None

    # Load saved token if it exists
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, YOUTUBE_SCOPES)

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_FILE):
                print(f"\n❌  '{CLIENT_SECRETS_FILE}' not found.")
                print("    Download it from Google Cloud Console → APIs & Services → Credentials")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next run
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"✅  YouTube token saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


# ─── GEMINI AI GENERATION ────────────────────────────────────────────────────

def generate_metadata_with_gemini(video_topic: str, niche: str, tone: str) -> dict:
    """
    Generate metadata using the configured LLM (legacy name for scheduler compatibility).
    Returns a dict: { title, description, tags }
    """
    prompt = f"""You are an expert YouTube SEO strategist. Generate metadata for a YouTube video.

Video Topic: {video_topic}
Niche/Category: {niche}
Tone: {tone}

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:
{{
  "title": "A compelling, click-worthy title under 70 characters with primary keyword",
  "description": "An SEO-optimized description of 200-300 words. Include:\\n- Hook in first 2 lines (shown before 'Show more')\\n- What viewers will learn\\n- Timestamps placeholder (00:00 Intro, etc.)\\n- CTA to like/subscribe/comment\\n- 3-5 relevant keywords naturally woven in",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10"]
}}

Rules:
- Title: Lead with a specific source-supported question, surprising detail, or practical benefit.
- Avoid generic titles such as "All About X" and niche suffixes such as "| Kids Education".
- Do not invent facts, numbers, outcomes, or promises. No clickbait; keep the topic keyword.
- Description: Conversational yet professional, must include 5 hashtags at the end like #Tag
- Tags: Mix of broad and niche keywords, all lowercase, no # symbol in tags array"""

    print(f"\n🤖  Generating metadata with {provider_name()}...")
    metadata = generate_json(prompt)
    for field in ("title", "description"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"LLM metadata requires a nonempty {field}")
    tags = metadata.get("tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("LLM metadata tags must be a list of strings")
    metadata["title"] = metadata["title"][:100]
    metadata["description"] = metadata["description"][:5000]

    print(f"\n📝  Generated Title     : {metadata['title']}")
    print(f"🏷️   Generated Tags      : {', '.join(metadata['tags'][:5])}...")
    print(f"📄  Description Preview : {metadata['description'][:120]}...")

    return metadata


def generate_metadata_fallback(video_topic: str, niche: str, tone: str) -> dict:
    """
    Fallback: Try to find the item in local JSON configs to gather keywords/info.
    """
    print(f"  🔍  Attempting local JSON lookup for: {video_topic}")
    
    # Clean topic name (e.g. "Lion (Filename context: Lion_Learning.mp4)" -> "Lion")
    clean_topic = video_topic
    match = re.search(r"context: ([^_]+)", video_topic)
    if match:
        clean_topic = match.group(1).strip()
    else:
        # Just grab the first word or handle simple string
        clean_topic = video_topic.split()[0].strip()

    # Directories to search
    config_dirs = ["content_config", "tech_content_config"]
    item_data = None
    
    for d in config_dirs:
        if not os.path.isdir(d):
            continue
        for fpath in glob.glob(os.path.join(d, "*.json")):
            try:
                with open(fpath) as f:
                    cfg = json.load(f)
                # Check for direct key match (case insensitive)
                for key, data in cfg.items():
                    if key.lower() == clean_topic.lower():
                        item_data = data
                        break
                if item_data: break
            except Exception:
                continue
        if item_data: break
        
    if item_data:
        print(f"  ✅  Found '{clean_topic}' in local JSON!")
        explanation = item_data.get("explanation", f"A video about {clean_topic}.")
        points = item_data.get("points", [])
        
        description = f"{explanation}\n\n"
        if points:
            description += "Key learning points:\n"
            for p in points:
                description += f"• {p}\n"
        description += f"\n#Youtube #Learning #Education #{clean_topic} #{niche.replace(' ', '')}"
        
        return {
            "title": f"{clean_topic}: Key Facts Explained",
            "description": description,
            "tags": [clean_topic.lower(), niche.lower(), "learning", "education", "facts"]
        }
    
    print(f"  ⚠️   No local JSON found for '{clean_topic}'. Using basic metadata.")
    return {
        "title": f"{clean_topic} Explained",
        "description": f"Learn about {clean_topic} in this {tone} video.\n\n#Youtube #Education #{clean_topic}",
        "tags": [clean_topic.lower(), "education", "learning"]
    }


# ─── YOUTUBE UPLOAD ──────────────────────────────────────────────────────────

def update_video(youtube, video_id: str, metadata: dict, category_id: str = "27") -> str:
    """
    Update title, description, and tags of an existing YouTube video.
    Requires the 'youtube' OAuth scope (broader than youtube.upload).
    If you get a 403, delete youtube_token.json and re-authenticate.
    """
    body = {
        "id": video_id,
        "snippet": {
            "title":       metadata["title"],
            "description": metadata["description"],
            "tags":        metadata["tags"],
            "categoryId":  category_id,
        },
    }

    print(f"\n📝  Updating metadata for video: {video_id}")
    response = youtube.videos().update(part="snippet", body=body).execute()
    vid = response.get("id")
    print(f"\n✅  Update complete!")
    print(f"🎬  Video URL : https://www.youtube.com/watch?v={vid}")
    return vid


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str) -> bool:
    """
    Upload a custom thumbnail for a YouTube video.
    Returns True if successfully uploaded, False otherwise.
    """
    if not os.path.exists(thumbnail_path):
        print(f"⚠️   Thumbnail image not found: {thumbnail_path}")
        return False

    print(f"\n🖼️   Uploading custom thumbnail: {os.path.basename(thumbnail_path)}...")
    mimetype = "image/png" if thumbnail_path.lower().endswith(".png") else "image/jpeg"
    try:
        media = MediaFileUpload(thumbnail_path, mimetype=mimetype, resumable=False)
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media
        ).execute()
        print(f"✅  Thumbnail successfully updated for video: {video_id}")
        return True
    except HttpError as e:
        print(f"⚠️   Thumbnail upload failed (HTTP {e.resp.status}): {e}")
        if e.resp.status == 403:
            print("    Note: Custom thumbnails require phone-verified account permissions in YouTube Studio.")
        return False
    except Exception as e:
        print(f"⚠️   Failed to upload thumbnail: {e}")
        return False


def upload_video(youtube, video_path: str, metadata: dict,
                 category_id: str = "22", privacy: str = "public",
                 made_for_kids: bool = False,
                 thumbnail_path: str = None,
                 publish_at: str = None) -> str:
    """
    Upload video to YouTube with the given metadata.
    category_id 22 = People & Blogs (common default)
    privacy: public | private | unlisted
    """
    if not os.path.exists(video_path):
        print(f"❌  Video file not found: {video_path}")
        sys.exit(1)

    body = {
        "snippet": {
            "title":       metadata["title"],
            "description": metadata["description"],
            "tags":        metadata["tags"],
            "categoryId":  category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
        }
    }

    if publish_at:
        from datetime import datetime, timezone
        scheduled = datetime.fromisoformat(publish_at.replace('Z', '+00:00'))
        if scheduled.tzinfo is None or scheduled <= datetime.now(timezone.utc):
            raise ValueError('Publication time must be timezone-aware and in the future')
        if privacy != 'public':
            raise ValueError('Scheduled publication requires public visibility intent')
        body['status'].update(privacyStatus='private', publishAt=publish_at)
        print(f"Scheduled publication: {publish_at} (UTC)")

    media = MediaFileUpload(
        video_path,
        mimetype="video/*",
        resumable=True,
        chunksize=1024 * 1024 * 5  # 5 MB chunks
    )

    print(f"\n📤  Uploading '{os.path.basename(video_path)}' to YouTube...")
    print(f"    Privacy: {privacy.upper()}")

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r    [{bar}] {pct}%", end="", flush=True)

    print(f"\n\n✅  Upload complete!")
    video_id = response.get("id")
    print(f"🎬  Video URL : https://www.youtube.com/watch?v={video_id}")
    print(f"🆔  Video ID  : {video_id}")

    # Custom thumbnail check and upload
    thumb_to_upload = thumbnail_path
    if not thumb_to_upload:
        # Check auto-generated thumbnail path next to video
        base, _ = os.path.splitext(video_path)
        for ext in ("_thumb.jpg", "_thumb.jpeg", "_thumb.png"):
            candidate = base + ext
            if os.path.exists(candidate):
                thumb_to_upload = candidate
                break

    if thumb_to_upload and os.path.exists(thumb_to_upload):
        upload_thumbnail(youtube, video_id, thumb_to_upload)

    return video_id


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto-upload YouTube videos with Gemini AI-generated metadata"
    )
    parser.add_argument("path",             nargs="?",
                        help="Path to a video file OR a directory containing videos (not needed for --update)")
    parser.add_argument("--topic",          default="General",
                        help="What is the video about? (default: General)")
    parser.add_argument("--niche",          default="General",
                        help="Channel niche (e.g. Kids Education, Animals, Science)")
    parser.add_argument("--tone",           default="engaging and informative",
                        help="Tone of the content (e.g. fun and educational for children)")
    parser.add_argument("--privacy",        default="public",
                        choices=["public", "private", "unlisted"],
                        help="Video privacy setting (default: public)")
    parser.add_argument("--category",       default="22",
                        help="YouTube category ID (22=People&Blogs, 27=Education)")
    parser.add_argument("--made-for-kids",  action="store_true",
                        help="Mark videos as Made for Kids (disables comments/personalization)")
    parser.add_argument("--publish-slot", choices=["video", "short"],
                        help="Schedule public uploads: video M/W/F 5 PM, short 7 PM Eastern")
    parser.add_argument("--thumbnail",      default=None,
                        help="Path to a custom thumbnail image (JPEG/PNG)")
    parser.add_argument("--update",         metavar="VIDEO_ID",
                        help="Update metadata of an existing video instead of uploading")
    parser.add_argument("--dry-run",        action="store_true",
                        help="Generate metadata only, do NOT upload or update")
    return parser.parse_args()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("=" * 60)
    print("  🚀  YouTube Auto-Upload  |  Local LLM / Gemini")
    print("=" * 60)

    # ── UPDATE MODE ──────────────────────────────────────────────────────────
    if args.update:
        print(f"\n🔄  UPDATE MODE — Video ID: {args.update}")
        print("-" * 40)

        metadata = generate_metadata_with_gemini(
            video_topic=args.topic,
            niche=args.niche,
            tone=args.tone,
        )

        if args.dry_run:
            print("\n⚠️   DRY RUN — skipping update.")
            print(f"\nWould update: https://www.youtube.com/watch?v={args.update}")
            print(f"Title: {metadata['title']}")
            print(f"Tags : {', '.join(metadata['tags'][:5])}...")
            print("\n🎉  Dry run complete!")
            print("=" * 60)
            return

        youtube = get_youtube_service()
        try:
            update_video(
                youtube=youtube,
                video_id=args.update,
                metadata=metadata,
                category_id=args.category,
            )
        except HttpError as e:
            if e.resp.status == 403:
                print("\n⚠️   403 Forbidden — your token may be missing the 'youtube' scope.")
                print("    Fix: delete youtube_token.json and re-run to re-authenticate.")
            else:
                raise
        print("\n🎉  Update complete!")
        print("=" * 60)
        return

    # ── UPLOAD MODE ───────────────────────────────────────────────────────────
    if not args.path:
        print("❌  Provide a video path/directory, or use --update VIDEO_ID to update metadata.")
        sys.exit(1)

    video_files = []
    if os.path.isfile(args.path):
        video_files.append(args.path)
    elif not os.path.exists(args.path):
        # Don't auto-create if it looks like a file (e.g. ends in .mp4)
        if args.path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
            print(f"❌  Video file not found: {args.path}")
            sys.exit(1)
        os.makedirs(args.path, exist_ok=True)
        print(f"📂  Auto-created missing directory: {args.path}")
        video_files = []
    elif os.path.isdir(args.path):
        extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm')
        video_files = [
            os.path.join(args.path, f) for f in os.listdir(args.path)
            if f.lower().endswith(extensions)
        ]
        video_files.sort()
        print(f"📂  Found {len(video_files)} videos in directory: {args.path}")
    else:
        print(f"❌  Path not found: {args.path}")
        sys.exit(1)

    if not video_files:
        print("Empty directory or no supported video files found.")
        return

    youtube = None
    if not args.dry_run:
        youtube = get_youtube_service()

    for i, video_path in enumerate(video_files, 1):
        filename = os.path.basename(video_path)
        print(f"\n[{i}/{len(video_files)}] Processing: {filename}")
        print("-" * 40)

        topic_context = args.topic
        if args.topic == "General":
            topic_context = f"General (Filename context: {filename})"

        metadata = generate_metadata_with_gemini(
            video_topic=topic_context,
            niche=args.niche,
            tone=args.tone,
        )
        
        if metadata is None:
            metadata = generate_metadata_fallback(
                video_topic=topic_context,
                niche=args.niche,
                tone=args.tone,
            )

        credits_path = os.path.splitext(video_path)[0] + "_visuals.json"
        if os.path.exists(credits_path):
            with open(credits_path, encoding="utf-8") as fh:
                assets = json.load(fh)
            credits = [f"{a.get('title', '')} — {a.get('author', '')} ({a.get('license', '')})\n{a.get('source_url', '')}\n{a.get('license_url', '')}" for a in assets]
            if credits:
                credit_text = "\n\nImage sources and licenses (images resized for video):\n" + "\n\n".join(credits)
                if len(credit_text) > 4500:
                    raise ValueError("Too many image credits for one YouTube description; review the visual manifest")
                metadata['description'] = metadata['description'][:5000-len(credit_text)] + credit_text

        meta_path = os.path.splitext(video_path)[0] + "_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"\n💾  Metadata saved to: {meta_path}")

        if args.dry_run:
            print("\n⚠️   DRY RUN — skipping upload.")
            print("\nFull Description Preview:\n")
            print(metadata["description"][:200] + "...")
            continue

        try:
            upload_video(
                youtube=youtube,
                video_path=video_path,
                metadata=metadata,
                category_id=args.category,
                privacy=args.privacy,
                made_for_kids=args.made_for_kids,
                thumbnail_path=args.thumbnail,
                publish_at=(next_publish_time(args.publish_slot)
                            if args.publish_slot and args.privacy == 'public' else None),
            )
            # Ping Google Search Console after successful upload
            ping_google_sitemap()
        except Exception as e:
            print(f"❌  Failed to upload {filename}: {e}")

    print("\n🎉  All tasks complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()