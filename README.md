# 🚀 Botu çalıştır — Codex Cloud gerekmiyor

**İngilizce botunu başlatmak için tek bağlantı:**

**[Render'da English Buddy'yi kur](https://render.com/deploy?repo=https://github.com/huseyink502/english-buddy-telegram)**

Bu bağlantı, depodaki `render.yaml` dosyasını okuyup Telegram botunu bir **arka plan işçisi** olarak çalıştırmaya hazırlar.

1. Render hesabınla giriş yap ve önerilen servisi **onaylamadan önce ücretini kontrol et**.
2. Açılan gizli alanlara BotFather token'ını `TELEGRAM_BOT_TOKEN`, Google AI Studio anahtarını `GEMINI_API_KEY` olarak gir. Bu kodları **GitHub'a veya Codex sohbetine yazma**.
3. Ücretli servisi kabul ediyorsan deploy işlemini onayla. Hazır olunca Telegram botuna `/start` yaz.
4. İlk denemeden sonra botunun özel kalması için Telegram'da `/whoami` yazıp çıkan sayısal ID'yi Render servis ayarlarında `ALLOWED_USER_ID` olarak değiştir. Başlangıçtaki `0` değeri botun başkalarına da açık olduğu anlamına gelir.

**Ücret uyarısı:** Render background worker için ücretli çalışma planı gerekir (dosyada `0.5c-512mb` seçili). Kalıcı disk de ek ücretlidir. Gemini API kullanımı da kotaya ve tarifeye tabidir. Herhangi bir ödeme, kurulum linkini açmakla otomatik olarak yapılmaz; planı ve tutarı onaylamadan önce kontrol et.

**Durum:** Kod ve kurulum şablonu hazır; gizli anahtarlar henüz eklenmediği ve Render'da servis oluşturulmadığı için bot şu an çevrimiçi değildir. Codex Cloud'da gördüğün `unavailable` hatasını çözmene gerek yok.

---

# English Buddy — Telegram + Gemini İngilizce Öğretmeni

Bu proje, sıfırdan günlük İngilizce öğrenmek için **Codex Cloud ile geliştirilebilir** bir Telegram botu başlangıç sürümüdür.

## Özellikler (v0.1)

- 7 günlük başlangıç programı: her gün 5 kelime, 3 ifade ve mini diyalog
- Her ders için butonlu mini test
- SQLite ile kelime, gün ve sınav ilerlemesi kaydı
- 3/7/14/30 gün aralıklı basitleştirilmiş kelime tekrarları
- **Gemini API** ile genel soru-cevap ve basit İngilizce konuşma pratiği
- Telegram ses kaydını Gemini'ye göndererek transkripsiyon ve sınırlı telaffuz geri bildirimi
- `/speak Hello` komutuyla MP3 telaffuz dinleme (`gTTS` üzerinden)
- İsteğe bağlı `ALLOWED_USER_ID` kişisel kullanım kısıtlaması

**Henüz yapılmayanlar:** Otomatik günlük bildirim, 7 günden uzun dinamik müfredat, seviye belirleme, güvenilir fonetik puanlama, üretim ortamında yönetim ekranı. API ve gTTS çalışması internet gerektirir. Ses analizi eğitimsel geri bildirimdir, uzman fonetik ölçüm değildir.

## 1) Telegram bot token oluştur

1. Telegram içinde [@BotFather](https://t.me/BotFather) ile konuş.
2. `/newbot` gönder, ad ve `...bot` ile biten kullanıcı adı belirle.
3. Verdiği **token'ı asla GitHub'a gönderme ve sohbette paylaşma.**

## 2) Gemini API anahtarı oluştur

1. [Google AI Studio API Keys](https://aistudio.google.com/api-keys) sayfasını aç.
2. Ayrı bir **Gemini API anahtarı** oluştur.
3. Gemini Plus / Google AI aboneliği **tek başına bu bot için sınırsız API kullanımı sağlamaz**. Kullanım katmanını, kota ve varsa ücretleri AI Studio'dan kontrol et.

## 3) Kurulum (Python 3.11+)

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Windows'ta `cp` yerine `copy .env.example .env` veya dosya yöneticisini kullan.

`.env` dosyasındaki `TELEGRAM_BOT_TOKEN` ve `GEMINI_API_KEY` değerlerini doldur. Tokenları Codex Cloud'a kaynak kod olarak yazdırma; gerekiyorsa Codex secrets/environment mekanizmasını kullan.

**Önerilen:** Önce bot açıkken Telegram'da `/whoami` yazarak sayısal ID'ni öğren. Sonra `.env` içindeki `ALLOWED_USER_ID` alanına yazıp botu yeniden başlat. `0` kalırsa botu başkaları da kullanabilir; API kotanı harcayabilir.

## 4) Çalıştır

```bash
python bot.py
```

Telegram'da kendi botuna `/start` gönder. Bot açık kaldığı sürece cevap verir. Bilgisayar kapanırsa bot durur; 7/24 için çalışan bir sunucu gerekir. Codex Cloud geliştirme ortamı 7/24 hosting değildir.

## 5) Kullanım

| Komut | Açıklama |
| --- | --- |
| `/start` | Menü |
| `/lesson` | Mevcut günün kelimeleri, cümleleri, diyaloğu |
| `/quiz` | 5 soruluk mini test |
| `/review` | Zamanı gelen kelime tekrarları |
| `/chat` | Gemini ile çok basit İngilizce diyalog |
| `/ask` | Gemini'ye serbest soru |
| `/speak Hello, how are you?` | İngilizce sesli telaffuz MP3 |
| `/progress` | Öğrenme durumun |
| `/whoami` | Telegram kullanıcı ID'n (güvenlik ayarı için) |
| `/next` | Bir sonraki ders günü |

Telegram'dan **sesli mesaj** da gönderebilirsin; Gemini seni duyarak metin ve basit geri bildirim sunar.

## 6) Testler

```bash
python -m unittest discover -s tests -v
```

Testler Gemini veya Telegram hesabına bağlanmadan müfredat ve veri tabanını kontrol eder. Gerçek API uçtan uca testi için kendi anahtarların gerekir.

## 7) Codex Cloud ile sonraki işler

GitHub'a bir repo aç ve **yalnızca bu dosyaları** yükle. `.env` dosyasını asla yükleme.

Codex'e şunu yaz:

> Bu repo, Telegram + Gemini ile çalışan İngilizce öğretmeni botunun MVP'sidir. Önce dosyaları oku ve testleri çalıştır. Sıfırdan kodlayan birine Türkçe basit anlatım yap. Her değişikliği küçük commit'lere böl. Sonraki aşamada günlük otomatik hatırlatmalar, kullanıcı ayarlı çalışma saati, A1/A2 yeni müfredat, konuşma diyaloglarının güvenli kalıcı hafızası ve bulutta güvenli 7/24 deploy özellikleri ekle. API key'leri kodda veya commit'lerde saklama. Geriye dönük testleri koru.

## Barındırma uyarısı

`DB_PATH` değeri kalıcı disk üzerine ayarlanmazsa barındırma servislerinde veritabanı yeniden başlatmalarda kaybolabilir. Uzun süreli kullanım için bir kalıcı disk veya harici veritabanı gerekir. API billing uyarılarını ve kota sınırlarını kontrol et.
