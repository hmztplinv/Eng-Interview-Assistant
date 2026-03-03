"""
Interview Assistant - Ses Yakalama Modülü
Stereo Mix'ten ses yakalar, WebRTC VAD ile cümle bitişi algılar,
WAV olarak WebSocket üzerinden backend'e gönderir.

Kullanım: python audio_capture.py
"""

import sys
import io
import wave
import time
import json
import struct
import asyncio
import logging
import threading
import queue  # Thread-safe queue (asyncio.Queue değil!)

import pyaudio
import webrtcvad
import websockets

# ─── Logging ayarları ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("audio-capture")

# ─── Ses ayarları ──────────────────────────────────────────────
SAMPLE_RATE = 16000       # 16 kHz (Whisper ve VAD için ideal)
CHANNELS = 1              # Mono
SAMPLE_WIDTH = 2          # 16-bit (2 bytes)
FRAME_DURATION_MS = 30    # VAD frame süresi (10, 20, veya 30 ms)
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples

# ─── VAD ayarları ──────────────────────────────────────────────
VAD_AGGRESSIVENESS = 2    # 0-3 arası (2 = dengeli)
SILENCE_THRESHOLD = 1.5   # Saniye - bu kadar sessizlik olursa cümle bitti say
MIN_SPEECH_DURATION = 1.0 # Saniye - minimum konuşma süresi (gürültü filtresi)
MAX_SPEECH_DURATION = 45  # Saniye - maksimum parça süresi

# ─── WebSocket ayarları ────────────────────────────────────────
WS_URL = "ws://127.0.0.1:8765/ws/audio"
RECONNECT_DELAY = 3       # Bağlantı koparsa tekrar deneme süresi (saniye)


def stereo_to_mono(data: bytes, input_channels: int) -> bytes:
    """Stereo ses verisini mono'ya çevir."""
    if input_channels == 1:
        return data
    
    num_samples = len(data) // 2
    samples = struct.unpack(f"<{num_samples}h", data)
    mono_samples = []
    
    for i in range(0, len(samples), input_channels):
        if i + input_channels <= len(samples):
            channel_sum = sum(samples[i:i + input_channels])
            mono_samples.append(int(channel_sum / input_channels))
    
    return struct.pack(f"<{len(mono_samples)}h", *mono_samples)


def resample_simple(data: bytes, from_rate: int, to_rate: int) -> bytes:
    """Basit linear interpolation ile resample yap."""
    if from_rate == to_rate:
        return data
    
    num_samples = len(data) // 2
    samples = struct.unpack(f"<{num_samples}h", data)
    
    ratio = to_rate / from_rate
    new_length = int(len(samples) * ratio)
    new_samples = []
    
    for i in range(new_length):
        src_idx = i / ratio
        idx = int(src_idx)
        frac = src_idx - idx
        
        if idx + 1 < len(samples):
            sample = int(samples[idx] * (1 - frac) + samples[idx + 1] * frac)
        elif idx < len(samples):
            sample = samples[idx]
        else:
            sample = 0
        
        sample = max(-32768, min(32767, sample))
        new_samples.append(sample)
    
    return struct.pack(f"<{len(new_samples)}h", *new_samples)


def list_audio_devices():
    """Kullanılabilir ses cihazlarını listele."""
    p = pyaudio.PyAudio()
    
    print("\n" + "=" * 60)
    print("  KULLANILABILIR SES CİHAZLARI")
    print("=" * 60)
    
    input_devices = []
    
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
        except Exception:
            continue
        
        if info["maxInputChannels"] > 0:
            name = info["name"]
            channels = info["maxInputChannels"]
            rate = int(info["defaultSampleRate"])
            
            input_devices.append({
                "index": i,
                "name": name,
                "channels": channels,
                "sample_rate": rate
            })
            
            marker = " ★ STEREO MIX" if "stereo mix" in name.lower() else ""
            print(f"  [{i}] {name} (ch: {channels}, rate: {rate}){marker}")
    
    print("=" * 60)
    p.terminate()
    
    return input_devices


def select_device(devices: list) -> dict:
    """Kullanıcıdan ses cihazı seçmesini iste."""
    stereo_mix = None
    for dev in devices:
        if "stereo mix" in dev["name"].lower():
            stereo_mix = dev
            break
    
    if stereo_mix:
        print(f"\n  ★ Stereo Mix bulundu: [{stereo_mix['index']}] {stereo_mix['name']}")
        print(f"    Otomatik seçmek için Enter'a basın,")
        print(f"    veya başka bir cihaz numarası girin.")
    
    while True:
        try:
            choice = input(f"\n  Cihaz numarası seçin (Enter = Stereo Mix): ").strip()
            
            if choice == "" and stereo_mix:
                print(f"\n  ✓ Seçilen: {stereo_mix['name']}")
                return stereo_mix
            
            idx = int(choice)
            selected = None
            for dev in devices:
                if dev["index"] == idx:
                    selected = dev
                    break
            
            if selected:
                print(f"\n  ✓ Seçilen: {selected['name']}")
                return selected
            else:
                print(f"  ✗ Geçersiz numara. Tekrar deneyin.")
        except ValueError:
            print(f"  ✗ Lütfen bir sayı girin.")
        except KeyboardInterrupt:
            print("\n\nÇıkış...")
            sys.exit(0)


def create_wav_bytes(audio_frames: list, sample_rate: int = SAMPLE_RATE) -> bytes:
    """PCM ses frame'lerini WAV formatına çevir."""
    buffer = io.BytesIO()
    
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        for frame in audio_frames:
            wf.writeframes(frame)
    
    return buffer.getvalue()


class AudioCapture:
    """Ses yakalama ve VAD ile cümle algılama sınıfı."""
    
    def __init__(self, device_info: dict):
        self.device_index = device_info["index"]
        self.device_channels = device_info["channels"]
        self.device_rate = device_info["sample_rate"]
        self.device_name = device_info["name"]
        
        # VAD başlat
        self.vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        
        # Durum değişkenleri
        self.is_speech = False
        self.speech_frames = []
        self.silence_frames_count = 0
        self.speech_start_time = 0
        
        # Thread-safe queue
        self.audio_queue = queue.Queue(maxsize=20)
        
        # Kontrol
        self.running = False
        self.stream = None
        self.pa = None
    
    def start(self):
        """Ses yakalamayı başlat (ayrı thread'de çalışır)."""
        self.running = True
        self.pa = pyaudio.PyAudio()
        
        actual_rate = int(self.device_rate)
        actual_channels = self.device_channels
        
        # Cihaz rate'ine göre frame boyutu
        device_frame_size = int(actual_rate * FRAME_DURATION_MS / 1000)
        
        # Sessizlik eşiği: frame sayısı cinsinden
        silence_frames_threshold = int(SILENCE_THRESHOLD / (FRAME_DURATION_MS / 1000))
        
        logger.info(f"Ses yakalama başlıyor: {self.device_name}")
        logger.info(f"  Cihaz: {actual_rate} Hz, {actual_channels} ch")
        logger.info(f"  VAD: {SAMPLE_RATE} Hz, frame={FRAME_SIZE} samples ({FRAME_DURATION_MS}ms)")
        logger.info(f"  Sessizlik eşiği: {silence_frames_threshold} frame ({SILENCE_THRESHOLD}s)")
        
        try:
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=actual_channels,
                rate=actual_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=device_frame_size,
            )
            
            logger.info("  ✓ Ses stream'i açıldı, dinlemeye başlıyor...")
            
            # Resampled veri için birikim bufferı
            # (44100->16000 dönüşümünde frame boyutu tam denk gelmeyebilir)
            leftover = b""
            expected_bytes = FRAME_SIZE * SAMPLE_WIDTH  # 960 bytes
            
            while self.running:
                try:
                    # Ham ses verisini oku
                    raw_data = self.stream.read(device_frame_size, exception_on_overflow=False)
                    
                    # Mono'ya çevir
                    mono_data = stereo_to_mono(raw_data, actual_channels)
                    
                    # 16000 Hz'e resample et
                    if actual_rate != SAMPLE_RATE:
                        resampled = resample_simple(mono_data, actual_rate, SAMPLE_RATE)
                    else:
                        resampled = mono_data
                    
                    # Önceki artık veriyle birleştir
                    buffer = leftover + resampled
                    leftover = b""
                    
                    # Buffer'ı VAD frame boyutunda parçalara böl
                    offset = 0
                    while offset + expected_bytes <= len(buffer):
                        vad_frame = buffer[offset:offset + expected_bytes]
                        offset += expected_bytes
                        
                        # VAD kontrolü
                        try:
                            is_speech = self.vad.is_speech(vad_frame, SAMPLE_RATE)
                        except Exception:
                            is_speech = False
                        
                        # ─── Konuşma durumu yönetimi ───────
                        if is_speech:
                            if not self.is_speech:
                                # Konuşma yeni başladı
                                self.is_speech = True
                                self.speech_start_time = time.time()
                                self.speech_frames = []
                                self.silence_frames_count = 0
                                logger.info("🎤 Konuşma algılandı!")
                            
                            self.speech_frames.append(vad_frame)
                            self.silence_frames_count = 0
                        
                        else:  # Sessizlik
                            if self.is_speech:
                                # Konuşma sırasında sessizlik
                                self.speech_frames.append(vad_frame)
                                self.silence_frames_count += 1
                                
                                speech_duration = time.time() - self.speech_start_time
                                
                                if self.silence_frames_count >= silence_frames_threshold:
                                    # Sessizlik eşiği aşıldı
                                    if speech_duration >= MIN_SPEECH_DURATION:
                                        logger.info(
                                            f"📝 Cümle tamamlandı "
                                            f"({speech_duration:.1f}s, "
                                            f"{len(self.speech_frames)} frames)"
                                        )
                                        
                                        wav_data = create_wav_bytes(self.speech_frames)
                                        
                                        try:
                                            self.audio_queue.put_nowait(wav_data)
                                            logger.info(f"📦 Kuyruğa eklendi: {len(wav_data)} bytes")
                                        except queue.Full:
                                            logger.warning("Kuyruk dolu, atlandı")
                                    else:
                                        logger.debug(f"Kısa konuşma ({speech_duration:.1f}s), atlandı")
                                    
                                    # Sıfırla
                                    self.is_speech = False
                                    self.speech_frames = []
                                    self.silence_frames_count = 0
                                
                                elif speech_duration >= MAX_SPEECH_DURATION:
                                    logger.info(f"⏱️ Maks süre ({speech_duration:.1f}s)")
                                    wav_data = create_wav_bytes(self.speech_frames)
                                    try:
                                        self.audio_queue.put_nowait(wav_data)
                                    except queue.Full:
                                        pass
                                    
                                    self.speech_frames = []
                                    self.speech_start_time = time.time()
                                    self.silence_frames_count = 0
                    
                    # Kalan veriyi sonraki iterasyona aktar
                    if offset < len(buffer):
                        leftover = buffer[offset:]
                
                except IOError as e:
                    logger.warning(f"Ses okuma hatası: {e}")
                    time.sleep(0.01)
        
        except Exception as e:
            logger.error(f"Stream hatası: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop()
    
    def stop(self):
        """Ses yakalamayı durdur."""
        self.running = False
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
        
        if self.pa:
            try:
                self.pa.terminate()
            except Exception:
                pass
        
        logger.info("Ses yakalama durduruldu")


async def websocket_sender(capture: AudioCapture):
    """Kuyruktan ses parçalarını alıp WebSocket üzerinden backend'e gönder."""
    while capture.running:
        try:
            logger.info(f"Backend'e bağlanılıyor: {WS_URL}")
            
            async with websockets.connect(WS_URL) as ws:
                logger.info("✓ Backend'e bağlandı!")
                
                while capture.running:
                    try:
                        # Thread-safe queue'dan non-blocking kontrol
                        wav_data = capture.audio_queue.get_nowait()
                        
                        await ws.send(wav_data)
                        logger.info(f"📤 Backend'e gönderildi: {len(wav_data)} bytes")
                    
                    except queue.Empty:
                        # Kuyrukta veri yok, kısa bekle
                        await asyncio.sleep(0.1)
                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("WebSocket bağlantısı kapandı")
                        break
        
        except (ConnectionRefusedError, OSError) as e:
            logger.warning(f"Backend'e bağlanılamadı: {e}")
        except Exception as e:
            logger.error(f"WebSocket hatası: {e}")
        
        if capture.running:
            logger.info(f"{RECONNECT_DELAY}s sonra tekrar denenecek...")
            await asyncio.sleep(RECONNECT_DELAY)


async def main():
    """Ana giriş noktası."""
    print("=" * 60)
    print("  INTERVIEW ASSISTANT - SES YAKALAMA")
    print("=" * 60)
    
    devices = list_audio_devices()
    
    if not devices:
        print("\n  ✗ Hiç ses giriş cihazı bulunamadı!")
        sys.exit(1)
    
    selected = select_device(devices)
    
    capture = AudioCapture(selected)
    
    # Ses yakalamayı ayrı thread'de başlat
    audio_thread = threading.Thread(target=capture.start, daemon=True)
    audio_thread.start()
    
    await asyncio.sleep(1)
    
    if not capture.running:
        print("\n  ✗ Ses yakalama başlatılamadı!")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("  ✓ Ses yakalama aktif!")
    print("  Konuşmayı dinliyor... (Ctrl+C ile durdurulur)")
    print("=" * 60 + "\n")
    
    try:
        await websocket_sender(capture)
    except KeyboardInterrupt:
        print("\n\nDurduruluyor...")
    finally:
        capture.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nÇıkış.")