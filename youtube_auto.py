#!/usr/bin/env python3
"""
YouTube Auto-Upload Script with AI-Generated Descriptions & Hashtags
Uses Gemini API to generate compelling titles, descriptions, and hashtags.
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
from google import genai
import httplib2

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

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
    Use Gemini API to generate a YouTube title, description, and hashtags.
    Returns a dict: { title, description, tags }
    """
    if not GEMINI_API_KEY:
        print("❌  GEMINI_API_KEY is not set. Export it or paste it in the script.")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    
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
- Title: No clickbait, accurate, keyword-rich
- Description: Conversational yet professional, must include 5 hashtags at the end like #Tag
- Tags: Mix of broad and niche keywords, all lowercase, no # symbol in tags array"""

    print("\n🤖  Generating metadata with Gemini AI...")
    
    max_retries = 4
    retry_delay = 10  # Initial delay in seconds
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            raw = response.text.strip()
            break  # Success!
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print(f"  ⚠️   Gemini Quota Exceeded (429). Waiting 65s to reset...")
                time.sleep(65)
            elif attempt < max_retries - 1:
                print(f"  ⚠️   Gemini API busy (attempt {attempt+1}/{max_retries}): {e}")
                print(f"      Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"  ⚠️   Gemini API failed after {max_retries} attempts. Falling back to local JSON data...")
                return None

    # Strip markdown fences if present
    if raw.startswith("```"):
        # Split and handle cases where it might be ```json or just ```
        parts = raw.split("```")
        if len(parts) >= 3:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    raw = raw.strip()

    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌  Error parsing JSON from Gemini: {e}")
        print(f"Raw response: {raw}")
        return None

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
            "title": f"All About {clean_topic} | {niche} Learning",
            "description": description,
            "tags": [clean_topic.lower(), niche.lower(), "learning", "education", "facts"]
        }
    
    print(f"  ⚠️   No local JSON found for '{clean_topic}'. Using basic metadata.")
    return {
        "title": f"{clean_topic} - {niche} Education",
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


def upload_video(youtube, video_path: str, metadata: dict,
                 category_id: str = "22", privacy: str = "public",
                 made_for_kids: bool = False) -> str:
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
    parser.add_argument("--update",         metavar="VIDEO_ID",
                        help="Update metadata of an existing video instead of uploading")
    parser.add_argument("--dry-run",        action="store_true",
                        help="Generate metadata only, do NOT upload or update")
    return parser.parse_args()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    print("=" * 60)
    print("  🚀  YouTube Auto-Upload  |  Powered by Gemini AI")
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
            )
        except Exception as e:
            print(f"❌  Failed to upload {filename}: {e}")

    print("\n🎉  All tasks complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()