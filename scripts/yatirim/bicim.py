"""Rapor bicimlendirme yardimcilari.

Ayri modul olmasinin tek sebebi: para ve yuzde bicimini iki rapor modulunun
birbirinden kopyalamasini onlemek. Kopyalanirsa biri 1 basamak digeri 2
basamak gosterir ve ayni rakam iki tabloda farkli okunur.
"""

from __future__ import annotations


def tl(deger: float) -> str:
    return f"{deger:,.0f} TL".replace(",", ".")


def yuzde(oran_: float, basamak: int = 1) -> str:
    """Isaretli yuzde: getiri ve sapma gibi yonu onemli olan degerler icin."""
    return f"{oran_ * 100:+.{basamak}f}%"


def oran(deger: float, basamak: int = 1) -> str:
    """Isaretsiz yuzde: agirlik, volatilite gibi buyuklugu onemli olanlar icin."""
    return f"{deger * 100:.{basamak}f}%"
