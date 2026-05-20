# YouTube Auto — AI-Powered Video Creation & Upload

Fully automated YouTube channel system that **generates educational animated slideshow videos** with child-style text-to-speech narration and **uploads them daily** using Gemini AI for SEO-optimized metadata.

Two separate channels, two separate daily pipelines running on GitHub Actions.

---

## Channels

| Channel | Content | Category | Style |
|---|---|---|---|
| **Kids Learning** | Animals, Fruits, Vegetables, Cars, Airplanes, Brands | Education (27) | Bright, colorful slides |
| **Tech Learning** | AI, LLM, RAG, Database, MCP | Science & Tech (28) | Dark professional slides |

---

## GitHub Actions Pipelines

| Workflow | Schedule | File |
|---|---|---|
| Kids Learning — Daily Upload | **9:00 AM EST** every day | `.github/workflows/kids_pipeline.yml` |
| Tech Learning — Daily Upload | **9:10 AM EST** every day | `.github/workflows/tech_pipeline.yml` |
| Latest Tech Topic — Daily Upload | **9:40 AM EST** every day | `.github/workflows/latest_topic_pipeline.yml` |

Each pipeline:
1. Picks today's category via day-of-year rotation
2. Generates an animated MP4 slideshow with child-style TTS narration (Pillow + edge-tts/gTTS + moviepy)
3. Generates SEO metadata (title, description, hashtags) via **Gemini AI**
4. Uploads directly to YouTube

The latest-topic pipeline differs slightly:
1. Fetches recent AI/tech headlines from Google News RSS
2. Uses Gemini AI to choose the best topic for today and turn it into a teachable explainer package
3. Generates one regular tech video plus one Short from that package
4. Uploads both to YouTube

### Manual trigger
Go to **Actions → Kids/Tech Learning — Daily Upload → Run workflow** in GitHub to trigger immediately and optionally override the category.

---

## Required GitHub Secrets

Set these in **GitHub → Settings → Secrets and variables → Actions**:

Both channels use **different Google accounts**, so each has its own `client_secrets.json` and `youtube_token.json`.

| Secret | Channel | Description |
|---|---|---|
| `GEMINI_API_KEY` | Shared | Gemini API key from [aistudio.google.com](https://aistudio.google.com) |
| `PEXELS_API_KEY` | Shared | Free image API key from [pexels.com/api](https://www.pexels.com/api/) |
| `YOUTUBE_CLIENT_SECRETS_KIDS_B64` | Kids | Base64 of `client_secrets.json` for the Kids Google account |
| `YOUTUBE_TOKEN_KIDS_B64` | Kids | Base64 of `youtube_token.json` for the Kids Google account |
| `YOUTUBE_CLIENT_SECRETS_TECH_B64` | Tech | Base64 of `client_secrets.json` for the Tech Google account |
| `YOUTUBE_TOKEN_TECH_B64` | Tech | Base64 of `youtube_token.json` for the Tech Google account |

### Encode credentials for secrets

Do this separately for **each Google account**:

```bash
# ── Kids channel account ──────────────────────────────────────────
# 1. Download client_secrets.json for the Kids Google Cloud project
# 2. Authenticate locally to get youtube_token.json for the Kids account:
python youtube_auto.py videos/any.mp4 --dry-run   # opens browser → sign in with Kids account
# 3. Encode both files:
base64 -i client_secrets.json | pbcopy   # → paste as YOUTUBE_CLIENT_SECRETS_KIDS_B64
base64 -i youtube_token.json  | pbcopy   # → paste as YOUTUBE_TOKEN_KIDS_B64

# ── Tech channel account ──────────────────────────────────────────
# 1. Download client_secrets.json for the Tech Google Cloud project
# 2. Rename your existing files so they don't overwrite:
mv client_secrets.json client_secrets_kids_backup.json
mv youtube_token.json  youtube_token_kids_backup.json
# 3. Place the Tech client_secrets.json and authenticate:
python youtube_auto.py videos/any.mp4 --dry-run   # opens browser → sign in with Tech account
# 4. Encode:
base64 -i client_secrets.json | pbcopy   # → paste as YOUTUBE_CLIENT_SECRETS_TECH_B64
base64 -i youtube_token.json  | pbcopy   # → paste as YOUTUBE_TOKEN_TECH_B64
# 5. Restore Kids credentials:
mv client_secrets_kids_backup.json client_secrets.json
mv youtube_token_kids_backup.json  youtube_token.json
```

### Get credentials per account (one-time setup)
1. [Google Cloud Console](https://console.cloud.google.com) → Create **one project per channel** → Enable **YouTube Data API v3** in each
2. Create **OAuth 2.0 credentials** (Desktop App) → Download as `client_secrets.json`
3. Run locally with that account's `client_secrets.json` to generate `youtube_token.json`
4. Encode and add both files as the channel-specific secrets above

---

## Local Development

### Prerequisites
```bash
brew install ffmpeg          # macOS
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"
```

### Generate kids' learning videos
```bash
python video_creator.py all                  # all 6 categories
python video_creator.py animals              # single category
python video_creator.py fruits --items 5     # first 5 items only
```

### Generate tech learning videos
```bash
python tech_video_creator.py all             # ai, llm, rag, database, mcp
python tech_video_creator.py llm             # single category
```

### Generate today's latest-topic package
```bash
python latest_topic_pipeline.py --source-topic "OpenAI launched a new coding feature" --source-notes "Saw this idea on Instagram today"
python latest_topic_pipeline.py
python latest_topic_pipeline.py --source-url "https://example.com/feed-or-profile"
export LATEST_TOPIC_SOURCE_URL="https://example.com/feed-or-profile"
bash run_latest_pipeline.sh
```

### Upload manually
```bash
# Upload a folder
python youtube_auto.py videos/ \
  --niche "Kids Education" \
  --tone "fun and educational for children" \
  --category 27 --made-for-kids

# Update existing video metadata
python youtube_auto.py \
  --update VIDEO_ID \
  --topic "Animals for Kids" \
  --niche "Kids Education" \
  --category 27
```

### Scheduler (local fallback)
```bash
python scheduler.py --status                 # show queue for both channels
python scheduler.py --run-now --dry-run      # preview without uploading
python scheduler.py --run-now                # upload now
python scheduler.py --run-now --channel "Tech Learning"
```

---

## Project Structure

```
youtube_auto/
├── .github/
│   └── workflows/
│       ├── kids_pipeline.yml        ← GitHub Actions: Kids channel (9:00 AM EST)
│       └── tech_pipeline.yml        ← GitHub Actions: Tech channel (9:10 AM EST)
│
├── youtube_auto.py                  ← Core: upload + update via YouTube API + Gemini
├── video_creator.py                 ← Kids: colorful animated slideshow generator
├── tech_video_creator.py            ← Tech: dark professional animated slideshow generator
├── animation_utils.py               ← Shared slide zoom/pan/fade helpers
├── latest_topic_pipeline.py         ← Fetches today's headlines and builds a tech explainer package
├── scheduler.py                     ← Local: daily upload scheduler with state tracking
│
├── content_config.json              ← Kids content: 6 categories × 10 items
├── tech_content_config.json         ← Tech content: 5 categories × 10 concepts
├── scheduler_config.json            ← Scheduler settings for both channels
│
├── videos/                          ← Generated kids MP4s (gitignored)
├── tech_videos/                     ← Generated tech MP4s (gitignored)
├── logs/                            ← Pipeline logs + upload state (gitignored)
│
├── run_kids_pipeline.sh             ← Local manual run (kids)
├── run_tech_pipeline.sh             ← Local manual run (tech)
├── run_latest_pipeline.sh           ← Local manual run (latest daily topic)
└── requirements.txt
```

---

## Expanding Content

Edit the JSON configs to add more videos to the queue:

```jsonc
// content_config.json  — add new categories or items
{
  "space": {                              // ← new category
    "items": [
      {"name": "Black Hole", "fact": "A black hole is a region of space where gravity is so strong that nothing can escape"},
      ...
    ]
  }
}
```

Then add the category to the rotation in `.github/workflows/kids_pipeline.yml`:
```bash
CATEGORIES=(animals fruits vegetables cars airplanes brands space)
```

---

## YouTube Quota

YouTube Data API v3 quota: **10,000 units/day** (free).
Each video upload costs **1,600 units** → safe limit is **6 uploads/day** across all channels.

The two pipelines upload **1 video/day each = 3,200 units/day**, well within the limit.

To request higher quota: [Google Cloud Console → APIs → YouTube Data API v3 → Quotas](https://console.cloud.google.com)
