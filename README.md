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
| GitHub Page Video Requests | Manual via GitHub Page + issue workflow | `.github/workflows/video_request_issue.yml` + `docs/index.html` |
| Vercel Video Request Portal | Manual via Vercel form + secure API | `public/index.html` + `api/video-request.js` |

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

### Quick local visual preview

```bash
python preview_video.py
python preview_video.py --style kids --output videos/kids_animated_preview.mp4
```

This renders a silent 16-second sample to `videos/animated_visual_preview.mp4`
using the tech slide renderer, without network access or publishing. Tech videos
now include text entrances, staggered point cards, an animated circuit diagram,
and a scene progress indicator, including when `--no-images` is used.

Kids videos use bright rounded cards, animated text, gently moving photos or a
friendly book illustration, and a progress indicator. These animations work
without stock images and apply to both single-item and category videos.

### Local LLM with Ollama

Install and start [Ollama](https://ollama.com), then pull a model:

```bash
ollama pull llama3.2:3b
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=llama3.2:3b
# Optional: OLLAMA_BASE_URL=http://localhost:11434 and LLM_TIMEOUT=300
```

The shared client uses Ollama's [JSON generation API](https://github.com/ollama/ollama/blob/main/docs/api.md).
Set these variables in the same terminal where you run the commands. Without
`LLM_PROVIDER`, Gemini is selected when `GEMINI_API_KEY` exists; otherwise Ollama
is selected. Explicit `LLM_PROVIDER=ollama` keeps LLM requests local even when a
Gemini key exists. Set `LLM_PROVIDER=gemini` to use the original cloud provider.

Generate a custom topic package, render it, and preview upload metadata:

```bash
python latest_topic_pipeline.py --source-topic "How local AI works" --source-text "Explain running language models on your own computer."
python tech_video_creator.py --config generated/latest_topic_package.json --output-dir preview_videos --no-images
python youtube_auto.py preview_videos/ --topic "How local AI works" --niche "Tech Education" --dry-run
```

After reviewing the video and metadata, publish it using your existing YouTube
OAuth credentials:

```bash
python youtube_auto.py preview_videos/ --topic "How local AI works" --niche "Tech Education" --category 28 --privacy private
```

Local LLM generation changes scripts/topics and upload metadata. The existing
Pillow/MoviePy renderer creates the visuals; narration still uses online
edge-tts/gTTS. YouTube publishing requires internet and channel credentials.
For scheduled use with your machine's Ollama, run the local scheduler on that
machine. GitHub-hosted Actions cannot reach your computer's localhost endpoint.

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

### Shareable request page
After enabling GitHub Pages for this repo, share:

```text
https://bntiyan.github.io/youtube_auto/
```

People can submit:
1. Topic
2. Source text
3. Optional notes
4. Privacy and dry-run preference

The page opens a structured GitHub issue, and the `video_request_issue.yml`
workflow picks it up and generates the requested video.

### Private repo option with Vercel
If you want to keep the GitHub repo private, deploy this repo to Vercel instead and use the built-in form/API:

Files:
- `public/index.html` — shareable request page
- `api/video-request.js` — secure serverless endpoint that triggers GitHub Actions
- `vercel.json` — Vercel config

Set these Vercel environment variables:
- `GITHUB_TOKEN` — GitHub token that can trigger Actions workflows in this repo
- `GITHUB_OWNER` — repo owner, for example `BNTiyan`
- `GITHUB_REPO` — repo name, for example `youtube_auto`
- `GITHUB_WORKFLOW_ID` — optional, default is `latest_topic_pipeline.yml`
- `GITHUB_REF` — optional branch, default is `main`
- `VIDEO_REQUEST_ACCESS_CODE` — optional shared code to protect the form

The Vercel form submits:
1. Topic
2. Source text
3. Optional notes
4. Channel (`navadisha` or `childishdreamer`)
5. Privacy
6. Language
7. Dry run

The backend triggers the existing `latest_topic_pipeline.yml` workflow in GitHub Actions.

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
├── docs/index.html                  ← GitHub Pages form for video requests
├── public/index.html                ← Vercel-hosted request form for private repo setup
├── api/video-request.js             ← Vercel serverless API to trigger GitHub workflow
├── vercel.json                      ← Vercel project config
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


## Mac self-hosted runner

The scheduled kids, tech, latest-topic, and manual uploader workflows target
`[self-hosted, macOS, ARM64, youtube-auto]`. They explicitly use local Ollama
with `qwen2.5:3b` at `http://127.0.0.1:11434`; Gemini keys do not override this.
The issue-triggered request workflow remains on GitHub-hosted Linux with its
existing Gemini configuration, so public issue events do not execute on the Mac.

The shared local runtime action uses uv to install Python 3.11 in a user-owned
temporary directory (without `/Users/runner` or administrator access), creates an isolated virtual
environment, supplies FFmpeg via imageio-ffmpeg, and checks that Ollama and the
configured model are available. Existing YouTube credential secrets are still
required for publishing and temporary credential files are removed after jobs.

On this Mac, the registered runner is `youtube-auto-mac-arm64`, installed at
`~/actions-runner-youtube-auto` with a per-user launchd service. It runs while
the screen is locked. Keep the Mac awake, connected, and Ollama running. After
restarting the Mac, sign in to your user account so its login services start.

Manage the service from Terminal:

```bash
cd ~/actions-runner-youtube-auto
./svc.sh status
./svc.sh stop
./svc.sh start
```

After pushing the repository changes, run **Actions → Local Mac Runner Check →
Run workflow**. It tests local script generation and renders kids and tech
previews as downloadable artifacts, without authenticating to or uploading to
YouTube. Then use the daily pipelines' dry-run option before publishing.

The repository is public: only trusted workflow code should target this personal
Mac runner. Do not add pull-request triggers that execute untrusted fork code.


Tech visuals default to locally drawn concept diagrams instead of first-result
stock photos. RAG, vector search, MCP, attention, databases, training, LLMs, and
agents have distinct labeled flows. Unrecognized topics use a labeled overview;
these diagrams are teaching templates, not diagrams inferred or verified by the
LLM. Tech Shorts use the same concept selection. To explicitly opt into Pexels
photos for landscape tech videos, set `TECH_STOCK_IMAGES=1`; review matches before
publishing. Kids photo selection is unchanged.
