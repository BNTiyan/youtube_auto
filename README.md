# YouTube Auto — AI-Powered Video Creation & Upload

Fully automated YouTube channel system that **generates educational slideshow videos** with text-to-speech narration and **uploads them daily** using Gemini AI for SEO-optimized metadata.

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

Each pipeline:
1. Picks today's category via day-of-year rotation
2. Generates an MP4 slideshow with TTS narration (Pillow + gTTS + moviepy)
3. Generates SEO metadata (title, description, hashtags) via **Gemini AI**
4. Uploads directly to YouTube

### Manual trigger
Go to **Actions → Kids/Tech Learning — Daily Upload → Run workflow** in GitHub to trigger immediately and optionally override the category.

---

## Required GitHub Secrets

Set these in **GitHub → Settings → Secrets and variables → Actions**:

| Secret | Description | How to get |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key | [aistudio.google.com](https://aistudio.google.com) |
| `YOUTUBE_CLIENT_SECRETS_B64` | Base64-encoded `client_secrets.json` | See below |
| `YOUTUBE_TOKEN_KIDS_B64` | Base64-encoded `youtube_token.json` for kids channel | See below |
| `YOUTUBE_TOKEN_TECH_B64` | Base64-encoded `youtube_token.json` for tech channel | Same as above if same account |

### Encode credentials for secrets

```bash
# On macOS — copies to clipboard
base64 -i client_secrets.json | pbcopy   # paste as YOUTUBE_CLIENT_SECRETS_B64
base64 -i youtube_token.json  | pbcopy   # paste as YOUTUBE_TOKEN_KIDS_B64 and YOUTUBE_TOKEN_TECH_B64
```

### Get credentials (one-time setup)
1. [Google Cloud Console](https://console.cloud.google.com) → New Project → Enable **YouTube Data API v3**
2. Create **OAuth 2.0 credentials** (Desktop App) → Download as `client_secrets.json`
3. Run locally once to authenticate and generate `youtube_token.json`:
   ```bash
   python youtube_auto.py videos/any_video.mp4 --dry-run
   ```
4. Encode and set both files as secrets (see above)

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
├── video_creator.py                 ← Kids: colorful slideshow generator
├── tech_video_creator.py            ← Tech: dark professional slideshow generator
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
