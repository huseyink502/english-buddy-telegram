"""Short beginner lessons; plain data makes it easy to extend with Codex."""

LESSONS = [
    {
        "title": "Selamlaşma",
        "words": [
            ("Hello", "Merhaba"), ("Goodbye", "Hoşça kal"),
            ("Please", "Lütfen"), ("Thank you", "Teşekkür ederim"),
            ("Yes", "Evet"),
        ],
        "phrases": [
            ("Hello! How are you?", "Merhaba! Nasılsın?"),
            ("I'm fine, thank you.", "İyiyim, teşekkür ederim."),
            ("See you later!", "Sonra görüşürüz!"),
        ],
        "dialogue": [
            "A: Hello! How are you?", "B: I'm fine, thank you. And you?",
            "A: I'm good! See you later!",
        ],
    },
    {
        "title": "Kendini tanıtma",
        "words": [
            ("Name", "İsim"), ("Student", "Öğrenci"),
            ("From", "-den/-dan"), ("Nice", "Güzel / memnun"),
            ("Meet", "Tanışmak"),
        ],
        "phrases": [
            ("My name is Ali.", "Benim adım Ali."),
            ("I am a student.", "Ben bir öğrenciyim."),
            ("Nice to meet you.", "Tanıştığıma memnun oldum."),
        ],
        "dialogue": [
            "A: Hi! What's your name?", "B: My name is Ali. What's yours?",
            "A: I'm Emma. Nice to meet you!",
        ],
    },
    {
        "title": "Günlük ihtiyaçlar",
        "words": [
            ("Water", "Su"), ("Food", "Yemek"),
            ("Help", "Yardım"), ("Want", "İstemek"),
            ("Need", "İhtiyaç duymak"),
        ],
        "phrases": [
            ("I want some water.", "Biraz su istiyorum."),
            ("I need help.", "Yardıma ihtiyacım var."),
            ("I'm hungry.", "Açım."),
        ],
        "dialogue": [
            "A: Do you need help?", "B: Yes, please. I need water.",
            "A: Here you go!",
        ],
    },
    {
        "title": "Basit sorular",
        "words": [
            ("What", "Ne"), ("Where", "Nerede"),
            ("When", "Ne zaman"), ("Who", "Kim"),
            ("How", "Nasıl"),
        ],
        "phrases": [
            ("What is this?", "Bu ne?"),
            ("Where are you?", "Neredesin?"),
            ("How are you?", "Nasılsın?"),
        ],
        "dialogue": [
            "A: What is this?", "B: It's my book.",
            "A: Where is your bag?", "B: It's here.",
        ],
    },
    {
        "title": "Kafede sipariş",
        "words": [
            ("Coffee", "Kahve"), ("Tea", "Çay"),
            ("Menu", "Menü"), ("Bill", "Hesap"),
            ("Small", "Küçük"),
        ],
        "phrases": [
            ("Can I have a coffee?", "Bir kahve alabilir miyim?"),
            ("The menu, please.", "Menüyü alabilir miyim, lütfen?"),
            ("Can I have the bill?", "Hesabı alabilir miyim?"),
        ],
        "dialogue": [
            "A: Hello! What would you like?", "B: A small tea, please.",
            "A: Here you are. Enjoy!",
        ],
    },
    {
        "title": "Günlük konuşma",
        "words": [
            ("Today", "Bugün"), ("Tomorrow", "Yarın"),
            ("Happy", "Mutlu"), ("Tired", "Yorgun"),
            ("Busy", "Meşgul"),
        ],
        "phrases": [
            ("How was your day?", "Günün nasıldı?"),
            ("I am a little tired.", "Biraz yorgunum."),
            ("See you tomorrow!", "Yarın görüşürüz!"),
        ],
        "dialogue": [
            "A: How was your day?", "B: Good, but I'm tired.",
            "A: Have a nice evening!",
        ],
    },
    {
        "title": "Genel tekrar",
        "words": [
            ("Learn", "Öğrenmek"), ("Speak", "Konuşmak"),
            ("Listen", "Dinlemek"), ("Practice", "Pratik yapmak"),
            ("Again", "Tekrar"),
        ],
        "phrases": [
            ("I am learning English.", "İngilizce öğreniyorum."),
            ("Please speak slowly.", "Lütfen yavaş konuş."),
            ("Can you say that again?", "Bunu tekrar söyleyebilir misin?"),
        ],
        "dialogue": [
            "A: Do you speak English?", "B: A little. I am learning!",
            "A: Great! Let's practice together.",
        ],
    },
]


# Extra guidance for absolute beginners. Each dialogue line gets a Turkish translation.
LESSON_GUIDANCE = {
    1: {
        "tip": "I am = I'm (ben ...im); How are you? = Nasılsın?",
        "dialogue_tr": [
            "A: Merhaba! Nasılsın?",
            "B: İyiyim, teşekkür ederim. Ya sen?",
            "A: Ben de iyiyim! Sonra görüşürüz!",
        ],
        "task": "İngilizce 'Merhaba, nasılsın?' yazmayı dene.",
    },
    2: {
        "tip": "My name is ... = Benim adım ...; I'm = I am.",
        "dialogue_tr": [
            "A: Selam! Adın ne?",
            "B: Benim adım Ali. Seninki ne?",
            "A: Ben Emma. Tanıştığıma memnun oldum!",
        ],
        "task": "Kendi adını ve öğrenci olduğunu iki İngilizce cümleyle yaz.",
    },
    3: {
        "tip": "I want = istiyorum; I need = ihtiyacım var.",
        "dialogue_tr": [
            "A: Yardıma ihtiyacın var mı?",
            "B: Evet, lütfen. Suya ihtiyacım var.",
            "A: Buyur!",
        ],
        "task": "I want ... ile bir ihtiyaç cümlesi kur.",
    },
    4: {
        "tip": "What = ne; Where = nerede; sorularda genellikle is/are kullanılır.",
        "dialogue_tr": [
            "A: Bu ne?",
            "B: Bu benim kitabım.",
            "A: Çantan nerede?",
            "B: Burada.",
        ],
        "task": "What is this? sorusuna basit bir cevap yaz.",
    },
    5: {
        "tip": "Can I have ...? = ... alabilir miyim? Kibar sipariş için kullanılır.",
        "dialogue_tr": [
            "A: Merhaba! Ne istersiniz?",
            "B: Küçük bir çay, lütfen.",
            "A: Buyurun. Afiyet olsun!",
        ],
        "task": "Can I have ...? ile bir sipariş cümlesi yaz.",
    },
    6: {
        "tip": "How was your day? geçmiş bir günü sorar; I'm tired = Yorgunum.",
        "dialogue_tr": [
            "A: Günün nasıldı?",
            "B: İyiydi ama yorgunum.",
            "A: İyi akşamlar!",
        ],
        "task": "I'm ... kalıbıyla bugün nasıl hissettiğini yaz.",
    },
    7: {
        "tip": "I am learning = Öğreniyorum; Can you ...? = ... yapabilir misin?",
        "dialogue_tr": [
            "A: İngilizce konuşuyor musun?",
            "B: Biraz. Öğreniyorum!",
            "A: Harika! Birlikte pratik yapalım.",
        ],
        "task": "I am learning English. cümlesini yaz, sonra /chat ile konuşmaya başla.",
    },
}


def lesson_for(day: int) -> dict:
    """Return a lesson by 1-based day number."""
    if not 1 <= day <= len(LESSONS):
        raise ValueError(f"Day must be 1..{len(LESSONS)}")
    return LESSONS[day - 1]


def all_words() -> list[tuple[str, str]]:
    return [word for lesson in LESSONS for word in lesson["words"]]


def render_lesson(day: int) -> str:
    lesson = lesson_for(day)
    guidance = LESSON_GUIDANCE[day]
    words = "\\n".join(f"• {en} — {tr}" for en, tr in lesson["words"])
    phrases = "\\n".join(f"• {en}\\n  ↳ {tr}" for en, tr in lesson["phrases"])
    dialogue = "\\n".join(
        f"{english}\\n  ↳ {turkish}"
        for english, turkish in zip(lesson["dialogue"], guidance["dialogue_tr"])
    )
    return (
        f"📚 GÜN {day}/{len(LESSONS)} — {lesson['title']}\\n\\n"
        f"🧩 Yeni kelimeler:\\n{words}\\n\\n"
        f"💬 Cümle kalıpları:\\n{phrases}\\n\\n"
        f"🧠 Küçük dil bilgisi notu:\\n{guidance['tip']}\\n\\n"
        f"🎭 Mini diyalog (çevirili):\\n{dialogue}\\n\\n"
        f"✍️ Mini alıştırma:\\n{guidance['task']}\\n\\n"
        "Hazır olunca /quiz ile kendini dene. /speak Hello ile telaffuzu dinle!"
    )
