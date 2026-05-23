import os, re, glob, requests, spotipy, instaloader
from yt_dlp import YoutubeDL
from spotipy.oauth2 import SpotifyClientCredentials
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from config import *

# =========================================
# CONFIGURAÇÃO E LOGIN
# =========================================
DOWNLOADS_DIR = "downloads"
if not os.path.exists(DOWNLOADS_DIR): os.makedirs(DOWNLOADS_DIR)

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
L = instaloader.Instaloader(dirname_pattern=DOWNLOADS_DIR, save_metadata=False, download_comments=False)

try:
    L.login(IG_USER, IG_PASS)
    print("🌙 Login no Instagram realizado com sucesso!")
except Exception as e:
    print(f"🌙 Erro ao logar no Instagram: {e}")

# =========================================
# FUNÇÕES DE DOWNLOAD
# =========================================

def download_instagram(url):
    limpar_downloads()
    try:
        # Se for Story
        if "/stories/" in url:
            username = url.split("/stories/")[1].split("/")[0]
            profile = instaloader.Profile.from_username(L.context, username)
            stories = L.get_stories(userids=[profile.userid])
            for story in stories:
                for item in story.get_items(): L.download_storyitem(item, target=DOWNLOADS_DIR)
        # Se for Post/Reel
        else:
            shortcode = url.split("/reel/")[-1].split("/")[0] if "/reel/" in url else url.split("/p/")[-1].split("/")[0]
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=DOWNLOADS_DIR)
    except Exception as e: print(f"Erro Insta: {e}")
    return [f for f in glob.glob(os.path.join(DOWNLOADS_DIR, "*")) if f.lower().endswith((".jpg", ".jpeg", ".png", ".mp4"))]

def download_twitter(url):
    limpar_downloads()
    # Limpa URL de parâmetros de rastreio
    url = url.split("?")[0]
    post_id = url.split("/")[-1]
    # Tenta via API
    try:
        resp = requests.get(f"https://api.vxtwitter.com/status/{post_id}").json()
        media_urls = resp.get("mediaURLs", [])
        arquivos = []
        for i, m_url in enumerate(media_urls):
            ext = 'mp4' if 'video' in m_url else 'jpg'
            path = os.path.join(DOWNLOADS_DIR, f"tw_{i}.{ext}")
            with open(path, 'wb') as f: f.write(requests.get(m_url).content)
            arquivos.append(path)
        return arquivos
    except: return []

# =========================================
# ENVIO INTELIGENTE (Agrupamento de 10 em 10)
# =========================================

async def send_media(update, arquivos):
    if not arquivos:
        await update.message.reply_text("🌙 Nada encontrado. Verifique se o perfil não é privado.")
        return
    
    # Divide arquivos em blocos de 10
    for i in range(0, len(arquivos), 10):
        group = []
        for f in arquivos[i:i+10]:
            if f.lower().endswith((".mp4", ".mov")): group.append(InputMediaVideo(media=open(f, "rb")))
            else: group.append(InputMediaPhoto(media=open(f, "rb")))
        await update.message.reply_media_group(media=group)

# =========================================
# ROTEADOR (HANDLE MESSAGE)
# =========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not any(d in url for d in ["spotify.com", "instagram.com", "x.com", "twitter.com", "youtube.com"]): return

    if "instagram.com" in url:
        await update.message.reply_text("🌙 Baixando do Instagram...")
        await send_media(update, download_instagram(url))
    
    elif "x.com" in url or "twitter.com" in url:
        await update.message.reply_text("🌙 Baixando do Twitter...")
        await send_media(update, download_twitter(url))
        
    elif "spotify.com" in url:
        await update.message.reply_text("🌙 Processando Spotify...")
        # ... (seu código de spotify original aqui)

# --- (Restante da estrutura main mantida) ---
