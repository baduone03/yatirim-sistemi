/**
 * Telegram -> GitHub Actions kopru Worker'i.
 *
 * NEDEN VAR: bot eskiden yoklama (polling) yapiyordu - GitHub Actions 30
 * dakikada bir uyanip "yeni mesaj var mi?" diye soruyordu. Iki sorunu vardi:
 * cevap 30 dakika gecikebiliyordu ve mesaj OLMASA DA her yoklama 1 dakika
 * fatura yaziyordu (~1095 dk/ay, butcenin %55'i).
 *
 * Bu Worker mesaj geldigi ANDA `repository_dispatch` atar. Cevap ~40 saniyeye
 * iner ve yalnizca gercekten mesaj oldugunda dakika yanar.
 *
 * YETKI KONTROLU BURADA YAPILIR, Actions'ta DEGIL. Telegram botlari herkese
 * aciktir: bot adini bilen herkes mesaj yazabilir. Suzme Actions tarafinda
 * kalsaydi her yabanci mesaj bir kosu baslatir ve 1 dakika kota yakardi -
 * yani botun adini bilen biri kotayi tuketebilirdi. Actions tarafindaki
 * kontrol KALDI ama artik ikincil savunma: repo'ya yazma yetkisi olan biri
 * Worker'i atlayip dogrudan dispatch atabilir.
 *
 * SIRA (her adim bir oncekini gecmeden calismaz):
 *   1. secret_token basligi     -> yoksa 401, dispatch YOK
 *   2. chat id beyaz listesi    -> yoksa 200 (sessiz), dispatch YOK
 *   3. komut bicimi ("/" ile)   -> degilse 200, dispatch YOK
 *   4. sogutma (asgari aralik)  -> gecmezse Telegram'a "N dk sonra"
 *   5. kota tavani              -> gecmezse Telegram'a "kota doldu"
 *   6. repository_dispatch
 *
 * GUVENLIK: burada hicbir anahtar YAZILI DEGIL. Hepsi Cloudflare secret'i
 * olarak enjekte edilir (`wrangler secret put`).
 */

export const AYAR = {
  // Aylik Actions dakika butcesi (private repo, GitHub Free).
  AYLIK_DAKIKA: 2000,
  // Bu oranin ustunde dispatch ATILMAZ. Rapor workflow'u korunur:
  // sorgu botu lukstur, gunluk rapor degil.
  TAVAN_ORANI: 0.92,
  // Ayni kullanicidan pes pese gelen mesajlar icin en kucuk aralik (saniye).
  // Olmasaydi 20 mesajlik bir seri 20 kosu = 20 dakika yakardi.
  ASGARI_ARALIK_SN: 90,
  // Kota tahmini icin ornekleme genisligi (tek sayfa, tek istek).
  ORNEK_KOSU: 100,
};

export default {
  async fetch(istek, ortam) {
    if (istek.method !== "POST") {
      return new Response("only POST", { status: 405 });
    }

    // 1. Istek gercekten Telegram'dan mi?
    //
    // 401 dondurmek guvenli: Telegram'in KENDI istekleri her zaman dogru
    // basligi tasir, yani 401 alan istek zaten sahtedir. Ustelik secret
    // yanlis kurulmussa (setWebhook'ta secret_token unutulmus) bu durum
    // Telegram tarafinda GORUNUR hata olarak birikir - sessizce 200 donmek
    // yanlis kurulumu her mesajin kaybolmasi seklinde gizlerdi.
    const baslik = istek.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (!ortam.TELEGRAM_WEBHOOK_SECRET || baslik !== ortam.TELEGRAM_WEBHOOK_SECRET) {
      console.log("reddedildi: secret_token gecersiz");
      return new Response("unauthorized", { status: 401 });
    }

    let guncelleme;
    try {
      guncelleme = await istek.json();
    } catch {
      return new Response("ok", { status: 200 });
    }

    const mesaj = guncelleme.message || guncelleme.edited_message;
    const chatId = mesaj?.chat?.id;
    const metin = (mesaj?.text || "").trim();
    if (!chatId || !metin) return new Response("ok", { status: 200 });

    // 2. Beyaz liste. CEVAP DONULMEZ - "yetkin yok" demek bile botun orada
    // oldugunu dogrular. Beyaz liste BOSSA kimseye acilmaz.
    if (!izinliMi(ortam.IZINLI_CHAT_ID, chatId)) {
      console.log(`reddedildi: izinsiz chat id ${chatId}`);
      return new Response("ok", { status: 200 });
    }

    // 3. Yalnizca komutlar kosu tetikler. Sohbet metni dakika yakmaz.
    if (!metin.startsWith("/")) {
      await telegramaYaz(ortam, chatId,
        "Komut degil. /yardim yazarsan ne sorabilecegini listelerim.");
      return new Response("ok", { status: 200 });
    }

    // 4-5. Frenler.
    const fren = await frenKontrol(ortam);
    if (fren) {
      await telegramaYaz(ortam, chatId, fren);
      return new Response("ok", { status: 200 });
    }

    // 6. Calistir.
    const gonderildi = await dispatchAt(ortam, chatId, metin);
    if (!gonderildi) {
      await telegramaYaz(ortam, chatId,
        "Analiz baslatilamadi (GitHub'a ulasilamadi). Birazdan tekrar dene.");
    }
    return new Response("ok", { status: 200 });
  },
};

/** Beyaz liste kontrolu. Liste bos/tanimsizsa HERKES reddedilir. */
export function izinliMi(ham, chatId) {
  const izinliler = String(ham || "")
    .split(",").map((s) => s.trim()).filter(Boolean);
  if (izinliler.length === 0) return false;
  return izinliler.includes(String(chatId));
}

/**
 * Kosu listesinden kota ozeti cikarir.
 *
 * GERCEK SURE kullanilir, "kosu basina 1 dakika" VARSAYILMAZ. GitHub kosu
 * basina YUKARI YUVARLAR: 39 saniyelik kosu 1 dakika, 61 saniyelik kosu
 * 2 dakikadir. Sabit 1 dk varsaymak, kosular yavaslamaya basladiginda
 * kotayi oldugundan YARI kadar gosterir ve fren hic devreye girmez.
 *
 * `kosular` GitHub'in dondugu sirada, yani EN YENI ONCE.
 */
export function kotaOzeti(kosular, toplamSayi, simdiMs = Date.now()) {
  const sureler = kosular
    .map((k) => (new Date(k.updated_at) - new Date(k.created_at)) / 1000)
    // Negatif (henuz bitmemis) ve absurt uzun (takilmis) kosular disarida:
    // ikisi de ortalamayi bozar.
    .filter((s) => Number.isFinite(s) && s >= 0 && s < 3600);
  if (sureler.length === 0) return null;

  const faturali = sureler.map((s) => Math.max(1, Math.ceil(s / 60)));
  const ortalamaFaturaDk =
    faturali.reduce((a, b) => a + b, 0) / faturali.length;

  const son10 = sureler.slice(0, 10);
  const ortalamaSaniye = son10.reduce((a, b) => a + b, 0) / son10.length;

  const sonKosu = kosular[0]?.created_at;
  return {
    tahminiDakika: Math.round(ortalamaFaturaDk * toplamSayi),
    ortalamaFaturaDk,
    ortalamaSaniye,
    ornekSayisi: sureler.length,
    sonKosuSaniye: sonKosu
      ? Math.floor((simdiMs - new Date(sonKosu).getTime()) / 1000)
      : null,
  };
}

/**
 * Sogutma ve kota freni. Doner: kullaniciya gidecek metin, ya da gecerse null.
 *
 * Olcum BASARISIZ olursa null doner, yani istek GECER. Olcememeyi "kota
 * dolmus" saymak, GitHub API'sinin bir hikkirigini botun tumden susmasina
 * cevirirdi.
 */
export async function frenKontrol(ortam, getir = fetch, simdi = new Date()) {
  const ayBasi = new Date(Date.UTC(simdi.getUTCFullYear(), simdi.getUTCMonth(), 1));
  const ham = await kosulariCek(ortam, ayBasi, getir);
  if (!ham) return null;

  const ozet = kotaOzeti(ham.kosular, ham.toplam, simdi.getTime());
  if (!ozet) return null;

  // 4. Sogutma - kota tavanindan ONCE. Sebep: sogutma ANLIK korumadir
  // (pes pese 20 mesaj), tavan ise AYLIK. Kota bolgesinde olmayan ama hizli
  // yazan biri once sogutmaya takilmali, "kota %40" hesabina degil.
  if (ozet.sonKosuSaniye !== null &&
      ozet.sonKosuSaniye < AYAR.ASGARI_ARALIK_SN) {
    const bekle = Math.ceil((AYAR.ASGARI_ARALIK_SN - ozet.sonKosuSaniye) / 60);
    return `Az once bir analiz calistirildi. Her kosu kotadan dusuyor, ` +
      `bu yuzden ${AYAR.ASGARI_ARALIK_SN} saniyeden sik tetiklenmiyor.\n\n` +
      `En erken ${bekle} dakika sonra tekrar sor.`;
  }

  // 5. Aylik tavan.
  const oran = ozet.tahminiDakika / AYAR.AYLIK_DAKIKA;
  if (oran >= AYAR.TAVAN_ORANI) {
    return `KOTA TAVANI - Actions kullanimi %${(oran * 100).toFixed(0)} ` +
      `(~${ozet.tahminiDakika}/${AYAR.AYLIK_DAKIKA} dk, ` +
      `kosu ort. ${ozet.ortalamaSaniye.toFixed(0)} sn).\n\n` +
      `Sorgu botu durduruldu; gunluk rapor calismaya devam ediyor ` +
      `(oncelik onda). Kota ${sonrakiAyaKalan(simdi)} sonra sifirlanacak.`;
  }
  return null;
}

/** Ay basindan bu yana kosular + toplam sayi. Tek istek. */
async function kosulariCek(ortam, ayBasi, getir) {
  const tarih = ayBasi.toISOString().slice(0, 10);
  const url = `https://api.github.com/repos/${ortam.GITHUB_REPO}` +
    `/actions/runs?created=%3E%3D${tarih}&per_page=${AYAR.ORNEK_KOSU}`;
  try {
    const cevap = await getir(url, { headers: githubBasliklari(ortam) });
    if (!cevap.ok) return null;
    const govde = await cevap.json();
    return {
      toplam: govde.total_count ?? 0,
      kosular: govde.workflow_runs ?? [],
    };
  } catch {
    return null;
  }
}

async function dispatchAt(ortam, chatId, metin) {
  const url = `https://api.github.com/repos/${ortam.GITHUB_REPO}/dispatches`;
  try {
    const cevap = await fetch(url, {
      method: "POST",
      headers: { ...githubBasliklari(ortam), "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: "telegram-mesaj",
        // Metin yalnizca komutu tasimak icin, 64 karakterle sinirli.
        client_payload: { chat_id: String(chatId), komut: metin.slice(0, 64) },
      }),
    });
    return cevap.ok;
  } catch {
    return false;
  }
}

function githubBasliklari(ortam) {
  return {
    Authorization: `Bearer ${ortam.GITHUB_PAT}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "yatirim-sistemi-webhook",
  };
}

async function telegramaYaz(ortam, chatId, metin) {
  // Hata YUTULUR ve loglanmaz: Telegram hata govdesi istek URL'ini, yani
  // bot token'ini tasiyabilir. Cloudflare loglari bu yuzden token gormemeli.
  try {
    await fetch(`https://api.telegram.org/bot${ortam.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: metin }),
    });
  } catch {
    /* yut */
  }
}

export function sonrakiAyaKalan(simdi) {
  const sonraki = new Date(Date.UTC(simdi.getUTCFullYear(), simdi.getUTCMonth() + 1, 1));
  const saat = Math.ceil((sonraki - simdi) / 3_600_000);
  return saat >= 48 ? `${Math.floor(saat / 24)} gun` : `${saat} saat`;
}
