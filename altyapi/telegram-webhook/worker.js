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
 * GUVENLIK: burada hicbir anahtar YAZILI DEGIL. Hepsi Cloudflare secret'i
 * olarak enjekte edilir (`wrangler secret put`). Dogrulama zinciri:
 *   1. Telegram'in `X-Telegram-Bot-Api-Secret-Token` basligi - istegin
 *      gercekten Telegram'dan geldigini kanitlar. Yoksa URL'i bilen herkes
 *      Actions dakikasi yakabilirdi.
 *   2. chat_id beyaz listesi - yabanci mesaji dispatch ETMEZ. Bot zaten
 *      cevap vermiyordu ama kosu yine de baslar ve dakika yakardi.
 *   3. Komut filtresi - yalnizca "/" ile baslayan metin kosu tetikler.
 *      Sohbet metni bir sey tetiklemez.
 */

const AYAR = {
  // Aylik Actions dakika butcesi (private repo, GitHub Free).
  AYLIK_DAKIKA: 2000,
  // Bu oranin ustunde UYARI eklenir ama istek yine de calisir.
  UYARI_ORANI: 0.8,
  // Bu oranin ustunde dispatch ATILMAZ. Rapor workflow'u korunur:
  // sorgu botu lukstur, gunluk rapor degil.
  TAVAN_ORANI: 0.92,
  // Ayni kullanicidan pes pese gelen mesajlar icin en kucuk aralik (saniye).
  // Olmasaydi 20 mesajlik bir seri 20 kosu = 20 dakika yakardi.
  ASGARI_ARALIK_SN: 90,
};

export default {
  async fetch(istek, ortam) {
    if (istek.method !== "POST") {
      return new Response("only POST", { status: 405 });
    }

    // 1. Istek gercekten Telegram'dan mi?
    const baslik = istek.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (!ortam.TELEGRAM_WEBHOOK_SECRET || baslik !== ortam.TELEGRAM_WEBHOOK_SECRET) {
      // 401 degil 200: Telegram 401 alirsa webhook'u devre disi birakabilir.
      // Sessizce yut, hicbir sey yapma.
      return new Response("ok", { status: 200 });
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

    // 2. Yalnizca izinli chat. Beyaz liste BOSSA kimseye acilmaz.
    const izinliler = (ortam.IZINLI_CHAT_ID || "")
      .split(",").map((s) => s.trim()).filter(Boolean);
    if (!izinliler.includes(String(chatId))) {
      return new Response("ok", { status: 200 });
    }

    // 3. Yalnizca komutlar kosu tetikler.
    if (!metin.startsWith("/")) {
      await telegramaYaz(ortam, chatId,
        "Komut degil. /yardim yazarsan ne sorabilecegini listelerim.");
      return new Response("ok", { status: 200 });
    }

    const fren = await frenKontrol(ortam);
    if (fren) {
      await telegramaYaz(ortam, chatId, fren);
      return new Response("ok", { status: 200 });
    }

    const gonderildi = await dispatchAt(ortam, chatId, metin);
    if (!gonderildi) {
      await telegramaYaz(ortam, chatId,
        "Analiz baslatilamadi (GitHub'a ulasilamadi). Birazdan tekrar dene.");
    }
    return new Response("ok", { status: 200 });
  },
};

/**
 * Kota ve hiz freni. Doner: kullaniciya gidecek metin, ya da gecerse null.
 *
 * Iki ayri fren, ayni yerde: aylik butce (uzun vadeli) ve ardisik istek
 * araligi (anlik). Ikisi de "kac kosu oldu" sorusunun cevabindan turuyor,
 * yani tek API cagrisiyla olculuyor.
 */
async function frenKontrol(ortam) {
  const simdi = new Date();
  const ayBasi = new Date(Date.UTC(simdi.getUTCFullYear(), simdi.getUTCMonth(), 1));
  const kosular = await kosulariSay(ortam, ayBasi);
  if (kosular === null) return null;   // olculemedi -> gecir, sistemi kilitleme

  // Her kosu en az 1 dakika faturalanir (yukari yuvarlama).
  const oran = kosular.toplam / AYAR.AYLIK_DAKIKA;

  if (oran >= AYAR.TAVAN_ORANI) {
    const kalan = sonrakiAyaKalan(simdi);
    return `KOTA TAVANI - Actions kullanimi %${(oran * 100).toFixed(0)} ` +
      `(${kosular.toplam}/${AYAR.AYLIK_DAKIKA} dk).\n\n` +
      `Sorgu botu durduruldu; gunluk rapor calismaya devam ediyor ` +
      `(oncelik onda). Kota ${kalan} sonra sifirlanacak.`;
  }

  if (kosular.sonKosuSaniye !== null &&
      kosular.sonKosuSaniye < AYAR.ASGARI_ARALIK_SN) {
    const bekle = Math.ceil((AYAR.ASGARI_ARALIK_SN - kosular.sonKosuSaniye) / 60);
    return `Az once bir analiz calistirildi. Her kosu 1 dakika kotadan ` +
      `dusuyor, bu yuzden ${AYAR.ASGARI_ARALIK_SN} saniyeden sik ` +
      `tetiklenmiyor.\n\nEn erken ${bekle} dakika sonra tekrar sor.`;
  }

  if (oran >= AYAR.UYARI_ORANI) {
    // Uyari FREN DEGIL: istek calisir, yalnizca haber verilir. Burada
    // durdurmak, kota daha bitmemisken botu erkenden susturmak olurdu.
    return null;
  }
  return null;
}

/** Ay basindan bu yana kac kosu oldu ve sonuncusu kac saniye once. */
async function kosulariSay(ortam, ayBasi) {
  const tarih = ayBasi.toISOString().slice(0, 10);
  const url = `https://api.github.com/repos/${ortam.GITHUB_REPO}` +
    `/actions/runs?created=%3E%3D${tarih}&per_page=1`;
  try {
    const cevap = await fetch(url, { headers: githubBasliklari(ortam) });
    if (!cevap.ok) return null;
    const govde = await cevap.json();
    const sonKosu = govde.workflow_runs?.[0]?.created_at;
    return {
      toplam: govde.total_count ?? 0,
      sonKosuSaniye: sonKosu
        ? Math.floor((Date.now() - new Date(sonKosu).getTime()) / 1000)
        : null,
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
        // Metin yalnizca Actions logunda ne oldugunu gormek icin. Bot
        // mesaji buradan DEGIL, getUpdates'ten okur - tek dogruluk kaynagi
        // Telegram'in kendi kuyrugu olsun, yoksa offset defteri ile bu
        // yuk arasinda tutarsizlik cikar.
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

function sonrakiAyaKalan(simdi) {
  const sonraki = new Date(Date.UTC(simdi.getUTCFullYear(), simdi.getUTCMonth() + 1, 1));
  const saat = Math.ceil((sonraki - simdi) / 3_600_000);
  return saat >= 48 ? `${Math.floor(saat / 24)} gun` : `${saat} saat`;
}
