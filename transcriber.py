"""
Interview Assistant - Whisper Transkripsiyon Modülü
OpenAI Whisper API ile ses verisini yazıya çevirir.
"""

import os
import io
import time
import logging
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("interview-assistant.transcriber")

# ─── OpenAI istemcisi ──────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Ayarlar ───────────────────────────────────────────────────
WHISPER_MODEL = "whisper-1"
WHISPER_LANGUAGE = "en"  # Mülakatçı İngilizce konuşacak
# Minimum ses uzunluğu (byte cinsinden) - çok kısa sesleri filtrele
# 16000 Hz, 16-bit, mono = 32000 bytes/saniye → 0.5 saniye ≈ 16000 bytes
MIN_AUDIO_SIZE = 16000


async def transcribe(audio_data: bytes) -> str:
    """
    WAV formatındaki ses verisini Whisper API ile transkribe et.
    
    Args:
        audio_data: WAV formatında binary ses verisi
        
    Returns:
        Transkribe edilmiş metin. Başarısız olursa boş string.
    """
    # Çok kısa sesleri filtrele (gürültü olabilir)
    if len(audio_data) < MIN_AUDIO_SIZE:
        logger.debug(f"Ses çok kısa ({len(audio_data)} bytes), atlanıyor")
        return ""
    
    try:
        start_time = time.time()
        
        # WAV verisini dosya benzeri nesneye çevir
        # Whisper API dosya adı + uzantı bekliyor
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"
        
        # Whisper API çağrısı
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            language=WHISPER_LANGUAGE,
            # prompt ile bağlam ver - teknik terimler için
            prompt="This is a job interview conversation about software development, Python, microservices, cloud, AWS, Azure, Docker, team management, and agile methodologies.",
            # Düz metin formatı yeterli
            response_format="text"
        )
        
        elapsed = time.time() - start_time
        transcript = response.strip() if isinstance(response, str) else str(response).strip()
        
        # Boş veya anlamsız sonuçları filtrele
        if not transcript or len(transcript) < 3:
            logger.debug("Transkript çok kısa veya boş, atlanıyor")
            return ""
        
        # Whisper bazen sadece "you" veya "thank you" gibi
        # çok kısa halüsinasyonlar üretir - bunları filtrele
        noise_phrases = [
            "you", "thank you", "thanks", "bye", "okay",
            "hmm", "uh", "um", "ah", "oh",
            "thank you for watching",
            "thanks for watching",
            "subscribe",
            "like and subscribe",
        ]
        if transcript.lower().strip(".!?, ") in noise_phrases:
            logger.debug(f"Gürültü filtresi: '{transcript}' atlandı")
            return ""
        
        logger.info(f"Whisper transkript ({elapsed:.1f}s): {transcript[:100]}...")
        return transcript
    
    except Exception as e:
        logger.error(f"Whisper API hatası: {e}")
        return ""


def test_whisper():
    """
    Whisper API bağlantısını test et.
    Basit bir ses dosyası oluşturup gönderir.
    """
    import wave
    import struct
    
    logger.info("Whisper API test ediliyor...")
    
    # 1 saniyelik sessiz WAV oluştur (sadece API bağlantı testi)
    sample_rate = 16000
    duration = 1  # saniye
    num_samples = sample_rate * duration
    
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)       # Mono
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        # Sessizlik yaz
        for _ in range(num_samples):
            wf.writeframes(struct.pack("<h", 0))
    
    wav_data = buffer.getvalue()
    
    try:
        audio_file = io.BytesIO(wav_data)
        audio_file.name = "test.wav"
        
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            language=WHISPER_LANGUAGE,
            response_format="text"
        )
        
        logger.info(f"Whisper API bağlantısı OK (yanıt: '{response.strip()}')")
        return True
    
    except Exception as e:
        logger.error(f"Whisper API test BAŞARISIZ: {e}")
        return False


# ─── Doğrudan çalıştırma testi ─────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    
    print("=" * 40)
    print("  Whisper API Bağlantı Testi")
    print("=" * 40)
    
    success = test_whisper()
    
    if success:
        print("\n✓ Whisper API çalışıyor!")
    else:
        print("\n✗ Whisper API bağlantı hatası!")
        print("  .env dosyasındaki OPENAI_API_KEY'i kontrol edin.")