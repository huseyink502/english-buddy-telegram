"""Owner-supplied disclosure, not an automatic claim of legal compliance."""

import os

NOTICE_VERSION = "2026-10-14"


def default_recording_ready() -> bool:
    # Classroom deployment requested by the owner. Disclosure and user choice
    # remain mandatory; optional policy fields never create a legal guarantee.
    return os.getenv("TRANSCRIPT_DEFAULT_ENABLED", "true").strip().lower() == "true"


def notice_text() -> str:
    controller = os.getenv("PRIVACY_CONTROLLER", "Karamaz Akademi bot yöneticisi")[:300]
    contact = os.getenv(
        "PRIVACY_CONTACT",
        "Bot üzerinden /gizlilik; yönetici iletişimi henüz tanımlanmadı",
    )[:300]
    basis = os.getenv(
        "PRIVACY_LEGAL_BASIS",
        "Deneysel ders kurulumu; veri sorumlusu ayrıca bir hukuki dayanak belirtmemiştir",
    )[:600]
    return (
        "🔐 Karamaz Akademi · Gizlilik bildirimi\n\n"
        f"Veri sorumlusu: {controller}\nBaşvuru/iletişim: {contact}\n"
        "Telegram ID, ad, kullanıcı adı ve etkinlik tarihleri hizmet ve destek için işlenir. "
        "Bu bildirimden SONRA gönderdiğin metinler ve AI yanıtları, kayıt açıksa "
        "güvenlik ve destek amacıyla en fazla 30 gün saklanır; yalnızca bot sahibi inceleyebilir. "
        f"Varsayılan metin kaydı için bildirilen işleme şartı: {basis}.\n\n"
        "Mesajlar yanıt üretmek için Telegram ve Gemini/Groq hizmetlerine iletilir; "
        "bu sağlayıcılar yurt dışında veri işleyebilir. Ses dosyaları admin arşivine alınmaz. "
        "Eski Telegram geçmişi geriye dönük alınamaz. Şifre, API anahtarı veya hassas bilgi paylaşma.\n\n"
        "/gizlilik ile kaydı durdurabilir, kayıtlarını silebilir ve duyuru iznini yönetebilirsin. "
        "Kaydı aç butonu isteğe bağlı kayıt iznini verir; istediğin zaman geri alabilirsin. "
        "KVKK kapsamındaki bilgi alma, düzeltme, silme ve itiraz başvurularını veri sorumlusuna iletebilirsin. "
        "Kayıt kapalıyken dersler ve AI çalışır. Duyurular ve günlük özetler ayrı izin gerektirir.\n\n"
        "Bu ilk mesaj kaydedilmedi. Menüyü açmak için /start; sorunu iletmek için yeniden yaz."
    )
