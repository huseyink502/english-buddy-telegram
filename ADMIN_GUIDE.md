# Karamaz Akademi yönetimi

Web paneli `/admin`; Telegram yönetimi `/admin`. Haber, ders, günlük özet,
Gemini/Groq ve mevcut webhook aynı uygulamada çalışır.

## İncelemede bulunan sorunlar

- Eski kullanıcılar önceki tercihler bilinmediği için kayıt kapalı tutuluyordu.
  Bu davranış korunur; yöneticinin görünür kayıt beklentisi kullanıcı tercihini değiştirmez.
- Panel yalnızca son 40 mesajı gösteriyor, tüm sayfayı yeniliyor ve arama sunmuyordu.
- Bildirim kontrolü yalnızca uygulamanın işleme sırasına dayanıyordu: bildirimden
  önce yazılıp Telegram kuyruğunda bekleyen mesajlar sonradan kayda girebiliyordu.
- İlk `/start` aydınlatma sonrası durduruluyor, kullanıcı ana menüyü alamıyordu.
- Parola çerezi sunucuda iptal edilmiyordu; çıkış sonrası kopyalanmış çerez kullanılabilirdi.
- Giriş deneme sayacı bellekteydi; yeniden başlatmada kayboluyordu. Login CSRF,
  ikinci doğrulama adımı ve admin denetim kaydı bulunmuyordu.
- Duyurular web isteği/Telegram handler'ı içinde tamamlanıyordu; sunucu uyursa
  kalan alıcılar kayboluyordu. Rate limit ve belirsiz teslim ayrımı yoktu.
- Süresi geçen kayıtların fiziksel temizliği yalnızca kullanıcı etkinliğine bağlıydı.
  İlk açılışta monotonic saat 1 saatten küçükse ilk temizlik de atlanabiliyordu.
- Admin ve eski izin komutları bütün kullanıcıların `/` menüsünü kalabalıklaştırıyordu.

## Küçük adımlarla mimari

1. `privacy_policy.py`: tek aydınlatma metni ve yeni kullanıcıların bildirim sonrası kayıt kontrolü.
2. `admin_store.py`: parametrik SQL, kayıt izinleri ve güvenli veri işlemleri.
3. `migrations/001_admin_security.sql`: mevcut tabloları silmeden ek alanlar,
   indeksler, oturum, denetim ve duyuru kuyruğu tabloları.
4. `admin_telegram.py`: önce bildirim, sonra kayıt; butonlu kullanıcı/admin ekranları.
5. `admin_web.py` ve `admin_assets/`: mobil koyu arayüz, güvenli giriş ve sohbet API'si.
6. `admin_delivery.py`: web ve Telegram'ın ortak, kalıcı gönderim kuyruğu.
7. `admin_maintenance.py`: saklama süresi dolan veriyi temizleyen görev.

## Ortam değişkenleri

Gerçek sırları kaynak dosyalarına yazmayın. Render **Environment** veya yerel
`.env` kullanın. `.env.example` yalnızca şablondur.

| Değişken | Gereklilik / kullanım |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot ve yönetici doğrulama kodu için zorunlu gizli token |
| `GEMINI_API_KEY` | Mevcut AI uygulaması için zorunlu gizli anahtar |
| `GEMINI_MODEL` | Mevcut model seçimi |
| `GROQ_API_KEY`, `GROQ_MODEL` | Mevcut isteğe bağlı Groq yedeği/haber entegrasyonu |
| `DATABASE_URL` | Mevcut Neon bağlantısı; panel ve kalıcı kayıt için zorunlu, uygulamada pooled tercih edilir |
| `DATABASE_URL_UNPOOLED` | Migration/manuel temizlik komutunda isteğe bağlı doğrudan bağlantı |
| `ADMIN_USER_ID` | Yöneticinin pozitif Telegram sayısal ID'si; `/whoami` ile öğrenilir |
| `ADMIN_WEB_PASSWORD` | Benzersiz, rastgele, en az 20 karakterli yönetici parolası |
| `ADMIN_SESSION_SECRET` | Önerilen ayrı, rastgele 32+ karakterli imzalama sırrı; eksikse mevcut parola alan ayrımlı HMAC anahtarı olarak kullanılır |
| `ADMIN_PANEL_ENABLED` | `true` web panelini açar; eksik/false kapalı tutar |
| `ALLOWED_USER_ID` | Mevcut bot erişim sınırı; 0 tüm bot kullanıcılarına izin verir, admin yetkisi vermez |
| `WEBHOOK_BASE_URL` | İsteğe bağlı HTTPS adresi; Render'ın `RENDER_EXTERNAL_HOSTNAME` değeri varsayılan olarak kullanılır |
| `TRANSCRIPT_DEFAULT_ENABLED` | Deneysel ders kurulumu için varsayılan `true`; yalnızca yeni kullanıcılar için bildirim SONRASI kayıt açar; `false` otomatik kaydı kapatır |
| `PRIVACY_CONTROLLER` | Veri sorumlusu adı/unvanı; kullanıcıya aynen bildirilir |
| `PRIVACY_CONTACT` | KVKK başvuruları için gerçek iletişim adresi |
| `PRIVACY_LEGAL_BASIS` | Veri sorumlusunun değerlendirdiği, amaçla bağlantılı işleme şartı ve açıklaması |

Kullanıcının isteğiyle deneysel ders kurulumunda son üç gizlilik alanı teknik
açılış koşulu değildir. Kod bir hukuki dayanak icat etmez; alanların dolu olması
tek başına KVKK uygunluğunu kanıtlamaz. Varsayılan kayıt yine ilk bildirimden
önce açılmaz; önceki kapalı kullanıcı tercihleri asla otomatik açılmaz.
Güvenlik/destek amacıyla varsayılan içerik kaydı için uygulanabilir işleme şartı,
zorunluluk ve ölçülülük, özel nitelikli veri riski ve yurt dışına aktarım
koşulları veri sorumlusunca değerlendirilmelidir. Telegram, Gemini/Groq ve Neon
sağlayıcılarının işleme/aktarım şartları da bu değerlendirmeye dahildir.

## Kullanıcı gizliliği

- İlk metin arşivlenmez. Aydınlatma iletilmeden kayıt başlamaz.
- İlk `/start` ve `/gizlilik` bildirimden sonra menüyü açabilir; AI'ya ilk özel
  mesaj iletilmez. Kullanıcıdan mesajını yeniden yazması açıkça istenir.
- Sonraki metinler Telegram mesaj zamanı bildirimden sonrayken kaydedilir.
  Menü komutları ve ses dosyaları bu arşive alınmaz.
- Önceki açık/kapalı tercihler korunur. İngilizce ilerleme veya haber aboneliği
  tablosunda bilinen eski kullanıcılar da migration'da `legacy_record=true` alınır.
- Kullanıcının açık tercihi `privacy_choice_at` alanındadır; otomatik bildirim
  bu tercihi geçersiz kılamaz.
- `/gizlilik`: kayıt durumunu gör, isteğe bağlı **Kaydı aç**, **Kaydı durdur ve
  geçmişi sil**, **Kayıtlarımı sil**, duyuru iznini aç/kapat.
- Eski kayıt/duyuru komutları uyumluluk için çalışır fakat menüde görünmez.
- Yönetici kayıtları durdurabilir ve silebilir; kullanıcı adına kayıt açamaz.
- Durdurma/silme DB'de hemen etkili olur. Açık web sekmesi en geç bir sonraki
  20 saniyelik kontrolde kayıt durumunu günceller. Yeniden açma, silinen mesajları
  veya önceki isteğe ait gecikmiş AI yanıtını geri getirmez.
- Telegram eski sohbet geçmişini topluca getirmeye izin vermez. Silinmiş veya
  kayıt kapalıyken yazılmış konuşmalar oluşturulamaz.

Kayıtlar 30 gün sonunda sorgularda erişilemez. Çalışan servis saatlik temizlik
yapar; ayrıca **Admin data retention** GitHub Actions görevi Render uyurken de
temizlik yapar. Depodaki `DATABASE_URL` Actions sırrının varlığı kontrol edilmeli.
GitHub schedule gecikebilir; tam 30. gün saniyesinde fiziksel silme garantisi
yoktur. Manuel görev: `python admin_maintenance.py`. Neon geri yükleme/yedek
pencereleri ayrı yönetilir; kullanıcı silme talebinin yedeklerden geri getirilmemesi
için veri sorumlusunun yedek/silme süreci tanımlanmalıdır.

## Web giriş ve korumalar

HTTPS zorunlu. Paroladan sonra kod **yalnızca ADMIN_USER_ID** hesabına Telegram
üzerinden gider. Yönetici önce botu `/start` ile açmış olmalı. Kod 5 dakika,
en fazla 5 deneme ve tek kullanım; oturum 8 saat geçerli.

Sadece oturum token'ının hash'i Postgres'te tutulur. Çerezler HttpOnly, Secure,
SameSite=Strict ve `/admin` kapsamındadır. Çıkış DB oturumunu iptal eder;
parola/yönetici ID'si/imzalama sırrı değişirse eski oturumlar geçersiz olur.
Girişte ve bütün değişikliklerde CSRF kontrolü vardır. Giriş deneme sınırı
Postgres'te kalır; IP ham olarak değil HMAC ile saklanır.

HTML alanları kaçışlanır; JS sohbet metinlerini yalnızca `textContent` ile
yerleştirir. CSP nonce, no-store, frame engeli ve parametrik SQL kullanılır.
Admin denetim tablosunda giriş, çıkış, görüntüleme, kayıt değişiklikleri ve
duyuru önizleme/onay işlemleri bulunur; metin veya sır içermez, 90 gün tutulur.

## Duyurular

Web: **Duyurular → mesaj/isteğe bağlı hedef ID → önizleme → onay**.
Telegram: **/admin → Duyuru gönder → metin → önizleme → onay**.
Toplu mesaj yalnızca duyuru izni olanlara gider; haber aboneliği bu izin değildir.
Tek kişiye mesaj, mevcut bot kullanıcısına destek iletişimidir.

Onay DB'de tek kez kullanılabilir, 5 dakika geçerlidir. Gönderimler Postgres'te
kuyruğa alınır ve tek Render instance'ında yaklaşık 8 mesaj/saniye ile işlenir.
İzin her gönderim öncesi tekrar kontrol edilir. Telegram `RetryAfter` ertelenir;
engellenmiş/botu başlatmamış kullanıcı başarısız sayılır. Timeout veya gönderim
sırasında restart olursa teslim **belirsiz** olabilir; otomatik tekrar
gönderilmez. Geçmiş ekranında başarılı, başarısız, atlanmış ve belirsiz sayıları
ayrı gösterilir. Render uykudaysa bekleyen işler uyandıktan sonra devam eder.
Yerel polling modunda da aynı gönderim döngüsü çalışır.

## Migration, test ve yayınlama

`setup()` migration sürümünü DB'de tutar ve aynı transaction'da advisory lock
alır. İkinci çalıştırma güvenlidir; kullanıcı, haber ve abonelik tabloları
silinmez. Önce ayrı test veritabanı/Neon test branch'inde doğrulanmalıdır.
İsteğe bağlı doğrudan URL ile migration: `python admin_maintenance.py`.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
# PostgreSQL entegrasyonları için, yalnızca AYRI test DB'si:
TEST_DATABASE_URL=postgresql://... python -m unittest discover -s tests -v
python -m compileall -q .
```

CI kendi PostgreSQL 16 servisini başlatır. Entegrasyon testleri geçici,
benzersiz `karamaz_test_...` şemaları oluşturur ve sonunda yalnızca bunları siler.
Gerçek kullanıcı mesajlarıyla test yapılmaz. Telegram/Gemini/Groq ağ çağrıları
testlerde taklit edilir; bu canlı API başarı kanıtı değildir.

Render mevcut `main` dalını izler. PR incelemesi ve birleştirmeden sonra otomatik
dağıtımı izleyin; commit SHA ve `Live` durumunu eşleştirin. `/health` 200,
yetkisiz `/admin/api/user/.../messages` 401 ve gerçek yönetici hesabıyla
parola/kod girişi kontrol edilmeli. Gizlilik yapılandırması, migration ve
Actions saklama görevi de canlıda doğrulanmalı.

Free web tier, mevcut Neon ve webhook korunur; yeni ücretli servis eklenmez.
Bu sürümün yayınlandığı, yalnızca ilgili commit gerçekten Live olduğunda söylenebilir.
