# 🇬🇧 English Buddy — ücretsiz Telegram + Gemini İngilizce öğretmeni

Sıfırdan gündelik İngilizce öğrenmek için geliştirilen Telegram botu. 7 günlük dersler,
kelime sınavları, tekrarlama, sesli telaffuz, Gemini'yle Türkçe soru-cevap ve basit
İngilizce sohbet özellikleri içerir.

## 🚀 Ücretsiz Render kurulum — Codex Cloud gerekmez

**[Ücretsiz Render üzerinde kur](https://render.com/deploy?repo=https://github.com/huseyink502/english-buddy-telegram)**

1. Açılan Render sayfasında giriş yap veya hesap oluştur.
2. Blueprint'te yalnızca **Free / $0** web hizmetini onayla. Ücretli plan seçme.
3. Gizli alanlara iki değeri yapıştır:
   - `TELEGRAM_BOT_TOKEN` → Telegram [@BotFather](https://t.me/BotFather) bot token'ı
   - `GEMINI_API_KEY` → [Google AI Studio](https://aistudio.google.com/api-keys) API anahtarın
4. **Apply / Deploy** düğmesine bas; durumun **Live** olmasını bekle.
5. Telegram'da kendi botuna `/start` gönder. Ardından `/lesson` ve `/ask` dene.

**Önemli:** Bu gizli anahtarları GitHub'a, Codex sohbetine veya ekran görüntülerine yazma.
Eğer eskiden başka bir yerde botun polling modunu çalıştırdıysan kapat; aynı bot token'ı
ile farklı çalışan kopyalar çakışabilir. Yeni sistem `webapp.py` ile webhook'u
**kendisi kaydeder**; elle Telegram setWebhook URL'si girmen gerekmez.

### Ücretsiz planın gerçek sınırlamaları

- Render Free web servisi 15 dakika gelen istek olmazsa uyur. Sonraki Telegram
  mesajı servisi uyandırır; yanıt yaklaşık 1 dakika veya daha uzun gecikebilir.
  Telegram'ın tekrar denemesi sınırlı olduğundan bazı mesajlar hiç ulaşmayabilir.
- Render Free sunucunun yerel SQLite dosyası uyuma, yeniden başlama ve yeniden
  dağıtımda silinir. **Kalıcı öğrenme ilerlemesi için aşağıdaki Neon adımı gerekir.**
- Gemini API'nin ücretsiz bir kotası vardır; Google AI abonelikleri ayrı değerlendirilir.
- Render'ın ücretsiz kullanım saatleri ve bant genişliği sınırları vardır. Ödeme
  yöntemi eklenmişse limit aşımında ücret oluşabilir. Hesabın faturalandırma ve
  harcama ayarlarını kontrol et.

## 💾 Kalıcı ücretsiz ilerleme — Neon Postgres (önerilir)

Sunucu açıldıktan sonra ders gününün ve kelime tekrarlarının kaybolmaması için:

1. [Neon](https://console.neon.tech/) üzerinde **Free** proje oluştur.
2. Neon'un **pooled connection string** değerini (`postgresql://...`) kopyala.
   Bağlantı şifresini kimseyle paylaşma.
3. Render'da servisini aç, **Environment** bölümüne yeni gizli değişken ekle:
   - **Key**: `DATABASE_URL`
   - **Value**: Neon pooled PostgreSQL bağlantı adresinin tamamı
4. Değişikliği kaydet ve servisi yeniden başlat / deploy et.

Bot `DATABASE_URL` tanımlandığında otomatik PostgreSQL'e geçer, tablolarını
oluşturur; ekstra SQL komutu gerekmez. Bu adımı yapmazsan bot geçici SQLite ile
çalışır, ama ilerlemen Render uyandığında veya yeniden başladığında silinir.
Neon'un da ücretsiz kaynak limitleri ve ölçeğe sıfırlama koşulları vardır.

**Önemli:** Neon'u sonradan bağlarsan önceki geçici SQLite ilerlemesi
otomatik aktarılmaz. En iyisi derslere başlamadan önce eklemektir.

## 🔒 Yalnızca kendin kullan

İlk açılışta `/whoami` gönder ve Telegram sayısal kullanıcı ID'ni öğren.
Render → Environment kısmında `ALLOWED_USER_ID` alanındaki `0` yerine kendi
ID'ni yaz; kaydet ve yeniden deploy et. `0` kaldığı sürece botu bulan diğer
Telegram kullanıcıları da Gemini API kotanı harcayabilir.

## 📰 Güncel haberler ve Gemini'ye haber soruları

Telegram sohbetinde `/` tuşuna bastığında komut listesi görünür. Menü bot her başlatıldığında
`setMyCommands` ile otomatik kaydedilir.

- `/haberler` veya `/turkiye`: Türkiye gündeminden en yeni haber başlıklarını gösterir.
- `/siyaset`: Türkiye siyaseti, siyasi partiler, hükümet ve muhalefet haberleri.
- `/tbmm`: TBMM ve Meclis gündemi.
- `/sondakika`: Türkiye son dakika gelişmeleri.
- `/oyun`: Oyun dünyasından genel haberler.
- `/brawlstars`: Brawl Stars güncellemeleri ve etkinlik haberleri.
- `/gta6`: GTA 6 ve Grand Theft Auto VI ile ilgili güncel haberler.
- Her kategoride son 8 haber başlığını, haberin yayıncısını ve tarihini gösterir.
- Butonlarla **Türkiye, Siyaset, Türkiye Son Dakika, TBMM, TRT Son Dakika, Gündem, Dünya, Ekonomi, Teknoloji, BBC Türkçe, Oyun Gündemi, Brawl Stars ve GTA 6** arasında geçiş yapılabilir.
- Haber butonuna basınca ilgili **başlık, RSS özeti, kaynak bağlantısı ve yayın tarihi** açılır.
- Seçtikten sonra normal mesaj yazarak Gemini'ye o haber hakkında soru sorarsın;
  `/ask` komutuyla yeniden genel yapay zekâ sohbetine geçersin.
- Türkiye ve siyaset haberlerinde farklı yayıncıların başlıkları **Google Haberler RSS** üzerinden toplanır;
  her başlığın gerçek yayıncı adı ayrıca gösterilir. Genel haberler ayrıca TRT Haber ve BBC Türkçe
  RSS kaynaklarından gelir.
- Oyun Gündemi, Brawl Stars ve GTA 6 kategorileri de Google Haberler RSS araması kullanır.
  Bu kategoriler haber niteliğinde içerik toplar; doğrulanmamış söylentiler de çıkabilir.
- Google Haberler'in RSS arama akışları resmi bir API değildir; formatı değişebilir. Haberler farklı
  yayıncılardan geldiği için iddiaları karşılaştır, gerekirse kaynak bağlantısını aç.
  Kaynaklar zaman zaman erişilemeyebilir veya haber özetleri yetersiz olabilir.
- **Gemini tam haber metnini otomatik olarak okumaz; sadece RSS başlık ve özetini kullanır.**
  Bilgi özette yoksa bunu söylemesi beklenir; yanlış veya eksik yanıt olasılığı vardır.
- İstekler her iki dakikada bir güncellenen küçük bir önbellekten yararlanır.
- Ücretsiz Render uyuduğunda seçili haberle sohbet bağlamı sıfırlanabilir;
  `/haberler` üzerinden tekrar haber seçebilirsin.

**Kullanıcı güvenliği:** Herkese açık botta Gemini API kullanımını diğer kullanıcılarla
paylaşırsın. Sınırsız kullanım hedeflenmemelidir; API kota/harcamalarını izle.

## 🔧 Bot komutları

| Komut | İşlev |
|---|---|
| `/start` | Menü ve kullanım açıklaması |
| `/haberler`, `/turkiye` | Türkiye gündemini gör ve haber seç |
| `/siyaset` | Türkiye siyaseti haberlerini gör |
| `/tbmm` | TBMM ve Meclis haberlerini gör |
| `/sondakika` | Türkiye son dakika haberlerini gör |
| `/oyun` | Genel oyun gündemini gör |
| `/brawlstars` | Brawl Stars haberlerini gör |
| `/gta6` | GTA 6 haberlerini gör |
| `/lesson` | Günün 5 kelimesi, 3 cümlesi ve diyalog |
| `/quiz` | Çoktan seçmeli test |
| `/review` | Aralıklı kelime tekrarı |
| `/chat` | Gemini ile başlangıç seviyesi İngilizce sohbet |
| `/ask` | Gemini'ye istediğin soruyu sor |
| `/speak hello` | Sesli İngilizce telaffuz |
| `/progress` | Öğrenme ilerlemesi |
| `/next` | Sonraki ders |
| `/whoami` | Telegram kullanıcı ID'n |

Telegram sesli mesajlarını Gemini analiz edebilir; erişilebilirlik ve doğruluk
modele ve API kotasına bağlıdır.

## 🧑‍💻 Yerel geliştirme

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env içinde iki gizli API anahtarını doldur
python bot.py                  # bilgisayarda polling modu
```

Windows'ta sanal ortamı `.venv\\Scripts\\activate` ile etkinleştir.
Render'da `python bot.py` **kullanılmaz**; `render.yaml` dosyasında
`uvicorn webapp:app --host 0.0.0.0 --port $PORT` çalışır ve Telegram webhook'u
HTTPS üzerinden otomatik kaydeder.

Yerel webhook denemesi için `WEBHOOK_BASE_URL=https://domain.example` ve gerçek
HTTPS erişimi gerekir. Webhook aktifken aynı token ile yerel polling başlatma.

## 🧪 Test

```bash
python -m unittest discover -s tests -v
```

**Not:** Testler temel ders/veritabanı işlevlerini ve webhook yardımcılarını
doğrular; gerçek Telegram/Gemini API testi ancak senin gizli anahtarlarınla
canlı Render ortamında yapılabilir. Bu repo API anahtarları içermez.

## Proje dosyaları

- `bot.py`: Telegram komutları, dersler, testler, polling modu
- `webapp.py`: Render Free için FastAPI Telegram webhook uç noktası
- `ai.py`: Gemini öğretmen ve ses değerlendirmesi
- `db.py`: Geçici SQLite ilerlemesi
- `postgres_db.py`: Kalıcı Neon/Postgres ilerlemesi
- `render.yaml`: **Ücretsiz** Render web servisi ve güvenli anahtar girişleri
- `news.py`: RSS haberleri, kategoriler, yayın tarihi ve linkler
- `curriculum.py`, `quiz.py`, `tests/`: Dersler, testler ve kontroller


## 🗞️ Ortak haber hafızası ve günlük özet (yeni)

Bu özellikler Neon `DATABASE_URL` tanımlandıktan ve GitHub Actions sırları
ayarlandıktan sonra etkinleşir. Render Free uykuda olsa da GitHub Actions
RSS akışlarını saatte bir kontrol eder; çalıştırmalar birkaç dakika gecikebilir.

- `/ozet_ac`: Kullanıcı adına **günlük bildirim izni** verir; ilk bildirim,
  Türkiye saatiyle 09.00'dan sonraki uygun taramada gönderilir.
- `/ozet_kapat`: Günlük bildirimi durdurur.
- `/takip`: GTA 6, Brawl Stars, Türkiye siyaseti, Teknoloji ve Dünya
  kategorilerini açıp kapatır (en az bir kategori açık kalmalı).
- `/ozet`: Son hazırlanmış günlük özeti gösterir.
- `/gelismeler gta6`: Veritabanında kayıtlı son haberleri seçilebilir gösterir.
  Diğer kodlar: `brawlstars`, `siyaset`, `teknoloji`, `dunya`.
- `GROQ_API_KEY` Render üzerinde ayarlanırsa **seçilen haberle serbest Türkçe
  sohbetlerde** Groq GPT-OSS 120B denenir; hata olursa Gemini'ye dönülür.
  Haber arşivi üzerinden aynı kategorideki yakın tarihli başlıklar da bağlama
  eklenir. Haber metninin tamamı değil RSS başlık/özetleri bilinir.
- Özet oluşturulurken Groq erişilemezse kaynak bağlantılı başlıklar kullanılır.

### Kurulum

1. Neon üzerinde PostgreSQL oluştur ve pooled `postgresql://...` bağlantısını al.
2. Render `english-buddy-telegram` → Environment bölümüne:
   - `DATABASE_URL` = Neon pooled bağlantısı
   - `GROQ_API_KEY` = Groq API anahtarı (isteğe bağlı, ancak önerilir)
3. GitHub deposu → Settings → Secrets and variables → Actions altında
   **Repository secrets** olarak ekle:
   - `DATABASE_URL` = Aynı Neon bağlantısı
   - `TELEGRAM_BOT_TOKEN` = Var olan BotFather token'ı
   - `GROQ_API_KEY` = Groq anahtarı (isteğe bağlı)
4. GitHub Actions → **Hourly news archive and daily digest** → Run workflow
   komutuyla ilk taramayı manuel çalıştırıp kayıtların oluştuğunu kontrol et.
5. Telegram'da `/ozet_ac`, `/takip` ve `/ozet` komutlarını dene.

`GROQ_API_KEY` ve diğer anahtarları **asla GitHub kaynak dosyalarına,
commit mesajlarına veya ekran görüntülerine yazma**.

### Sınırlar ve güvenlik

- Botun tüm haberleri toplaması kullanıcıların kişisel sohbetlerini saklamaz.
  Yalnızca açıkça /ozet_ac yapan kullanıcıların Telegram kullanıcı ID'si
  ve kategori tercihleri kalıcı saklanır.
- İlk sürüm aynılaştırılmış haber başlıklarını tekrar olarak değerlendirir;
  farklı başlıklarla anlatılan aynı olayı kusursuz birleştirdiğini iddia etmez.
- Haberleri Google Haberler RSS üzerinden toplamak resmi bir API garantisi
  değildir. Resmî oyun duyurularını ve politik haberleri kaynağından doğrula.
- Planlanan saatler kesin değildir. GitHub Actions zamanlanmış görevleri
  gecikebilir; 60 gün aktif olmayan açık depolarda schedule devre dışı kalabilir.
- Bildirim teslimatında PostgreSQL kayıtları tekrarları azaltır; Telegram'ın
  gönderip kayıt öncesinde hata vermesi gibi istisnalarda tekrar teslim mümkündür.
- Ücretsiz Groq, GitHub Actions, Render ve Neon planlarının her birinde
  kota/limit vardır.


## 🔐 Admin paneli (Web + Telegram)

Yalnızca bot sahibi erişebilir. Varsayılan olarak **yönetim kapalıdır**.
Render → Environment bölümüne aşağıdaki iki değişkeni ekleyin:

- `ADMIN_USER_ID`: Telegram'da `/whoami` komutundan öğrendiğiniz **kendi sayısal ID'niz**; `ALLOWED_USER_ID` ile karıştırmayın. `ADMIN_USER_ID=0` iken Telegram'daki admin komutları kapalıdır.
- `ADMIN_WEB_PASSWORD`: En az **20 karakterlik, benzersiz ve güçlü** parola. Telegram mesajı veya kod dosyasında paylaşmayın. Parolayı bir parola yöneticisi ile üretmek önerilir.

`ADMIN_PANEL_ENABLED=true` değişkeni panelin ayrıca etkinleştirilmesini sağlar. False veya eksikse web admin sayfası kapalı kalır.

Mevcut `DATABASE_URL` Neon bağlantısı kullanılacaktır; ikinci bir veritabanı gerekmez.
Ayarları kaydedip Render dağıtımı tamamlanınca:
- Web paneli: `https://english-buddy-telegram.onrender.com/admin`
- Telegram: `/admin`, `/admin_kullanicilar`, `/admin_sohbet <TelegramID>`,
  `/admin_duyuru <Duyuru metni>`

**Bildirim izni varsayılan olarak kapalıdır.** Kullanıcı `/duyuru_ac` yazarsa yönetici
duyurusu alabilir; `/duyuru_kapat` ile vazgeçer. Haber bildirimi
`/ozet_ac` izninden tamamen ayrıdır. Kullanıcıların
`/start` komutu kullanması, yönetici duyurusuna otomatik abone yapmaz.

**Sohbet kayıtları:** Yeni kullanıcılarda bot, ilk etkileşimde mesaj içeriğinin
güvenlik ve destek amacıyla bot sahibi tarafından incelenmek üzere en fazla 30 gün
saklanabileceğini açıkça bildirir. **Bu ilk mesaj arşivlenmez.** Bildirim
Telegram üzerinden başarıyla iletildikten sonra sonraki metin mesajları ve
AI yanıtları saklanır; komut metinleri, ses dosyaları ve API anahtarları
kaydedilmez. Daha önceki sürümde kayıt tercihi bulunan mevcut kullanıcıların
tercihleri (açık veya kapalı) **değiştirilmez**. Bunun nedeni önceki kapalı
durumun açık bir devre dışı bırakma tercihi olup olmadığının bilinememesidir.
Bu kullanıcılar isterlerse kaydı sonradan kendileri açabilir.

Komut menüsünde yalnızca \`/gizlilik\` bulunur. Bu ekranda kayıt durumunu
gösteren **Kaydı aç**, **Kaydı durdur ve geçmişi sil** ve **Kayıtlarımı sil**
butonları vardır. Önceki \`/kayit_ac\`, \`/kayit_kapat\`, \`/kayit_sil\` komutları
eski bağlantılar bozulmasın diye çalışmaya devam eder fakat Telegram'ın görünür
komut menüsünden kaldırılmıştır. Kayıt kontrolü kullanıcıya aittir.

Kayıtlar 30 gün sonra erişilemez, düzenli kullanıcı etkileşimlerinde temizlenir;
hiç etkinlik olmayan dönemlerde otomatik zamanlı silmenin ayrıca planlanması
gerekir. Telegram geçmiş mesajlarını geriye dönük topluca sunmaz.
Kullanıcı ID'si, kullanıcı adı ve son etkinlik zamanı yönetim amaçlı saklanır.

**Önemli hukukî not:** Mesaj içeriklerinin varsayılan olarak işlenmesi için,
KVKK kapsamında amaca uygun bir işleme şartı, açık aydınlatma metni,
veri minimizasyonu ve saklama süresi değerlendirilmelidir. Sırf botun sahibi
olmak, tüm mesaj içeriklerini sınırsız saklama yetkisi vermez.
Özellikle hassas içerikler için varsayılan kayıt yerine kullanıcı onaylı
yaklaşım gerekebilir.

Web paneli; HTTPS üzerinde imzalı, HttpOnly/Secure/SameSite=Strict çerez,
CSRF doğrulaması ve temel başarısız giriş sınırı kullanır. `/admin` yolu
Render'da HTTPS ile açılmalıdır; API anahtarı veya yönetici parolası
URL parametresi olarak eklenmemelidir. Tüm gönderilen duyurular yalnızca
mevcut izni olan kullanıcılara yollanır. Botu engelleyen kullanıcıya
Telegram mesajı ulaşmaz.

Güvenlik notu: Parola tabanlı bu ilk sürümde çok faktörlü doğrulama ve
merkezî, kalıcı IP sınırlaması bulunmamaktadır. Daha büyük kamuya açık bot
için Telegram kimlik doğrulaması/2FA ve ayrı bir görev kuyruğu eklenmelidir.
