"""Gemini-backed teaching, free-form Q&A and voice-note analysis."""

import os
from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

TEACHER_PROMPT = """Sen English Buddy adlı sabırlı ve pratik bir İngilizce öğretmenisin.
Öğrenci A0 seviyesinde, Türkçe biliyor. Günlük hayatta kullanılan İngilizceyi öğret.
Kısa, doğru ve motive edici cevaplar ver. İngilizce cümleleri basit tut.
Öğrenci 'neden' veya 'detaylı anlat' derse Türkçe ve örneklerle ayrıntılı açıkla.
Yanlış İngilizce yazdığında düzelt, nedenini söyle, basit bir doğru örnek göster.
Önce doğrudan sorusunu yanıtla; öğrenci soru sorarsa cevap vermeden test yaptırma.
Bilmediğin şeyi uydurma. Dersler dışında genel soruları da yanıtlayabilirsin.
"""

CHAT_PROMPT = TEACHER_PROMPT + """
Şimdi İngilizce konuşma pratiği yapıyorsunuz. Öğrenciye tek seferde 1 basit
İngilizce soru sor, Türkçe ipucu ekle. Cevabındaki hataları nazikçe düzelt.
Konuşma seviyesini A0/A1'de tut.
"""


class GeminiTeacher:
    def __init__(self, api_key: str) -> None:
        self.client = genai.Client(api_key=api_key)

    async def reply(self, message: str, history: list[tuple[str, str]], practice: bool = False) -> str:
        contents = [types.Content(role=role, parts=[types.Part.from_text(text=txt)])
                    for role, txt in history[-10:]]
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        response = await self.client.aio.models.generate_content(
            model=MODEL, contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=CHAT_PROMPT if practice else TEACHER_PROMPT,
                max_output_tokens=750,
            ),
        )
        return response.text or "Bu kez yanıt oluşturamadım. Tekrar dener misin?"

    async def analyse_voice(self, audio: bytes) -> str:
        response = await self.client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_text(text=(
                    "Bu, sıfırdan İngilizce öğrenen Türkçe konuşan bir öğrencinin ses kaydı. "
                    "Önce söylediklerini mümkün olduğunca yazıya dök. "
                    "Sonra doğru bir İngilizce karşılık ve çok kısa telaffuz önerisi sun. "
                    "Ses kaydı İngilizce değilse bunu belirt. Sadece duyduğun şeylere dayan. "
                    "Kesin sayısal telaffuz puanı verme."
                )),
                types.Part.from_bytes(data=audio, mime_type="audio/ogg"),
            ],
            config=types.GenerateContentConfig(
                system_instruction=TEACHER_PROMPT, max_output_tokens=750,
            ),
        )
        return response.text or "Sesini çözümleyemedim; bir kez daha dener misin?"
