# Interview Assistant - Hızlı Başlangıç Kılavuzu

---

## 1. GÖRÜŞME ÖNCESİ HAZIRLIK

### Hangi dosyada ne değiştirilmeli?

**`.env` dosyası** — API anahtarların:
```
OPENAI_API_KEY=sk-gerçek-openai-keyin
ANTHROPIC_API_KEY=sk-ant-gerçek-anthropic-keyin
```

**`candidate_profile.json` dosyası** — Her yeni iş başvurusu için şu alanları güncelle:

| Alan | Ne yazılacak | Örnek |
|------|-------------|-------|
| `target_position` | Başvurduğun pozisyon | `"Senior Python Developer"` |
| `target_company` | Başvurduğun şirket | `"EPAM Systems"` |
| `why_this_company` | Neden bu şirket (kısa, basit İngilizce) | `"I like the company culture and..."` |
| `job_posting` | İş ilanının tam metni | İlanı kopyala yapıştır |

> **Not:** `name`, `experience`, `skills`, `key_achievements` alanları senin genel profilin — bunları her başvuruda değiştirmene gerek yok.

---

## 2. WINDOWS SES AYARI (ÖNEMLİ — İLK SEFERDE YAP)

Stereo Mix, PC'nin ses çıkışını yakalar. Ses çıkışı Realtek üzerinden olmalı.

1. Görev çubuğu > 🔊 hoparlör ikonu > Ses çıkış cihazı: **Speakers (Realtek)** seç
2. Aynı ikon > sağ tıkla > **Ses Ayarları** > **Kayıt** sekmesi
3. **Stereo Mix (Realtek)** > sağ tıkla > **Özellikler** > **Düzeyler** > **100** yap
4. Stereo Mix'in "Ready" / "Hazır" durumunda olduğunu kontrol et

> **Test:** `python test_audio.py` çalıştır, YouTube'dan ses çal. RMS > 500 görmelisin.

---

## 3. UYGULAMAYI BAŞLATMA

### Terminal 1 — Backend (önce bu):
```
cd C:\Projects\interview-assistant
python main.py
```
Beklenen çıktı:
```
INTERVIEW ASSISTANT BAŞLATILIYOR
Aday profili yüklendi: Hamza
Hedef pozisyon: Senior Python Developer
Overlay UI: http://localhost:8765
```

### Tarayıcı — Overlay UI:
```
chrome.exe --app=http://localhost:8765 --always-on-top
```
Veya tarayıcıda `http://localhost:8765` aç.

### Terminal 2 — Ses Yakalama (yeni terminal aç):
```
cd C:\Projects\interview-assistant
python audio_capture.py
```
- Cihaz listesi çıkacak
- **Enter** bas → Stereo Mix otomatik seçilir
- `✓ Backend'e bağlandı!` mesajını gör

---

## 4. GÖRÜŞME SIRASINDA

### Otomatik mod (ses ile):
- Görüşme platformunu aç (Teams/Zoom/Meet)
- Mülakatçı konuşunca otomatik algılanır
- Overlay'de transkript + önerilen cevap görünür
- Cevabın yanındaki **Kopyala** butonuyla hızlıca kopyalayabilirsin

### Manuel mod (yazarak):
- Overlay'in altındaki input alanına soruyu yaz
- **Enter** bas veya **Gönder** butonuna tıkla
- Ses yakalamada sorun olursa bu yöntemi kullan

---

## 5. GÖRÜŞME SONRASI

- Overlay'deki **📥 İndir** butonuna tıkla
- Tüm soru-cevaplar `.txt` dosyası olarak indirilir
- Dosya adı: `interview_2026-03-03_14-03-29.txt` formatında

---

## 6. KAPATMA

1. Terminal 2'de (audio_capture) → `Ctrl+C`
2. Terminal 1'de (main.py) → `Ctrl+C`

---

## 7. SORUN GİDERME

| Sorun | Çözüm |
|-------|-------|
| Overlay'de "Bağlantı Kesildi" | Backend (main.py) çalışıyor mu kontrol et |
| Ses algılanmıyor | `python test_audio.py` ile Stereo Mix'i test et |
| RMS = 0 (hiç ses yok) | Windows ses çıkışını Realtek'e çevir |
| VAD konuşma algılamıyor | Stereo Mix seviyesini 100'e çıkar |
| Whisper yanlış çeviriyor | Ses seviyesini artır, arka plan gürültüsünü azalt |
| Claude cevap vermiyor | `.env` dosyasındaki ANTHROPIC_API_KEY'i kontrol et |
| `pip install` hatası | `python -m pip install -r requirements.txt` kullan |

---

## DOSYA YAPISI

```
interview-assistant/
├── main.py                 ← Backend (buna dokunma)
├── audio_capture.py        ← Ses yakalama (buna dokunma)
├── transcriber.py          ← Whisper API (buna dokunma)
├── ai_responder.py         ← Claude API (buna dokunma)
├── candidate_profile.json  ← ★ HER BAŞVURUDA GÜNCELLE
├── .env                    ← ★ API KEY'LERİN (ilk seferde ayarla)
├── .env.example            ← .env şablonu
├── requirements.txt        ← Python bağımlılıkları
├── start.bat               ← Çift tıkla başlat
├── test_audio.py           ← Ses testi scripti
└── overlay/
    └── index.html          ← Overlay arayüzü (buna dokunma)
```
