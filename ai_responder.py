"""
Interview Assistant - Claude AI Cevap Üretici
Anthropic Claude API ile mülakatçının sorularına
mid-level İngilizce seviyesinde cevap üretir.
"""

import os
import json
import time
import logging
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("interview-assistant.ai_responder")

# ─── Anthropic istemcisi ───────────────────────────────────────
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ─── Ayarlar ───────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 200

# ─── Aday profili (başlangıçta yüklenir) ──────────────────────
_candidate_profile: dict = {}
_system_prompt: str = ""

# ─── Konuşma geçmişi (bağlam için) ────────────────────────────
_conversation_history: list = []
MAX_HISTORY = 10  # Son 10 soru-cevap çiftini tut


def load_profile(profile: dict):
    """
    Aday profilini yükle ve system prompt'u oluştur.
    main.py başlangıçta bu fonksiyonu çağırır.
    """
    global _candidate_profile, _system_prompt
    _candidate_profile = profile
    _system_prompt = _build_system_prompt(profile)
    logger.info("AI Responder profili yüklendi")


def _build_system_prompt(profile: dict) -> str:
    """
    Claude'a verilecek system prompt'u oluştur.
    Mid-level İngilizce seviyesi talimatları dahil.
    """
    # İş ilanı metnini düzgün stringe çevir
    job_posting = profile.get("job_posting", "")
    if isinstance(job_posting, list):
        job_posting = "\n".join(job_posting)
    
    # Başarıları listeye çevir
    achievements = profile.get("key_achievements", [])
    achievements_text = "\n".join(f"- {a}" for a in achievements)
    
    return f"""You are an interview response assistant helping {profile.get('name', 'Candidate')} answer questions in a live job interview.

== CANDIDATE PROFILE ==
Name: {profile.get('name', '')}
Current Role: {profile.get('current_role', '')}
Experience: {profile.get('experience', '')}
Skills: {profile.get('skills', '')}
Target Position: {profile.get('target_position', '')}
Target Company: {profile.get('target_company', '')}
Management Style: {profile.get('management_style', '')}
Why This Company: {profile.get('why_this_company', '')}

Key Achievements:
{achievements_text}

== JOB POSTING ==
{job_posting}

== ABSOLUTE RULES FOR ENGLISH LEVEL ==
The candidate is a NON-NATIVE speaker with INTERMEDIATE English (B1). This is the MOST IMPORTANT rule. If the answer sounds too fluent or polished, the interviewer will know AI is helping.

RESPONSE LENGTH:
- Maximum 2-4 sentences per answer. NEVER more than 4 sentences.
- Total answer must be under 60 words. This is a HARD LIMIT.
- One short paragraph only. NO multiple paragraphs.
- Say ONE main point, maybe add ONE example. That's it.

VOCABULARY:
- Use ONLY simple words a 12 year old would know
- BANNED words: leverage, utilize, facilitate, comprehensive, demonstrate, consistently, foster, scalable, robust, enhance, initiative, implement, optimize, collaborate, innovative, passionate, excellence, proficiency, expertise
- Use instead: use, make, help, build, work on, fix, good, big, small, fast, easy, hard, a lot, many, some
- Say "use" not "utilize". Say "build" not "architect". Say "help" not "facilitate". Say "make better" not "optimize".

SENTENCE STRUCTURE:
- Max 10 words per sentence. Short and choppy is GOOD.
- Use "I did X. Then I did Y." style. Not "Having done X, I proceeded to Y."
- Start with: "So...", "Well...", "Hmm...", "I mean...", "Let me think..."
- Use filler: "basically", "you know", "kind of", "like", "actually"

GRAMMAR - intentionally imperfect:
- Sometimes skip articles: "I worked on project" instead of "I worked on a project"  
- Occasionally use wrong preposition: "good in" instead of "good at"
- Use simple tenses: "I work" not "I have been working"
- Repeat a word sometimes: "It was... it was really good project"

== WRONG (too long, too perfect) ==
"Throughout my career, I've consistently demonstrated the ability to scale engineering organizations while maintaining technical excellence and fostering a culture of innovation. At my previous company, I successfully grew the team from 20 to 90 members while implementing microservices architecture."

== CORRECT (short, simple, natural B1 level) ==
"So basically... I managed teams for like 10 years. At my last company I grew team from 20 to 90 people. It was pretty hard but I learned a lot."

== ANOTHER CORRECT EXAMPLE ==
"Hmm, let me think... I used Python mostly for ML stuff and backend APIs. We built some services that process data. It worked good with our .NET systems."

== FORMAT ==
- Write as if YOU are the candidate speaking
- Give answer directly, no labels or meta text
- ONE paragraph, 2-4 sentences, under 60 words
- Match answer to job posting when relevant"""


async def generate_response(question: str) -> str:
    """
    Mülakatçının sorusuna mid-level İngilizce cevap üret.
    
    Args:
        question: Mülakatçının sorusu (transkript veya manuel giriş)
        
    Returns:
        Üretilen cevap metni. Hata durumunda hata mesajı.
    """
    global _conversation_history
    
    if not _system_prompt:
        logger.error("Profil henüz yüklenmedi! load_profile() çağrılmalı.")
        return "[HATA: Profil yüklenmedi]"
    
    try:
        start_time = time.time()
        
        # Konuşma geçmişini mesaj formatına çevir
        messages = []
        for entry in _conversation_history[-MAX_HISTORY:]:
            messages.append({"role": "user", "content": entry["question"]})
            messages.append({"role": "assistant", "content": entry["answer"]})
        
        # Yeni soruyu ekle
        messages.append({"role": "user", "content": question})
        
        # Claude API çağrısı
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=_system_prompt,
            messages=messages
        )
        
        # Cevabı çıkar
        answer = ""
        for block in response.content:
            if block.type == "text":
                answer += block.text
        
        answer = answer.strip()
        elapsed = time.time() - start_time
        
        logger.info(f"Claude cevap ({elapsed:.1f}s): {answer[:100]}...")
        
        # Geçmişe ekle
        _conversation_history.append({
            "question": question,
            "answer": answer
        })
        
        # Geçmiş çok uzadıysa eski kayıtları sil
        if len(_conversation_history) > MAX_HISTORY:
            _conversation_history = _conversation_history[-MAX_HISTORY:]
        
        return answer
    
    except Exception as e:
        logger.error(f"Claude API hatası: {e}")
        return f"[API Hatası: {str(e)[:100]}]"


def clear_history():
    """Konuşma geçmişini temizle (yeni mülakat için)."""
    global _conversation_history
    _conversation_history = []
    logger.info("Konuşma geçmişi temizlendi")


def test_claude():
    """Claude API bağlantısını test et."""
    import asyncio
    
    logger.info("Claude API test ediliyor...")
    
    # Test profili yükle
    test_profile = {
        "name": "Test",
        "current_role": "Developer",
        "experience": "5 years",
        "skills": "Python, JavaScript",
        "target_position": "Senior Developer",
        "target_company": "Test Corp",
        "key_achievements": ["Built a web app"],
        "management_style": "Collaborative",
        "why_this_company": "I like the company",
        "job_posting": "We need a Python developer with 5 years experience."
    }
    
    load_profile(test_profile)
    
    # Test sorusu
    async def run_test():
        answer = await generate_response("Tell me about yourself and your experience.")
        return answer
    
    answer = asyncio.run(run_test())
    
    if answer and not answer.startswith("["):
        logger.info(f"Claude cevap: {answer}")
        return True
    else:
        logger.error(f"Claude test başarısız: {answer}")
        return False


# ─── Doğrudan çalıştırma testi ─────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    
    print("=" * 40)
    print("  Claude API Bağlantı Testi")
    print("=" * 40)
    
    success = test_claude()
    
    if success:
        print("\n✓ Claude API çalışıyor!")
    else:
        print("\n✗ Claude API bağlantı hatası!")
        print("  .env dosyasındaki ANTHROPIC_API_KEY'i kontrol edin.")