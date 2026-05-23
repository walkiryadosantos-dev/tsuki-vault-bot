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
# PASTA DOWNLOADS E APIs
# =========================================

DOWNLOADS_DIR = "downloads"

if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

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
    "instagram.com", "tiktok.com", "vm.tiktok.com", 
    "pinterest.com", "x.com", "twitter.com"
]

# =========================================
# UTILIDADES
# =========================================

def limpar_downloads():
    arquivos = glob.glob(os.path.join(DOWNLOADS_DIR, "*"))
    for arquivo in arquivos:
        try:
            os.remove(arquivo)
        except:
            pass

def extract_url(text):
    if not text:
        return None
    urls = re.findall(r'https?://\S+', text)
    for url in urls:
        for domain in SUPPORTED_DOMAINS:
            if domain in url.lower():
                return url
    return None

# =========================================
# 1. SPOTIFY (PRECISÃO MÁXIMA)
# =========================================

def get_spotify_info(url):
    # Limpa a URL e puxa os dados oficiais do Spotify
    url = url.split("?")[0]
    track = sp.track(url)
    capa = track['album']['images'][0]['url'] if track['album']['images'] else None
    
    return {
        "title": track["name"], 
        "artist": track["artists"][0]["name"], 
        "cover": capa,
        "duration": track["duration_ms"] / 1000 # Tempo em segundos
    }

def download_spotify(artist, title):
    limpar_downloads()
    
    # Adiciona "Official Audio" para forçar o yt-dlp a ignorar clipes, covers e vídeos do tiktok
    query_exata = f'"{artist} - {title}" Official Audio'
    
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
        # Impede de baixar áudios maiores que 10 minutos (ex: loops ou shows completos)
        "match_filter": lambda info: 'Video muito longo' if info.get('duration', 0) > 600 else None
    }
    
    with YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([f"ytsearch1:{query_exata}"])
        except Exception as e:
            print(f"Erro ao tentar baixar áudio: {e}")
            
    arquivos = glob.glob(os.path.join(DOWNLOADS_DIR, "*.mp3"))
    return arquivos[0] if arquivos else None

# =========================================
# 2. TWITTER / X
# =========================================

def download_twitter(url):
    limpar_downloads()
    url_limpa = url.split("?")[0]
    post_path = url_limpa.replace("https://x.com", "").replace("https://twitter.com", "")
    
    arquivos = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    media_urls = []
    
    try:
        api_url = f"https://api.vxtwitter.com{post_path}"
        resposta = requests.get(api_url, headers=headers, timeout=10)
        if resposta.status_code == 200:
            media_urls = resposta.json().get("mediaURLs", [])
            
        if not media_urls:
            api_url_2 = f"https://api.fxtwitter.com{post_path}"
            resposta_2 = requests.get(api_url_2, headers=headers, timeout=10)
            if resposta_2.status_code == 200:
                media_data = resposta_2.json().get("tweet", {}).get("media", {})
                if "photos" in media_data:
                    for p in media_data["photos"]: media_urls.append(p["url"])
                if "videos" in media_data:
                    for v in media_data["videos"]: media_urls.append(v["url"])

        if not media_urls:
            return []
            
        for i, m_url in enumerate(media_urls):
            ext = m_url.split('.')[-1].split('?')[0]
            if ext.lower() not in ['jpg', 'jpeg', 'png', 'mp4']:
                ext = 'jpg' if 'twimg' in m_url else 'mp4'
            caminho_arquivo = os.path.join(DOWNLOADS_DIR, f"twitter_media_{i}.{ext}")
            conteudo = requests.get(m_url, headers=headers, timeout=15).content
            with open(caminho_arquivo, 'wb') as f:
                f.write(conteudo)
            arquivos.append(caminho_arquivo)
            
    except Exception as e:
        print(f"Erro no Twitter: {e}")
    return arquivos

# =========================================
# 3. INSTAGRAM
# =========================================

def download_instagram(url):
    limpar_downloads()
    try:
        shortcode = url.split("/reel/")[1].split("/")[0] if "/reel/" in url else url.split("/p/")[1].split("/")[0]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, target=DOWNLOADS_DIR)
    except:
        pass
    return [f for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")) if f.lower().endswith((".jpg", ".jpeg", ".png", ".mp4"))]

# =========================================
# 4. YOUTUBE, TIKTOK, ETC
# =========================================

def download_media_geral(url):
    limpar_downloads()
    ydl_opts = {
        "outtmpl": f"{DOWNLOADS_DIR}/%(title).80s.%(ext)s",
        "format": "best",
        "quiet": True,
        "ignoreerrors": True,
        "writesubtitles": False,
        "no_warnings": True
    }
    with YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as e:
            print(f"Erro yt-dlp geral: {e}")
            
    extensoes = [".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".gif"]
    return [f for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")) if os.path.splitext(f)[1].lower() in extensoes]

# =========================================
# FUNÇÃO DE ENVIO
# =========================================

async def send_media(update, arquivos):
    if not arquivos:
        await update.message.reply_text("🌙 Não consegui baixar a mídia. Verifique se o link está correto e se o perfil não é privado.")
        return

    if len(arquivos) == 1:
        arquivo = arquivos[0]
        if arquivo.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
            await update.message.reply_video(video=open(arquivo, "rb"))
        else:
            await update.message.reply_photo(photo=open(arquivo, "rb"))
        return

    media_group = []
    for arquivo in arquivos[:10]:
        try:
            if arquivo.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
                media_group.append(InputMediaVideo(media=open(arquivo, "rb")))
            else:
                media_group.append(InputMediaPhoto(media=open(arquivo, "rb")))
        except:
            pass

    if media_group:
        await update.message.reply_media_group(media=media_group)

# =========================================
# ROTEADOR DE LINKS (IDENTIFICA E SEPARA)
# =========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        url = extract_url(text)

        if not url:
            return

        print(f"\n🌙 LINK RECEBIDO: {url}")

        # ROTA 1: SPOTIFY EXCLUSIVO
        if "spotify.com" in url:
            await update.message.reply_text("🌙 Identifiquei um link do Spotify. Buscando áudio de estúdio...")
            info = get_spotify_info(url)
            
            mp3 = download_spotify(info['artist'], info['title'])
            
            if mp3:
                if info.get("cover"):
                    capa_req = requests.get(info["cover"])
                    await update.message.reply_audio(
                        audio=open(mp3, "rb"), 
                        title=info["title"], 
                        performer=info["artist"], 
                        thumbnail=capa_req.content
                    )
                else:
                    await update.message.reply_audio(
                        audio=open(mp3, "rb"), 
                        title=info["title"], 
                        performer=info["artist"]
                    )
            else:
                await update.message.reply_text("🌙 Não consegui encontrar a versão oficial dessa música.")
            return

        # ROTA 2: TWITTER/X
        if "x.com" in url or "twitter.com" in url:
            await update.message.reply_text("🌙 Identifiquei X/Twitter. Extraindo mídia...")
            arquivos = download_twitter(url)
            await send_media(update, arquivos)
            return

        # ROTA 3: INSTAGRAM
        if "instagram.com" in url:
            await update.message.reply_text("🌙 Identifiquei Instagram. Baixando postagem...")
            arquivos = download_instagram(url)
            if not arquivos:
                # Fallback de segurança se o instaloader falhar
                arquivos = download_media_geral(url)
            await send_media(update, arquivos)
            return

        # ROTA 4: YOUTUBE, TIKTOK E RESTANTE
        await update.message.reply_text("🌙 Identifiquei vídeo genérico. Baixando mídia...")
        arquivos = download_media_geral(url)
        await send_media(update, arquivos)

    except Exception as e:
        print(f"Erro principal: {e}")
        await update.message.reply_text(f"🌙 Ocorreu um erro interno ao processar o link.")

# =========================================
# START
# =========================================

if __name__ == '__main__':
    print("🌙 LUNAR BUNNY VAULT ONLINE - ROTEADOR ESTrito ATIVO")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()