#!/usr/bin/env python3
"""
Tech Learning Video Creator
Generates professional educational videos for AI/LLM/RAG/Database/MCP topics.
Each slide shows a real Pexels photo on the left half and concept text on the right.

Set PEXELS_API_KEY environment variable to enable images.
Falls back to text-only dark slides when key is absent.

Usage:
    python tech_video_creator.py ai
    python tech_video_creator.py all
    python tech_video_creator.py llm --items 5
    python tech_video_creator.py all --no-images
"""

import os
import json
import argparse
import textwrap
import tempfile
import random
import glob
from io import BytesIO
from typing import Optional

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

# ── moviepy v1 / v2 compat ────────────────────────────────────────────────────
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
except (ImportError, ModuleNotFoundError):
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips


def _set_audio(clip, audio):
    try:
        return clip.set_audio(audio)
    except AttributeError:
        return clip.with_audio(audio)


# ── VIDEO SETTINGS ────────────────────────────────────────────────────────────
WIDTH, HEIGHT      = 1280, 720
FPS                = 24
PAUSE_AFTER_AUDIO  = 1.0
MIN_SLIDE_DURATION = 5.0

# Split-screen: left = text panel, right = photo
TEXT_W = 640       # left half width
PHOTO_W = 640      # right half width
BADGE_H = 70       # top badge bar height

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# Pexels search queries per tech item name
TECH_IMAGE_QUERIES: dict = {
    # AI
    "Artificial Intelligence": "artificial intelligence robot futuristic",
    "Machine Learning":        "data science machine learning graph",
    "Neural Networks":         "brain neural connections network",
    "Deep Learning":           "deep learning artificial intelligence",
    "Computer Vision":         "computer vision camera technology",
    "NLP":                     "natural language processing text technology",
    "Reinforcement Learning":  "robot learning training technology",
    "Generative AI":           "generative ai creative art technology",
    "Transfer Learning":       "knowledge transfer education technology",
    "AI Agents":               "autonomous robot agent technology",
    # LLM
    "Large Language Model":    "language AI chatbot interface",
    "Transformer":             "transformer architecture circuit board",
    "Tokens":                  "text tokenization word letters",
    "Context Window":          "computer memory processing data",
    "Prompt Engineering":      "prompt writing AI interface",
    "Fine-tuning":             "optimization training machine learning",
    "Embeddings":              "vector space mathematics abstract",
    "Hallucination":           "confusion brain glitch technology",
    "Temperature":             "control settings dashboard technology",
    "System Prompt":           "system interface programming code",
    # RAG
    "RAG":                     "search retrieval database knowledge",
    "Vector Database":         "database search server technology",
    "Chunking":                "document text processing data",
    "Semantic Search":         "search meaning technology interface",
    "Re-ranking":              "ranking sorting list technology",
    "Knowledge Base":          "knowledge library documents data",
    "Document Loader":         "document loading server processing",
    "Query Expansion":         "search query interface technology",
    "Hybrid Search":           "hybrid search technology interface",
    "Context Window RAG":      "context memory AI data",
    # Database
    "SQL":                     "sql database query code programming",
    "NoSQL":                   "nosql database server technology",
    "PostgreSQL":              "postgresql database server",
    "MongoDB":                 "mongodb database documents server",
    "Redis":                   "redis cache server memory",
    "Vector DB":               "vector database AI server",
    "ACID":                    "database reliability server technology",
    "Indexing":                "database index search optimization",
    "Graph Database":          "graph network nodes connections",
    "Sharding":                "distributed server database technology",
    # AI (extended)
    "Supervised Learning":     "teacher student learning classroom",
    "Unsupervised Learning":   "data clustering abstract patterns",
    "Semi-supervised Learning":"data science analysis chart",
    "Self-supervised Learning":"robot self training learning",
    "Federated Learning":      "distributed network privacy data",
    "Active Learning":         "human loop labeling data annotation",
    "Few-shot Learning":       "small data examples learning AI",
    "Zero-shot Learning":      "AI generalization knowledge transfer",
    "One-shot Learning":       "single example face recognition",
    "Meta-learning":           "learning to learn AI optimization",
    "Explainable AI":          "transparent AI explanation dashboard",
    "AI Safety":               "safety shield protection technology",
    "AI Alignment":            "AI human values alignment ethics",
    "AI Ethics":               "ethics fairness AI society",
    "Bias in AI":              "bias fairness scale balance data",
    "AI Fairness":             "fairness equality technology AI",
    "Robustness":              "shield protection robust technology",
    "Adversarial Examples":    "attack glitch image adversarial",
    "Model Interpretability":  "transparent glass model explanation",
    "Feature Engineering":     "data science feature analysis chart",
    "Overfitting":             "fitting curve data graph overfitting",
    "Underfitting":            "simple model data graph chart",
    "Regularization":          "constraint optimization mathematics",
    "Cross-validation":        "validation testing data split science",
    "Hyperparameter Tuning":   "optimization tuning knobs settings",
    "Gradient Descent":        "mountain slope descent optimization graph",
    "Backpropagation":         "neural network backward signal circuit",
    "Epoch":                   "training cycle loop data iteration",
    "Batch Size":              "data batch group processing server",
    "Learning Rate":           "speed optimization learning rate graph",
    "Dropout":                 "neural network regularization circuit",
    "Attention Mechanism":     "focus attention spotlight AI",
    "Convolutional Neural Net":"image recognition layers neural",
    "Recurrent Neural Net":    "sequence time series neural network",
    "LSTM":                    "memory cell sequence learning neural",
    "GAN":                     "generative adversarial network art",
    "Diffusion Model":         "image generation art diffusion noise",
    "Variational Autoencoder": "encoder decoder latent space AI",
    "Encoder-Decoder":         "encoder decoder architecture AI",
    "Object Detection":        "object detection bounding box camera",
    "Image Segmentation":      "image segmentation mask pixel",
    "Speech Recognition":      "speech microphone voice recognition",
    "Text-to-Speech":          "text voice speaker audio",
    "Sentiment Analysis":      "emotion sentiment happy sad text",
    "Named Entity Recognition":"text entity highlight recognition",
    "Text Classification":     "text label classification document",
    "Recommendation System":   "recommendation engine Netflix shopping",
    "Anomaly Detection":       "anomaly alert warning detection",
    "Time Series Forecasting": "time series chart forecast prediction",
    "Clustering":              "data clustering groups visualization",
    "Principal Component Analysis":"data dimensionality reduction chart",
    "Random Forest":           "forest trees decision ensemble",
    "Support Vector Machine":  "classification boundary data science",
    "Decision Tree":           "decision tree branch flowchart",
    "Naive Bayes":             "probability statistics bayesian",
    "K-Nearest Neighbors":     "nearest neighbor points data chart",
    "Logistic Regression":     "classification sigmoid curve chart",
    "Linear Regression":       "statistics graph line chart data science",
    "Ensemble Learning":       "team ensemble models combination",
    "Boosting":                "boost performance optimization chart",
    "Bagging":                 "sampling bootstrap data bags",
    "Stacking":                "stack layers models ensemble",
    "Confusion Matrix":        "matrix table classification results",
    "Precision and Recall":    "precision recall metrics evaluation",
    "F1 Score":                "score metric evaluation chart",
    "ROC Curve":               "roc curve chart classification",
    "AUC":                     "area curve chart classification metric",
    "Mean Squared Error":      "error loss function graph chart",
    "Cross-entropy Loss":      "loss function neural network training",
    "Reward Function":         "reward signal robot training",
    "Policy Gradient":         "policy optimization reinforcement",
    "Q-Learning":              "Q table reinforcement learning game",
    "Multi-agent Systems":     "multiple agents robots cooperation",
    "Symbolic AI":             "logic symbols rules AI",
    "Neuro-symbolic AI":       "neural symbolic hybrid AI",
    "Causal Inference":        "cause effect arrows diagram",
    "AutoML":                  "automated machine learning pipeline",
    "Neural Architecture Search":"architecture design neural network",
    "Knowledge Graph":         "knowledge graph nodes edges network",
    "Ontology":                "ontology concepts hierarchy diagram",
    "Data Augmentation":       "data augmentation image transformation",
    "Synthetic Data":          "synthetic data generation AI",
    "Model Compression":       "compression small model efficient",
    "Quantization":            "quantization bits precision model",
    "Pruning":                 "pruning cutting branches tree model",
    "Knowledge Distillation":  "teacher student knowledge transfer",
    "Edge AI":                 "edge device mobile AI chip",
    "Multimodal AI":           "multimodal image text audio AI",
    "World Model":             "world simulation model AI",
    "AI Benchmark":            "benchmark test score evaluation",
    # MCP
    "MCP":                     "protocol connection API network",
    "MCP Server":              "server API connection technology",
    "MCP Client":              "client connection software interface",
    "Tools":                   "AI tools software integration",
    "Resources":               "database resources files server",
    "Prompts":                 "text prompt interface AI",
    "Sampling":                "sampling probability data statistics",
    "Transport":               "network transport protocol connection",
    "Claude Desktop":          "AI assistant desktop application",
    "MCP SDK":                 "software development programming code",
}

# ── DARK PROFESSIONAL THEMES ──────────────────────────────────────────────────
TECH_THEMES = {
    "ai": {
        "bg":     (8,  10, 25),   "card":   (14, 20, 50),
        "accent": (96, 165, 250), "text":   (255, 255, 255),
        "grid":   (18, 25, 58),   "muted":  (170, 195, 235),
        "badge":  "🤖  Artificial Intelligence",
    },
    "llm": {
        "bg":     (12,  8, 28),   "card":   (22, 16, 56),
        "accent": (167, 139, 250),"text":   (255, 255, 255),
        "grid":   (28, 20, 65),   "muted":  (200, 185, 240),
        "badge":  "💬  Large Language Models",
    },
    "rag": {
        "bg":     (8,  22, 20),   "card":   (14, 44, 40),
        "accent": (52, 211, 153), "text":   (255, 255, 255),
        "grid":   (18, 52, 48),   "muted":  (150, 220, 200),
        "badge":  "🔍  Retrieval Augmented Generation",
    },
    "database": {
        "bg":     (25, 12,  5),   "card":   (50, 24, 10),
        "accent": (251, 146, 60), "text":   (255, 255, 255),
        "grid":   (60, 30, 14),   "muted":  (235, 185, 140),
        "badge":  "🗄️   Database Systems",
    },
    "mcp": {
        "bg":     (5,  25, 14),   "card":   (10, 50, 28),
        "accent": (74, 222, 128), "text":   (255, 255, 255),
        "grid":   (12, 58, 34),   "muted":  (155, 230, 185),
        "badge":  "🔌  Model Context Protocol",
    },
}
DEFAULT_TECH_THEME = {
    "bg": (12, 12, 12), "card": (24, 24, 24), "accent": (200, 200, 200),
    "text": (255, 255, 255), "grid": (28, 28, 28), "muted": (180, 180, 180),
    "badge": "📖  Tech Learning",
}

# ── FONTS ─────────────────────────────────────────────────────────────────────
_FONT_CACHE: dict = {}
_FONT_PATHS = [
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/mnt/c/Windows/Fonts/arialbd.ttf",
    "/mnt/c/Windows/Fonts/arial.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def fit_text_font(draw, text: str, max_width: int, max_size: int = 72) -> ImageFont.FreeTypeFont:
    for size in range(max_size, 24, -4):
        f = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=f)
        if (bbox[2] - bbox[0]) < max_width:
            return f
    return load_font(24)


def draw_centered_in(draw, text: str, font, y: int, x_start: int, x_end: int, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = x_start + (x_end - x_start - tw) // 2
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0))  # shadow
    draw.text((x, y), text, font=font, fill=fill)


# ── PEXELS IMAGE FETCH ────────────────────────────────────────────────────────
_img_cache: dict = {}


def fetch_pexels_image(query: str) -> Optional[Image.Image]:
    if not PEXELS_API_KEY:
        return None
    if query in _img_cache:
        return _img_cache[query]

    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=10,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            resp2 = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": query, "per_page": 3},
                timeout=10,
            )
            resp2.raise_for_status()
            photos = resp2.json().get("photos", [])
        if not photos:
            _img_cache[query] = None
            return None

        src = photos[0]["src"]
        url = src.get("large2x") or src.get("large")
        img_resp = requests.get(url, timeout=15)
        img_resp.raise_for_status()
        img = Image.open(BytesIO(img_resp.content)).convert("RGB")
        _img_cache[query] = img
        return img

    except Exception as e:
        print(f"    ⚠️   Pexels fetch failed ({query}): {e}")
        _img_cache[query] = None
        return None


def get_tech_image(term: str) -> Optional[Image.Image]:
    query = TECH_IMAGE_QUERIES.get(term)
    if query:
        return fetch_pexels_image(query)
    # For unmapped terms, try the term itself first, then fall back to "technology data science"
    img = fetch_pexels_image(term)
    if img:
        return img
    return fetch_pexels_image("technology data science code")



# ── SLIDE CREATION ────────────────────────────────────────────────────────────

def _draw_grid(draw, theme: dict):
    for x in range(0, WIDTH, 48):
        for y in range(0, HEIGHT, 48):
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=theme["grid"])


def _darken_image(img: Image.Image, factor: float = 0.55) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    arr = np.clip(arr * factor, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def _gradient_bg(w: int, h: int, top_color, bot_color) -> np.ndarray:
    """Vertical gradient from top_color → bot_color."""
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for i, (tc, bc) in enumerate(zip(top_color, bot_color)):
        arr[:, :, i] = np.linspace(tc, bc, h).reshape(-1, 1)
    return np.clip(arr, 0, 255).astype(np.uint8)


def _accent_glow(arr: np.ndarray, accent, x: int, glow_w: int = 18):
    """Paint a glowing accent strip at column x (fades right)."""
    ac = np.array(accent, dtype=np.float32)
    for dx in range(glow_w):
        alpha = (1 - dx / glow_w) ** 2
        col = x + dx
        if col < arr.shape[1]:
            arr[:, col] = np.clip(arr[:, col] * (1 - alpha) + ac * alpha, 0, 255)


def create_tech_slide(
    term: str,
    explanation: str,
    theme: dict,
    counter: str = "",
    image: Optional[Image.Image] = None,
) -> np.ndarray:

    # ── Gradient base ─────────────────────────────────────────────────────────
    bg_top = tuple(min(c + 12, 255) for c in theme["bg"])
    bg_arr = _gradient_bg(WIDTH, HEIGHT, bg_top, theme["bg"])
    base = Image.fromarray(bg_arr)
    draw = ImageDraw.Draw(base)

    if image is not None:
        # ══ SPLIT-SCREEN: left = text panel, right = darkened photo ══════════
        CONTENT_Y = BADGE_H

        photo_h = HEIGHT - CONTENT_Y
        img_w, img_h = image.size
        scale = max(PHOTO_W / img_w, photo_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)
        scaled = image.resize((nw, nh), Image.LANCZOS)
        left = (nw - PHOTO_W) // 2
        top  = (nh - photo_h) // 2
        cropped = scaled.crop((left, top, left + PHOTO_W, top + photo_h))

        darkened = _darken_image(cropped, factor=0.50)
        base.paste(darkened, (TEXT_W, CONTENT_Y))

        # Blend photo edge into card
        arr = np.array(base, dtype=np.float32)
        bg_c = np.array(theme["card"], dtype=np.float32)
        blend_w = 100
        for x in range(blend_w):
            alpha = (1 - x / blend_w) ** 1.5
            arr[CONTENT_Y:, TEXT_W + x] = (
                arr[CONTENT_Y:, TEXT_W + x] * (1 - alpha) + bg_c * alpha
            )
        base = Image.fromarray(arr.astype(np.uint8))
        draw = ImageDraw.Draw(base)

        # Card gradient on left panel
        card_arr = _gradient_bg(TEXT_W, HEIGHT - CONTENT_Y,
                                 tuple(min(c + 8, 255) for c in theme["card"]),
                                 theme["card"])
        base.paste(Image.fromarray(card_arr), (0, CONTENT_Y))
        draw = ImageDraw.Draw(base)

    else:
        _draw_grid(draw, theme)
        card_arr = _gradient_bg(WIDTH, HEIGHT - BADGE_H,
                                 tuple(min(c + 10, 255) for c in theme["card"]),
                                 theme["card"])
        base.paste(Image.fromarray(card_arr), (0, BADGE_H))
        draw = ImageDraw.Draw(base)

    # ── Top badge bar ──────────────────────────────────────────────────────────
    badge_arr = _gradient_bg(WIDTH, BADGE_H,
                              tuple(min(c + 6, 255) for c in theme["bg"]),
                              theme["bg"])
    base.paste(Image.fromarray(badge_arr), (0, 0))
    draw = ImageDraw.Draw(base)
    draw.line([(0, BADGE_H - 1), (WIDTH, BADGE_H - 1)], fill=theme["accent"], width=3)
    draw.text((38, 20), theme["badge"], font=load_font(30), fill=theme["accent"])

    if counter:
        cf = load_font(26)
        bbox = draw.textbbox((0, 0), counter, font=cf)
        draw.text((WIDTH - (bbox[2] - bbox[0]) - 30, 22),
                  counter, font=cf, fill=theme["muted"])

    # ── Glowing accent strip ───────────────────────────────────────────────────
    arr = np.array(base, dtype=np.float32)
    _accent_glow(arr, theme["accent"], x=0, glow_w=20)
    base = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(base)

    # ── Term name ─────────────────────────────────────────────────────────────
    x_pad = 36
    text_x_start = 20 + x_pad
    text_x_end   = TEXT_W - x_pad if image else WIDTH - x_pad
    term_font = fit_text_font(draw, term, text_x_end - text_x_start, max_size=68)
    term_y    = BADGE_H + (HEIGHT - BADGE_H) // 2 - 120
    # Shadow
    draw.text((text_x_start + 3, term_y + 3), term, font=term_font, fill=(0, 0, 0))
    draw_centered_in(draw, term, term_font, term_y, text_x_start, text_x_end, theme["text"])

    # ── Accent divider with dots ───────────────────────────────────────────────
    div_y = BADGE_H + (HEIGHT - BADGE_H) // 2 - 10
    draw.line([(text_x_start, div_y), (text_x_end, div_y)], fill=theme["accent"], width=2)
    for dot_x in range(text_x_start, text_x_end, 20):
        draw.ellipse([dot_x - 2, div_y - 2, dot_x + 2, div_y + 2], fill=theme["accent"])

    # ── Explanation ───────────────────────────────────────────────────────────
    exp_font = load_font(33)
    max_exp_w = 30 if image else 54
    wrapped = textwrap.wrap(explanation, width=max_exp_w)
    y_pos = div_y + 22
    for line in wrapped[:3]:
        bbox = draw.textbbox((0, 0), line, font=exp_font)
        tw = bbox[2] - bbox[0]
        x  = text_x_start + (text_x_end - text_x_start - tw) // 2
        draw.text((x + 1, y_pos + 1), line, font=exp_font, fill=(0, 0, 0))
        draw.text((x, y_pos), line, font=exp_font, fill=theme["muted"])
        y_pos += 52

    # ── Bottom watermark ──────────────────────────────────────────────────────
    wm = "NavaDisha Tech Learning"
    wm_font = load_font(20)
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    draw.text(((text_x_start + text_x_end - (bbox[2] - bbox[0])) // 2, HEIGHT - 30),
              wm, font=wm_font, fill=theme["grid"])

    return np.array(base)


def create_points_slide(
    term: str,
    points: list,
    theme: dict,
    image: Optional[Image.Image] = None,
) -> np.ndarray:
    """Creative bullet-point slide showing key facts about a concept."""

    bg_top = tuple(min(c + 12, 255) for c in theme["bg"])
    bg_arr = _gradient_bg(WIDTH, HEIGHT, bg_top, theme["bg"])
    base = Image.fromarray(bg_arr)
    draw = ImageDraw.Draw(base)

    if image is not None:
        CONTENT_Y = BADGE_H
        photo_h = HEIGHT - CONTENT_Y
        img_w, img_h = image.size
        scale = max(PHOTO_W / img_w, photo_h / img_h)
        nw, nh = int(img_w * scale), int(img_h * scale)
        scaled = image.resize((nw, nh), Image.LANCZOS)
        left = (nw - PHOTO_W) // 2
        top  = (nh - photo_h) // 2
        cropped = scaled.crop((left, top, left + PHOTO_W, top + photo_h))
        darkened = _darken_image(cropped, factor=0.45)
        base.paste(darkened, (TEXT_W, CONTENT_Y))

        arr = np.array(base, dtype=np.float32)
        bg_c = np.array(theme["card"], dtype=np.float32)
        for x in range(100):
            alpha = (1 - x / 100) ** 1.5
            arr[CONTENT_Y:, TEXT_W + x] = arr[CONTENT_Y:, TEXT_W + x] * (1 - alpha) + bg_c * alpha
        base = Image.fromarray(arr.astype(np.uint8))

        card_arr = _gradient_bg(TEXT_W, HEIGHT - CONTENT_Y,
                                 tuple(min(c + 8, 255) for c in theme["card"]),
                                 theme["card"])
        base.paste(Image.fromarray(card_arr), (0, CONTENT_Y))
    else:
        _draw_grid(draw, theme)
        card_arr = _gradient_bg(WIDTH, HEIGHT - BADGE_H,
                                 tuple(min(c + 10, 255) for c in theme["card"]),
                                 theme["card"])
        base.paste(Image.fromarray(card_arr), (0, BADGE_H))

    draw = ImageDraw.Draw(base)

    # Badge bar
    badge_arr = _gradient_bg(WIDTH, BADGE_H,
                              tuple(min(c + 6, 255) for c in theme["bg"]),
                              theme["bg"])
    base.paste(Image.fromarray(badge_arr), (0, 0))
    draw = ImageDraw.Draw(base)
    draw.line([(0, BADGE_H - 1), (WIDTH, BADGE_H - 1)], fill=theme["accent"], width=3)
    draw.text((38, 20), theme["badge"], font=load_font(30), fill=theme["accent"])

    # Glowing strip
    arr = np.array(base, dtype=np.float32)
    _accent_glow(arr, theme["accent"], x=0, glow_w=20)
    base = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(base)

    x_pad = 36
    text_x_start = 20 + x_pad
    text_x_end   = TEXT_W - x_pad if image else WIDTH - x_pad
    panel_w = text_x_end - text_x_start

    # "Key Points" header
    header_font = fit_text_font(draw, term, panel_w, max_size=52)
    header_y = BADGE_H + 22
    draw.text((text_x_start + 2, header_y + 2), term, font=header_font, fill=(0, 0, 0))
    draw_centered_in(draw, term, header_font, header_y, text_x_start, text_x_end, theme["text"])

    # Accent underline
    uh = header_y + 62
    draw.line([(text_x_start, uh), (text_x_end, uh)], fill=theme["accent"], width=2)
    draw.text((text_x_start, uh + 8), "Key Points", font=load_font(26), fill=theme["accent"])

    # Bullet point rows
    bullet_font  = load_font(28)
    marker_font  = load_font(30)
    row_h        = 95
    row_start_y  = uh + 52
    use_points   = [p for p in points if p][:5]

    for i, point in enumerate(use_points):
        ry = row_start_y + i * row_h
        # Row background card
        row_bg = tuple(min(c + 18, 255) for c in theme["card"])
        draw.rectangle([text_x_start - 8, ry - 4,
                        text_x_end + 8, ry + row_h - 14], fill=row_bg)
        # Left accent bar for each row
        draw.rectangle([text_x_start - 8, ry - 4,
                        text_x_start - 4, ry + row_h - 14], fill=theme["accent"])
        # Bullet marker
        draw.text((text_x_start + 4, ry + 4), "▶", font=marker_font, fill=theme["accent"])
        # Point text (wrapped)
        max_chars = 38 if image else 60
        wrapped_pt = textwrap.wrap(point, width=max_chars)
        pt_y = ry + 6
        for line in wrapped_pt[:2]:
            draw.text((text_x_start + 38, pt_y), line, font=bullet_font, fill=theme["muted"])
            pt_y += 34

    # Bottom watermark
    wm = "NavaDisha Tech Learning"
    wm_font = load_font(20)
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    draw.text(((text_x_start + text_x_end - (bbox[2] - bbox[0])) // 2, HEIGHT - 30),
              wm, font=wm_font, fill=theme["grid"])

    return np.array(base)


def create_tech_intro(category: str, total: int, theme: dict,
                      image: Optional[Image.Image] = None) -> np.ndarray:
    return create_tech_slide(
        term=f"Learn {category.upper()}",
        explanation=f"Explore {total} essential {category.upper()} concepts in this video",
        theme=theme,
        image=image,
    )


def create_tech_outro(category: str, theme: dict) -> np.ndarray:
    return create_tech_slide(
        term="That's a Wrap!",
        explanation=f"You leveled up your {category.upper()} knowledge. See you tomorrow!",
        theme=theme,
    )


# ── SINGLE-CONCEPT VIDEO ──────────────────────────────────────────────────────

def create_single_concept_video(
    category: str,
    item: dict,
    output_path: str,
    lang: str = "en",
    use_images: bool = True,
) -> str:
    """
    Generate a short (~45-60 sec) video for ONE tech concept.
    Structure: intro → concept explanation → key points → outro.
    """
    theme       = TECH_THEMES.get(category.lower(), DEFAULT_TECH_THEME)
    name        = item["name"]
    explanation = item.get("explanation", f"{name} is a key concept in tech.")
    raw_points  = item.get("points", [])
    clips       = []

    with tempfile.TemporaryDirectory() as tmp:

        # Fetch image once, reuse across slides
        item_img = None
        if use_images:
            print(f"  🖼️  Fetching image for {name}...")
            item_img = get_tech_image(name)

        # ── Slide 1: Intro ────────────────────────────────────────────────────
        print("  Creating intro slide...")
        intro_slide = create_tech_slide(
            term=f"Today: {name}",
            explanation=f"Leveling up your {category.upper()} knowledge — one concept at a time",
            theme=theme,
            image=item_img,
        )
        intro_mp3 = os.path.join(tmp, "intro.mp3")
        create_tts(
            f"Welcome to NavaDisha Tech Learning! "
            f"Today we are breaking down {name} — an essential {category} concept.",
            intro_mp3, lang,
        )
        clips.append(make_clip(intro_slide, intro_mp3))

        # ── Slide 2: Concept explanation ──────────────────────────────────────
        print("  Creating concept slide...")
        main_slide = create_tech_slide(
            term=name,
            explanation=explanation,
            theme=theme,
            image=item_img,
        )
        main_mp3 = os.path.join(tmp, "main.mp3")
        create_tts(
            f"So, what is {name}? {explanation} "
            f"This is one of the core ideas in {category} that every developer should know.",
            main_mp3, lang,
        )
        clips.append(make_clip(main_slide, main_mp3))

        # ── Slide 3: Key points ───────────────────────────────────────────────
        if raw_points:
            print("  Creating key points slide...")
            points_slide = create_points_slide(
                term=name,
                points=raw_points,
                theme=theme,
                image=item_img,
            )
            points_mp3 = os.path.join(tmp, "points.mp3")
            # Build a natural-sounding TTS from the first 5 points
            pts_tts = [p for p in raw_points if p][:5]
            pts_text = " ".join(f"Point {i+1}: {p}" for i, p in enumerate(pts_tts))
            create_tts(
                f"Here are the key things to know about {name}. {pts_text}",
                points_mp3, lang,
            )
            clips.append(make_clip(points_slide, points_mp3))

        # ── Slide 4: Outro ────────────────────────────────────────────────────
        print("  Creating outro slide...")
        outro_slide = create_tech_outro(category, theme)
        outro_mp3   = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"And that is {name} explained! "
            f"Subscribe to NavaDisha for a new {category} concept every single day. See you tomorrow!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3))

        # ── Render ────────────────────────────────────────────────────────────
        print(f"\n  Rendering → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            final.write_videofile(output_path, fps=FPS, codec="libx264",
                                  audio_codec="aac", logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass

    return output_path


# ── AUDIO ─────────────────────────────────────────────────────────────────────

def create_tts(text: str, out_path: str, lang: str = "en") -> None:
    gTTS(text=text, lang=lang, slow=False).save(out_path)


# ── CLIP ASSEMBLY ─────────────────────────────────────────────────────────────

def make_clip(slide: np.ndarray, audio_path: str):
    audio = AudioFileClip(audio_path)
    duration = max(audio.duration + PAUSE_AFTER_AUDIO, MIN_SLIDE_DURATION)
    return _set_audio(ImageClip(slide, duration=duration), audio)


# ── MAIN VIDEO BUILDER ────────────────────────────────────────────────────────

def create_tech_video(
    category: str,
    items: list,
    output_path: str,
    lang: str = "en",
    use_images: bool = True,
) -> str:
    theme = TECH_THEMES.get(category.lower(), DEFAULT_TECH_THEME)
    total = len(items)
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Intro ──
        print("  Creating intro...")
        intro_img = None
        if use_images:
            intro_img = fetch_pexels_image(f"{category} technology concept")
        intro_slide = create_tech_intro(category, total, theme, image=intro_img)
        intro_mp3   = os.path.join(tmp, "intro.mp3")
        create_tts(f"Welcome! In this video you'll learn {total} key {category} concepts. Let's dive in!",
                   intro_mp3, lang)
        clips.append(make_clip(intro_slide, intro_mp3))

        # ── Concept slides ──
        for i, item in enumerate(items, 1):
            name        = item["name"]
            explanation = item.get("explanation", f"{name} is a key concept in tech.")
            counter     = f"{i} of {total}"

            print(f"  [{i}/{total}] {name}", end="", flush=True)
            item_img = None
            if use_images:
                item_img = get_tech_image(name)
                print(f"  {'🖼️ ' if item_img else '📝 '}", end="")
            print()

            slide    = create_tech_slide(term=name, explanation=explanation,
                                         theme=theme, counter=counter, image=item_img)
            mp3_path = os.path.join(tmp, f"item_{i}.mp3")
            create_tts(f"{name}. {explanation}", mp3_path, lang)
            clips.append(make_clip(slide, mp3_path))

        # ── Outro ──
        print("  Creating outro...")
        outro_slide = create_tech_outro(category, theme)
        outro_mp3   = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"Great work! You've learned {total} {category} concepts. "
            "Come back tomorrow for another tech learning concept!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3))

        # ── Render ──
        print(f"\n  Rendering → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            final.write_videofile(output_path, fps=FPS, codec="libx264",
                                  audio_codec="aac", logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass

    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create tech learning videos with Pexels images + TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tech_video_creator.py ai                  # whole category (10 slides)
  python tech_video_creator.py all                 # all 5 categories
  python tech_video_creator.py rag --items 5       # first 5 concepts
  python tech_video_creator.py all --no-images     # text-only slides

  # ── Single-concept mode (daily pipeline) ───────────────────────────────────
  python tech_video_creator.py --item "RAG"             --cat rag
  python tech_video_creator.py --item "Vector Database" --cat rag
        """,
    )
    # Positional (legacy whole-category mode)
    parser.add_argument("category", nargs="?", default=None,
                        help="Category name or 'all' — omit when using --item/--cat")
    # Single-concept mode
    parser.add_argument("--item",       default=None,
                        help="Single concept name, e.g. 'RAG'  (enables single-concept mode)")
    parser.add_argument("--cat",        default=None,
                        help="Category for --item, e.g. 'rag'")
    # Common options
    parser.add_argument("--config",     default="tech_content_config")
    parser.add_argument("--output-dir", default="tech_videos")
    parser.add_argument("--lang",       default="en")
    parser.add_argument("--items",      type=int, default=0,
                        help="Limit concepts per category (whole-category mode only)")
    parser.add_argument("--no-images",  action="store_true",
                        help="Disable Pexels image fetching (text-only slides)")
    args = parser.parse_args()

    use_images = not args.no_images
    if use_images and not PEXELS_API_KEY:
        print("⚠️   PEXELS_API_KEY not set — using text-only slides.")
        print("    Free key: https://www.pexels.com/api/\n")
        use_images = False

    config_path = args.config
    if os.path.isdir(args.config):
        if hasattr(args, 'cat') and args.cat and os.path.exists(os.path.join(args.config, f"{args.cat}.json")):
            config_path = os.path.join(args.config, f"{args.cat}.json")
        else:
            json_files = sorted(glob.glob(os.path.join(args.config, "*.json")))
            if not json_files:
                print(f"❌  No JSON config files found in directory: {args.config}")
                return
            
            state_file = os.path.join(args.config, ".last_config_idx.txt")
            idx = 0
            if os.path.exists(state_file):
                try:
                    with open(state_file) as sf:
                        idx = (int(sf.read().strip()) + 1) % len(json_files)
                except Exception:
                    pass
            
            config_path = json_files[idx]
            try:
                with open(state_file, "w") as sf:
                    sf.write(str(idx))
            except Exception:
                pass
                
            print(f"🔄  Sequentially selected config: {os.path.basename(config_path)}")

    if not os.path.exists(config_path):
        print(f"❌  Config not found: {config_path}")
        return

    cat_from_file = os.path.basename(config_path).replace(".json", "")
    with open(config_path) as f:
        raw_config = json.load(f)

    # Normalize raw_config into the expected format { "category": { "items": [...] } }
    config = {}
    is_multi = False
    for k, v in raw_config.items():
        if isinstance(v, dict) and "items" in v:
            is_multi = True
            break

    if is_multi:
        config = raw_config
    else:
        items = []
        if isinstance(raw_config, dict) and raw_config and isinstance(next(iter(raw_config.values())), dict):
            # New format: {"Lion": {"explanation": "...", "points": [...]}}
            for name, data in raw_config.items():
                item = {"name": name} if "name" not in data else {"name": data["name"]} # use existing name if present
                item["name"] = name
                item.update(data)
                items.append(item)
        elif "items" in raw_config:
            items = raw_config["items"]
        elif isinstance(raw_config, dict) and raw_config and "items" in next(iter(raw_config.values())):
            items = next(iter(raw_config.values()))["items"]
        else:
            items = raw_config if isinstance(raw_config, list) else []
            
        config = {cat_from_file: {"items": sorted(items, key=lambda x: x.get("name", ""))}}

    # ── SINGLE-CONCEPT MODE ───────────────────────────────────────────────────
    if args.item:
        if not args.cat:
            print("❌  --cat CATEGORY is required when using --item")
            return
        cat = args.cat.lower()
        if cat not in config:
            print(f"❌  Unknown category: {cat!r}. Available: {list(config.keys())}")
            return

        # Look up the concept by name (case-insensitive); create stub if not found
        item_data = next(
            (it for it in config[cat]["items"]
             if it["name"].lower() == args.item.lower()),
            None,
        )
        if item_data is None:
            print(f"⚠️   Item {args.item!r} not found in '{cat}' config — using name only.")
            item_data = {"name": args.item,
                         "explanation": f"{args.item} is a key concept in tech."}

        slug        = item_data["name"].lower().replace(" ", "_").replace("-", "_")
        output_path = os.path.join(args.output_dir, f"{slug}_learning.mp4")

        print("=" * 60)
        print("  💻  Tech Learning Video Creator — Single Concept")
        print(f"  📂  Category : {cat}")
        print(f"  🏷️   Concept  : {item_data['name']}")
        print(f"  {'🖼️   Images: Pexels API ✅' if use_images else '📝  Images: text-only mode'}")
        print("=" * 60)

        os.makedirs(args.output_dir, exist_ok=True)
        try:
            create_single_concept_video(
                category=cat, item=item_data, output_path=output_path,
                lang=args.lang, use_images=use_images,
            )
            print(f"\n✅  Done: {output_path}")
        except Exception as e:
            import traceback
            print(f"❌  Failed: {e}")
            traceback.print_exc()
        return

    # ── WHOLE-CATEGORY MODE (original behaviour) ──────────────────────────────
    cat_arg  = args.category or "all"
    all_cats = list(config.keys()) + ["all"]
    if cat_arg not in all_cats:
        print(f"❌  Unknown category: {cat_arg!r}. Choose from: {all_cats}")
        return

    categories = list(config.keys()) if cat_arg == "all" else [cat_arg]

    print("=" * 60)
    print("  💻  Tech Learning Video Creator")
    print(f"  {'🖼️   Images: Pexels API ✅' if use_images else '📝  Images: text-only mode'}")
    print("=" * 60)

    os.makedirs(args.output_dir, exist_ok=True)
    created = []

    for cat in categories:
        if cat not in config:
            print(f"⚠️   Unknown category: {cat}")
            continue
        items = config[cat]["items"]
        if args.items > 0:
            items = items[: args.items]

        output_path = os.path.join(args.output_dir, f"{cat}_learning.mp4")
        print(f"\n🎯  {cat.upper()} — {len(items)} concepts")
        print(f"📁  → {output_path}")
        print("-" * 40)

        try:
            create_tech_video(category=cat, items=items, output_path=output_path,
                              lang=args.lang, use_images=use_images)
            print(f"✅  {cat}_learning.mp4 done!")
            created.append(output_path)
        except Exception as e:
            import traceback
            print(f"❌  Failed: {e}")
            traceback.print_exc()

    print(f"\n🎉  Done! {len(created)}/{len(categories)} videos created.")
    print("=" * 60)


if __name__ == "__main__":
    main()
