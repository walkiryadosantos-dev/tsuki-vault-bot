import os
import re
import glob
import requests
import spotipy
import instaloader

from yt_dlp import YoutubeDL
from spotipy.oauth2 import SpotifyClientCredentials
from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo
)
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters
)

from config import *

# =========================================
# SETUP
# =========================================

DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
)

L = instaloader.Instaloader(
    dirname_pattern=DOWNLOADS_DIR,
    save_metadata=False,
    download_comments=False,
    post_metadata_txt_pattern=""
)

SUPPORTED_DOMAINS = [
    "spotify.com", "youtube.com", "youtu.be",
    "instagram.com", "tiktok.com",
    "x.com", "twitter.com"
]

# =========================================
# CLEAN SAFE
# =========================================

def limpar_downloads():
    for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")):
        try:
            os.remove(f)
        except:
            pass

def extract_url(text):
    if not text:
        return None

    urls = re.findall(r'https?://\S+', text)

    for url in urls:
        for d in SUPPORTED_DOMAINS:
            if d in url.lower():
                return url
    return None

# =========================================
# SPOTIFY
# =========================================

def get_spotify_info(url):
    url = url.split("?")[0]
    track = sp.track(url)

    return {
        "title": track["name"],
        "artist": track["artists"][0]["name"],
        "cover": track["album"]["images"][0]["url"] if track["album"]["images"] else None
    }

def download_spotify(artist, title):
    limpar_downloads()

    query = f"{artist} - {title} audio"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{DOWNLOADS_DIR}/music.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320"
        }],
        "quiet": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        }
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
    except Exception as e:
        print("Spotify download error:", e)

    files = glob.glob(os.path.join(DOWNLOADS_DIR, "*.mp3"))
    return files[0] if files else None

# =========================================
# X / TWITTER (ROBUSTO)
# =========================================

def download_twitter(url):
    limpar_downloads()

    try:
        path = url.replace("https://x.com", "").replace("https://twitter.com", "")

        api = f"https://api.fxtwitter.com{path}"
        r = requests.get(api, timeout=10)

        data = r.json()

        media = data.get("tweet", {}).get("media", {})

        urls = []

        for p in media.get("photos", []):
            urls.append(p["url"])

        for v in media.get("videos", []):
            urls.append(v["url"])

        files = []

        for i, u in enumerate(urls):
            ext = "jpg" if "jpg" in u or "png" in u else "mp4"
            file = os.path.join(DOWNLOADS_DIR, f"x_{i}.{ext}")

            r = requests.get(u, timeout=15)

            with open(file, "wb") as f:
                f.write(r.content)

            files.append(file)

        return files

    except Exception as e:
        print("X error:", e)
        return []

# =========================================
# INSTAGRAM (CARROSSEL + POSTS)
# =========================================

def download_instagram(url):
    limpar_downloads()

    try:
        shortcode = url.split("/p/")[1].split("/")[0] if "/p/" in url else url.split("/reel/")[1].split("/")[0]

        post = instaloader.Post.from_shortcode(L.context, shortcode)

        L.download_post(post, target=DOWNLOADS_DIR)

    except Exception as e:
        print("Instagram error:", e)

    files = glob.glob(os.path.join(DOWNLOADS_DIR, "*"))

    return [
        f for f in files
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".mp4"))
    ]

# =========================================
# YT-DLP (GENÉRICO)
# =========================================

def download_generic(url):
    limpar_downloads()

    ydl_opts = {
        "outtmpl": f"{DOWNLOADS_DIR}/%(title).80s.%(ext)s",
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        }
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print("yt-dlp error:", e)

    return glob.glob(os.path.join(DOWNLOADS_DIR, "*"))

# =========================================
# SEND MEDIA SAFE
# =========================================

async def send_media(update, files):
    if not files:
        await update.message.reply_text("🌙 não consegui baixar essa mídia.")
        return

    if len(files) == 1:
        f = files[0]

        try:
            if f.endswith(".mp4"):
                await update.message.reply_video(open(f, "rb"))
            else:
                await update.message.reply_photo(open(f, "rb"))
        except:
            await update.message.reply_text("🌙 erro ao enviar arquivo único")
        return

    media = []

    for f in files[:10]:
        try:
            if f.endswith(".mp4"):
                media.append(InputMediaVideo(open(f, "rb")))
            else:
                media.append(InputMediaPhoto(open(f, "rb")))
        except:
            pass

    if media:
        await update.message.reply_media_group(media=media)

# =========================================
# HANDLER (ROBUSTO + ANTI CRASH)
# =========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        url = extract_url(text)

        if not url:
            return

        print("🌙 LINK:", url)

        # SPOTIFY
        if "spotify.com" in url:
            await update.message.reply_text("🌙 Spotify detectado...")

            info = get_spotify_info(url)
            mp3 = download_spotify(info["artist"], info["title"])

            if mp3:
                await update.message.reply_audio(
                    audio=open(mp3, "rb"),
                    title=info["title"],
                    performer=info["artist"]
                )
            return

        # X
        if "x.com" in url or "twitter.com" in url:
            await update.message.reply_text("🌙 X detectado...")
            files = download_twitter(url)
            await send_media(update, files)
            return

        # INSTAGRAM
        if "instagram.com" in url:
            await update.message.reply_text("🌙 Instagram detectado...")
            files = download_instagram(url)

            if not files:
                files = download_generic(url)

            await send_media(update, files)
            return

        # RESTO
        await update.message.reply_text("🌙 processando mídia...")
        files = download_generic(url)
        await send_media(update, files)

    except Exception as e:
        print("ERROR:", e)
        await update.message.reply_text("🌙 erro ao processar link")

# =========================================
# START
# =========================================

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("🌙 BOT ONLINE")
    app.run_polling()
