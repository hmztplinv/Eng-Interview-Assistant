"""
Interview Assistant - Ana Giriş Noktası
FastAPI backend: HTTP server + WebSocket + Overlay UI serve
Tek komutla her şey ayağa kalkar: python main.py
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Proje modülleri
import transcriber
import ai_responder

# ─── Ortam değişkenlerini yükle ─────────────────────────────────
load_dotenv()

# ─── Logging ayarları ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("interview-assistant")

# ─── API key kontrolü ──────────────────────────────────────────
def check_api_keys():
    """API key'lerin .env dosyasında tanımlı olduğunu kontrol et."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    
    missing = []
    if not openai_key or openai_key.startswith("sk-your"):
        missing.append("OPENAI_API_KEY")
    if not anthropic_key or anthropic_key.startswith("sk-ant-your"):
        missing.append("ANTHROPIC_API_KEY")
    
    if missing:
        logger.error("=" * 50)
        logger.error("EKSIK API KEY'LER:")
        for key in missing:
            logger.error(f"  - {key}")
        logger.error("")
        logger.error(".env dosyasını düzenleyin:")
        logger.error("  notepad .env")
        logger.error("=" * 50)
        sys.exit(1)
    
    logger.info("API key'ler OK")

# ─── Aday profili yükleme ──────────────────────────────────────
def load_candidate_profile() -> dict:
    """candidate_profile.json dosyasını yükle ve kontrol et."""
    profile_path = Path("candidate_profile.json")
    
    if not profile_path.exists():
        logger.error("candidate_profile.json bulunamadı!")
        sys.exit(1)
    
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
        
        logger.info(f"Aday profili yüklendi: {profile.get('name', 'Bilinmiyor')}")
        logger.info(f"Hedef pozisyon: {profile.get('target_position', 'Belirtilmemiş')}")
        logger.info(f"Hedef şirket: {profile.get('target_company', 'Belirtilmemiş')}")
        
        return profile
    except json.JSONDecodeError as e:
        logger.error(f"candidate_profile.json parse hatası: {e}")
        sys.exit(1)

from contextlib import asynccontextmanager

# ─── Lifespan (başlatma/kapatma) ───────────────────────────────
@asynccontextmanager
async def lifespan(app):
    """Uygulama başladığında ve kapandığında çalışır."""
    # ── Startup ──
    logger.info("=" * 50)
    logger.info("  INTERVIEW ASSISTANT BAŞLATILIYOR")
    logger.info("=" * 50)
    
    global candidate_profile
    candidate_profile = load_candidate_profile()
    
    # AI Responder'a profili yükle
    ai_responder.load_profile(candidate_profile)
    
    logger.info("")
    logger.info("Overlay UI: http://localhost:8765")
    logger.info("WebSocket (overlay): ws://localhost:8765/ws/overlay")
    logger.info("WebSocket (audio):   ws://localhost:8765/ws/audio")
    logger.info("")
    logger.info("Overlay'i Chrome'da açmak için:")
    logger.info('  chrome.exe --app=http://localhost:8765 --always-on-top')
    logger.info("")
    logger.info("Ses yakalama script'ini ayrı terminalde başlatın:")
    logger.info("  python audio_capture.py")
    logger.info("=" * 50)
    
    yield
    
    # ── Shutdown ──
    logger.info("Interview Assistant kapatılıyor...")

# ─── FastAPI uygulaması ─────────────────────────────────────────
app = FastAPI(title="Interview Assistant", lifespan=lifespan)

# Global değişkenler
candidate_profile: dict = {}
# Bağlı overlay WebSocket istemcileri (birden fazla tarayıcı penceresi olabilir)
overlay_clients: Set[WebSocket] = set()

# ─── Overlay UI endpoint'i ──────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def serve_overlay():
    """Overlay UI'ı serve et."""
    overlay_path = Path("overlay/index.html")
    if not overlay_path.exists():
        return HTMLResponse(
            content="<h1>Overlay UI henüz oluşturulmadı</h1><p>Adım 6'da oluşturulacak.</p>",
            status_code=200
        )
    
    with open(overlay_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# ─── Profil bilgisi endpoint'i ──────────────────────────────────
@app.get("/api/profile")
async def get_profile():
    """Aday profilini JSON olarak döndür (overlay UI için)."""
    return JSONResponse(content={
        "name": candidate_profile.get("name", ""),
        "target_position": candidate_profile.get("target_position", ""),
        "target_company": candidate_profile.get("target_company", "")
    })

# ─── Durum endpoint'i ──────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    """Sistem durumunu döndür."""
    return JSONResponse(content={
        "status": "running",
        "overlay_clients": len(overlay_clients),
        "profile_loaded": bool(candidate_profile)
    })

# ─── Overlay WebSocket ─────────────────────────────────────────
@app.websocket("/ws/overlay")
async def overlay_websocket(websocket: WebSocket):
    """
    Overlay UI ile iletişim kuran WebSocket.
    Transkript ve AI cevaplarını overlay'e gönderir.
    Overlay'den manuel soru girişi alır.
    """
    await websocket.accept()
    overlay_clients.add(websocket)
    client_id = id(websocket)
    logger.info(f"Overlay bağlandı (id: {client_id}, toplam: {len(overlay_clients)})")
    
    try:
        # Bağlantı mesajı gönder
        await websocket.send_json({
            "type": "connected",
            "message": "Backend'e bağlandı",
            "profile": {
                "name": candidate_profile.get("name", ""),
                "target_position": candidate_profile.get("target_position", ""),
                "target_company": candidate_profile.get("target_company", "")
            }
        })
        
        # Overlay'den gelen mesajları dinle
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            
            if msg_type == "manual_question":
                # Manuel soru girişi - kullanıcı yazarak soru girdi
                question = data.get("text", "").strip()
                if question:
                    logger.info(f"Manuel soru: {question[:50]}...")
                    # İşleme fonksiyonu Adım 4'te eklenecek
                    await process_question(question, source="manual")
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        logger.info(f"Overlay bağlantısı kesildi (id: {client_id})")
    except Exception as e:
        logger.error(f"Overlay WebSocket hatası: {e}")
    finally:
        overlay_clients.discard(websocket)
        logger.info(f"Overlay kaldırıldı (kalan: {len(overlay_clients)})")

# ─── Audio Capture WebSocket ───────────────────────────────────
@app.websocket("/ws/audio")
async def audio_websocket(websocket: WebSocket):
    """
    Ses yakalama script'inden WAV verisi alan WebSocket.
    Gelen sesi Whisper'a gönderir, sonra Claude'a sorar.
    """
    await websocket.accept()
    logger.info("Ses yakalama bağlandı")
    
    try:
        while True:
            # Binary WAV verisi al
            audio_data = await websocket.receive_bytes()
            logger.info(f"Ses verisi alındı: {len(audio_data)} bytes")
            
            # Overlay'e "işleniyor" durumu gönder
            await broadcast_to_overlays({
                "type": "status",
                "status": "processing",
                "message": "Ses işleniyor..."
            })
            
            # Whisper ile transkribe et (Adım 3'te implement edilecek)
            transcript = await transcribe_audio(audio_data)
            
            if transcript:
                logger.info(f"Transkript: {transcript[:80]}...")
                
                # Transkripti overlay'e gönder
                await broadcast_to_overlays({
                    "type": "transcript",
                    "text": transcript
                })
                
                # Claude ile cevap üret (Adım 4'te implement edilecek)
                await process_question(transcript, source="audio")
            else:
                logger.warning("Transkript boş geldi, atlanıyor")
                await broadcast_to_overlays({
                    "type": "status",
                    "status": "listening",
                    "message": "Dinliyor..."
                })
    
    except WebSocketDisconnect:
        logger.info("Ses yakalama bağlantısı kesildi")
    except Exception as e:
        logger.error(f"Audio WebSocket hatası: {e}")

# ─── Yardımcı fonksiyonlar ─────────────────────────────────────
async def broadcast_to_overlays(message: dict):
    """Tüm bağlı overlay istemcilerine mesaj gönder."""
    disconnected = set()
    for client in overlay_clients:
        try:
            await client.send_json(message)
        except Exception:
            disconnected.add(client)
    
    # Kopan bağlantıları temizle
    overlay_clients.difference_update(disconnected)

async def transcribe_audio(audio_data: bytes) -> str:
    """Ses verisini Whisper API ile transkribe et."""
    return await transcriber.transcribe(audio_data)

async def process_question(question: str, source: str = "audio"):
    """Soruyu Claude API ile işleyip cevap üret ve overlay'e gönder."""
    # Overlay'e "cevap hazırlanıyor" durumu gönder
    await broadcast_to_overlays({
        "type": "status",
        "status": "processing",
        "message": "Cevap hazırlanıyor..."
    })
    
    # Claude ile cevap üret
    response_text = await ai_responder.generate_response(question)
    
    if response_text:
        # Cevabı overlay'e gönder
        await broadcast_to_overlays({
            "type": "response",
            "text": response_text,
            "source": source
        })
    else:
        await broadcast_to_overlays({
            "type": "response",
            "text": "[Cevap üretilemedi]",
            "source": source
        })
    
    # Durumu tekrar "dinliyor"ya çek
    await broadcast_to_overlays({
        "type": "status",
        "status": "listening",
        "message": "Dinliyor..."
    })

# ─── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    # API key kontrolü (sunucu başlamadan önce)
    check_api_keys()
    
    # Uvicorn ile FastAPI'yi başlat
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        # Geliştirme sırasında reload açılabilir:
        # reload=True
    )