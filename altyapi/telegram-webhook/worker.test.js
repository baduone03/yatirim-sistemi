/**
 * Worker testleri. Node'un YERLESIK kosucusu (`node --test`) - ek bagimlilik
 * yok, `npm install` gerekmiyor. Python tarafindaki "pytest YOK, stdlib
 * unittest" kuralinin JS karsiligi.
 *
 * Calistir:  node --test altyapi/telegram-webhook/
 *
 * Ag'a CIKILMAZ: `fetch` her testte sahte fonksiyonla degistirilir.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import worker, { AYAR, frenKontrol, izinliMi, kotaOzeti } from "./worker.js";

const ORTAM = {
  TELEGRAM_WEBHOOK_SECRET: "dogru-secret",
  TELEGRAM_BOT_TOKEN: "sahte-token",
  GITHUB_PAT: "sahte-pat",
  GITHUB_REPO: "sahibi/repo",
  IZINLI_CHAT_ID: "123456",
};

/** Telegram'in gonderecegi bicimde istek. */
function istekYap(chatId, metin, secret = "dogru-secret") {
  const basliklar = new Headers({ "Content-Type": "application/json" });
  if (secret !== null) basliklar.set("X-Telegram-Bot-Api-Secret-Token", secret);
  return new Request("https://worker.test/", {
    method: "POST",
    headers: basliklar,
    body: JSON.stringify({ message: { chat: { id: chatId }, text: metin } }),
  });
}

/** `fetch` yerine gecer; cagrilari kaydeder, hicbir sey gondermez. */
function fetchKaydedici(cevaplar = {}) {
  const cagrilar = [];
  globalThis.fetch = async (url, secenekler = {}) => {
    cagrilar.push({ url: String(url), yontem: secenekler.method || "GET" });
    if (String(url).includes("/actions/runs")) {
      return {
        ok: true,
        json: async () => cevaplar.kosular ?? { total_count: 0, workflow_runs: [] },
      };
    }
    return { ok: true, json: async () => ({ ok: true }) };
  };
  return cagrilar;
}

function dispatchSayisi(cagrilar) {
  return cagrilar.filter((c) => c.url.endsWith("/dispatches")).length;
}

// --------------------------------------------------------------------------

test("yetkisiz chat dispatch ATMAZ ve cevap DONMEZ", async () => {
  const cagrilar = fetchKaydedici();
  const cevap = await worker.fetch(istekYap(999999, "/durum"), ORTAM);

  assert.equal(cevap.status, 200, "sessiz 200 donmeli");
  assert.equal(dispatchSayisi(cagrilar), 0, "dispatch atilmamali");
  assert.equal(
    cagrilar.filter((c) => c.url.includes("api.telegram.org")).length, 0,
    "botun varligini dogrulayan cevap gitmemeli");
});

test("beyaz liste BOSSA kimse gecemez", () => {
  assert.equal(izinliMi("", 123456), false);
  assert.equal(izinliMi(undefined, 123456), false);
  assert.equal(izinliMi("123456", 123456), true);
  assert.equal(izinliMi("111, 123456 ,222", "123456"), true);
});

test("secret_token yoksa 401 ve dispatch YOK", async () => {
  const cagrilar = fetchKaydedici();
  const cevap = await worker.fetch(istekYap(123456, "/durum", null), ORTAM);

  assert.equal(cevap.status, 401);
  assert.equal(dispatchSayisi(cagrilar), 0);
});

test("secret_token YANLISSA 401", async () => {
  const cagrilar = fetchKaydedici();
  const cevap = await worker.fetch(istekYap(123456, "/durum", "yanlis"), ORTAM);

  assert.equal(cevap.status, 401);
  assert.equal(dispatchSayisi(cagrilar), 0);
});

test("Worker'da secret tanimli degilse hicbir istek gecmez", async () => {
  const cagrilar = fetchKaydedici();
  const eksik = { ...ORTAM, TELEGRAM_WEBHOOK_SECRET: "" };
  const cevap = await worker.fetch(istekYap(123456, "/durum", "herhangi"), eksik);

  assert.equal(cevap.status, 401);
  assert.equal(dispatchSayisi(cagrilar), 0);
});

test("kota hesabi GERCEK kosu suresini kullanir, 1 dk VARSAYMAZ", () => {
  // 90 saniyelik kosular: her biri 2 dakika faturalanir (yukari yuvarlama).
  // Sabit "1 dk" varsayilsaydi tahmin 100 dk cikardi - gercegin YARISI.
  const kosular = Array.from({ length: 10 }, () => ({
    created_at: "2026-08-19T10:00:00Z",
    updated_at: "2026-08-19T10:01:30Z",
  }));
  const ozet = kotaOzeti(kosular, 100, Date.parse("2026-08-19T12:00:00Z"));

  assert.equal(ozet.ortalamaFaturaDk, 2, "90 sn 2 dakika faturalanir");
  assert.equal(ozet.tahminiDakika, 200, "100 kosu x 2 dk");
  assert.equal(ozet.ortalamaSaniye, 90);
});

test("39 saniyelik kosu 1 dakika faturalanir", () => {
  const kosular = Array.from({ length: 5 }, () => ({
    created_at: "2026-08-19T10:00:00Z",
    updated_at: "2026-08-19T10:00:39Z",
  }));
  const ozet = kotaOzeti(kosular, 400, Date.parse("2026-08-19T12:00:00Z"));

  assert.equal(ozet.ortalamaFaturaDk, 1);
  assert.equal(ozet.tahminiDakika, 400);
  assert.equal(ozet.ortalamaSaniye, 39);
});

test("bitmemis kosu ortalamayi bozmaz", () => {
  const ozet = kotaOzeti([
    { created_at: "2026-08-19T10:00:00Z", updated_at: "2026-08-19T09:00:00Z" }, // negatif
    { created_at: "2026-08-19T10:00:00Z", updated_at: "2026-08-19T10:00:30Z" },
  ], 10, Date.parse("2026-08-19T12:00:00Z"));

  assert.equal(ozet.ornekSayisi, 1);
  assert.equal(ozet.ortalamaSaniye, 30);
});

test("sogutma kota tavanindan ONCE calisir", async () => {
  fetchKaydedici();
  const kosular = {
    total_count: 5,
    workflow_runs: [{
      created_at: new Date(Date.now() - 10_000).toISOString(),
      updated_at: new Date(Date.now() - 5_000).toISOString(),
    }],
  };
  const getir = async () => ({ ok: true, json: async () => kosular });
  const fren = await frenKontrol(ORTAM, getir);

  assert.ok(fren, "10 saniye once kosu varken fren devreye girmeli");
  assert.match(fren, /dakika sonra tekrar sor/);
  assert.doesNotMatch(fren, /KOTA TAVANI/, "kota degil sogutma sebebi olmali");
});

test("kota tavani asilinca dispatch ATILMAZ", async () => {
  const cagrilar = fetchKaydedici({
    kosular: {
      total_count: 1900,
      workflow_runs: [{
        created_at: "2026-01-01T00:00:00Z",      // cok eski - sogutma gecer
        updated_at: "2026-01-01T00:00:39Z",
      }],
    },
  });
  const cevap = await worker.fetch(istekYap(123456, "/durum"), ORTAM);

  assert.equal(cevap.status, 200);
  assert.equal(dispatchSayisi(cagrilar), 0, "tavanda dispatch atilmamali");
  assert.ok(cagrilar.some((c) => c.url.includes("sendMessage")),
    "kullaniciya sebep bildirilmeli");
});

test("olcum basarisizsa fren ACILIR - sistem kilitlenmez", async () => {
  const getir = async () => ({ ok: false, json: async () => ({}) });
  assert.equal(await frenKontrol(ORTAM, getir), null);
});

test("temiz durumda dispatch ATILIR", async () => {
  const cagrilar = fetchKaydedici({
    kosular: {
      total_count: 50,
      workflow_runs: [{
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:39Z",
      }],
    },
  });
  const cevap = await worker.fetch(istekYap(123456, "/durum"), ORTAM);

  assert.equal(cevap.status, 200);
  assert.equal(dispatchSayisi(cagrilar), 1);
});

test("komut olmayan metin dispatch ATMAZ", async () => {
  const cagrilar = fetchKaydedici();
  await worker.fetch(istekYap(123456, "merhaba"), ORTAM);

  assert.equal(dispatchSayisi(cagrilar), 0);
});

test("AYAR esikleri tutarli", () => {
  assert.ok(AYAR.TAVAN_ORANI > 0 && AYAR.TAVAN_ORANI < 1);
  assert.ok(AYAR.ASGARI_ARALIK_SN > 0);
});
