# Günlük haber takibi — kuruluma hazırlık

Bu özellik henüz canlıya dağıtılmadı. Geliştirme dalı: feature/daily-news-digest.

GitHub Actions repository secrets:
- DATABASE_URL: Neon pooled PostgreSQL connection string
- TELEGRAM_BOT_TOKEN: mevcut Telegram bot token'ı
- GROQ_API_KEY: Groq API key (opsiyonel; başlık tabanlı yedek var)

Render Environment:
- DATABASE_URL: aynı Neon bağlantısı
- GROQ_API_KEY: Groq key (opsiyonel)
- GROQ_MODEL: openai/gpt-oss-120b (isteğe bağlı)

Bot komutları:
/ozet, /ozet_ac, /ozet_kapat, /takip, /gelismeler gta6

GitHub Actions her saat UTC 17. dakikada tarama yapar. Türkiye saati
09.00'dan sonraki ilk başarılı çalışmada, yalnızca açıkça abone olmuş
kullanıcıya günlük özet gönderilir. Scheduled workflow gecikebilir.

Devreye almadan önce:
1. Neon projesi oluşturup DATABASE_URL'yi bağla.
2. GitHub Actions secrets'ı kaydet.
3. Testleri çalıştır, Actions'ı manuel çalıştırıp kayıtları doğrula.
4. Render test ortamında komutları dene.
5. Sonra geliştirme dalını main'e birleştir.

Not: RSS tam haber metni değildir. Başlık benzerliği her zaman aynı olay
demek değildir; kesin tarih ve iddialar kaynaklara göre açıklanmalıdır.
