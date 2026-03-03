"""
Stereo Mix Teşhis Scripti
Stereo Mix'ten ses gelip gelmediğini ve seviyesini kontrol eder.
Kullanım: python test_audio.py
"""

import pyaudio
import struct
import math
import time

CHUNK = 1024
FORMAT = pyaudio.paInt16
RATE = 44100

def list_and_select():
    p = pyaudio.PyAudio()
    
    print("\n=== SES CİHAZLARI ===")
    stereo_idx = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            name = info["name"]
            if "stereo mix" in name.lower() and stereo_idx is None:
                stereo_idx = i
                print(f"  ★ [{i}] {name} (ch:{info['maxInputChannels']}, rate:{int(info['defaultSampleRate'])})")
            elif i < 15:  # Sadece ilk cihazları göster
                print(f"    [{i}] {name}")
    
    if stereo_idx is None:
        print("  Stereo Mix bulunamadı!")
        p.terminate()
        return None, None
    
    choice = input(f"\nCihaz seç (Enter={stereo_idx}): ").strip()
    idx = int(choice) if choice else stereo_idx
    info = p.get_device_info_by_index(idx)
    
    return p, {
        "index": idx,
        "name": info["name"],
        "channels": info["maxInputChannels"],
        "rate": int(info["defaultSampleRate"])
    }


def rms_level(data, channels):
    """Ses seviyesini RMS olarak hesapla."""
    samples = struct.unpack(f"<{len(data)//2}h", data)
    
    # Mono'ya çevir
    if channels > 1:
        mono = []
        for i in range(0, len(samples), channels):
            mono.append(sum(samples[i:i+channels]) // channels)
        samples = mono
    
    if not samples:
        return 0
    
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / len(samples))
    return rms


def main():
    p, device = list_and_select()
    if not device:
        return
    
    print(f"\n✓ Seçilen: {device['name']}")
    print(f"  Channels: {device['channels']}, Rate: {device['rate']}")
    print(f"\n{'='*50}")
    print("  5 saniye boyunca ses seviyesini ölçüyor...")
    print("  PC'den bir ses çalın (YouTube, mp3, TTS vb.)")
    print(f"{'='*50}\n")
    
    stream = p.open(
        format=FORMAT,
        channels=device["channels"],
        rate=device["rate"],
        input=True,
        input_device_index=device["index"],
        frames_per_buffer=CHUNK
    )
    
    max_rms = 0
    start = time.time()
    
    try:
        while time.time() - start < 5:
            data = stream.read(CHUNK, exception_on_overflow=False)
            rms = rms_level(data, device["channels"])
            max_rms = max(max_rms, rms)
            
            # Görsel bar
            bar_len = int(rms / 200)
            bar = "█" * min(bar_len, 50)
            level = "SESSIZ" if rms < 50 else "DÜŞÜK" if rms < 500 else "ORTA" if rms < 2000 else "YÜKSEK"
            
            print(f"\r  RMS: {rms:7.0f} | {level:6s} | {bar:<50s}", end="", flush=True)
            
    except KeyboardInterrupt:
        pass
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n\n{'='*50}")
    print(f"  Maksimum RMS: {max_rms:.0f}")
    
    if max_rms < 50:
        print("\n  ✗ HİÇ SES YOK!")
        print("    1. Windows Ses Ayarları > Kayıt > Stereo Mix")
        print("       Sağ tıkla > Özellikler > Düzeyler > 100 yap")
        print("    2. Stereo Mix 'Devre Dışı' olabilir")
        print("       Kayıt cihazlarında sağ tıkla > Devre dışı cihazları göster")
        print("    3. Sesi PC hoparlöründen çalın (kulaklık değil)")
    elif max_rms < 500:
        print("\n  ⚠ Ses çok düşük! VAD algılayamayabilir.")
        print("    Stereo Mix seviyesini 100'e çıkarın.")
    else:
        print("\n  ✓ Ses seviyesi yeterli! VAD çalışmalı.")
    
    print(f"{'='*50}")


if __name__ == "__main__":
    main()