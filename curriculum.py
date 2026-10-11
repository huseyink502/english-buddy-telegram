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


def lesson_for(day: int) -> dict:
    """Return a lesson by 1-based day number."""
    if not 1 <= day <= len(LESSONS):
        raise ValueError(f"Day must be 1..{len(LESSONS)}")
    return LESSONS[day - 1]


def all_words() -> list[tuple[str, str]]:
    return [word for lesson in LESSONS for word in lesson["words"]]


def render_lesson(day: int) -> str:
    lesson = lesson_for(day)
    words = "\n".join(f"• {en} — {tr}" for en, tr in lesson["words"])
    phrases = "\n".join(f"• {en}\n  {tr}" for en, tr in lesson["phrases"])
    dialogue = "\n".join(lesson["dialogue"])
    return (
        f"📚 GÜN {day}/7 — {lesson['title']}\n\n"
        f"🧩 Yeni kelimeler:\n{words}\n\n"
        f"💬 Cümle kalıpları:\n{phrases}\n\n"
        f"🎭 Mini diyalog:\n{dialogue}\n\n"
        "Şimdi /quiz ile kendini dene. /speak Hello ile telaffuzu dinle!"
    )
