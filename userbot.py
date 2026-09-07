"""
IvasBot — Userbot Telegram buat promosi massal ke semua grup.
Pakai Telethon, login pakai akun asli (bukan bot token).

Jalankan : python userbot.py
Perintah : .promosi | .promote | .addbl | .delbl | .listbl | .setdelay | .stop | .ping | .id | .help

Catatan penting soal promosi:
Kalau kita reply ke pesan orang lain (akun premium / postingan channel),
pesan itu akan DI-FORWARD apa adanya — bukan diketik ulang oleh akun kita.
Alasannya ada di komentar fungsi `kirim_promosi_ke()`.
"""

import os
import re
import json
import asyncio
import random

from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
)

BERKAS_KONFIG = "config.json"
NAMA_SESI = "userbot"

# Jeda sebelum pesan perintah dihapus sendiri (detik).
# Sengaja pendek: cukup buat kita baca konfirmasinya, tapi gak nongkrong lama di grup.
JEDA_HAPUS_OTOMATIS = 2

KONFIG_DEFAULT = {
    "api_id": 0,
    "api_hash": "",
    "delay_min": 5,
    "delay_max": 12,
    "blacklist": [],
}


# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
def muat_konfigurasi():
    """Baca config.json. Kalau rusak/gak ada, pakai nilai default biar bot tetap hidup."""
    konfig = dict(KONFIG_DEFAULT)
    if os.path.exists(BERKAS_KONFIG):
        try:
            with open(BERKAS_KONFIG, "r", encoding="utf-8") as berkas:
                konfig.update(json.load(berkas))
        except (json.JSONDecodeError, OSError):
            print("[!] config.json rusak, sementara pakai konfigurasi default.")
    return konfig


def simpan_konfigurasi(konfig):
    """Tulis ulang config.json. ensure_ascii=False biar emoji/teks Indonesia gak jadi \\uXXXX."""
    with open(BERKAS_KONFIG, "w", encoding="utf-8") as berkas:
        json.dump(konfig, berkas, indent=2, ensure_ascii=False)


konfig = muat_konfigurasi()

# Beberapa job promosi boleh jalan bareng, jadi disimpan per id.
# DAFTAR_JOB[id] = {"task": asyncio.Task, "stop": bool, "chat_id": int}
DAFTAR_JOB = {}
NOMOR_JOB = {"terakhir": 0}


# ---------------------------------------------------------------------------
# Helper tampilan
# ---------------------------------------------------------------------------
GARIS = "━━━━━━━━━━━━━━━━━━━━"


def kutip(teks: str) -> str:
    """Bungkus teks jadi blockquote HTML supaya rapi & bisa dilipat Telegram."""
    return "<blockquote>" + teks + "</blockquote>"


def susun_panel(judul: str, baris=None, catatan: str = "") -> str:
    """
    Rangkai pesan jadi satu format panel yang seragam:

        JUDUL
        ━━━━━━━━━━━
        isi baris
        ━━━━━━━━━━━
        catatan kecil

    `baris` boleh list of str atau list of (label, nilai) biar kolomnya rata.
    """
    bagian = [f"<b>{judul}</b>", GARIS]

    if baris:
        # Kalau formatnya (label, nilai), labelnya di-pad biar titik dua-nya lurus.
        pasangan = [b for b in baris if isinstance(b, (tuple, list))]
        lebar_label = max((len(str(p[0])) for p in pasangan), default=0)

        for item in baris:
            if isinstance(item, (tuple, list)):
                label, nilai = item[0], item[1]
                bagian.append(f"{str(label).ljust(lebar_label)} : <b>{nilai}</b>")
            else:
                bagian.append(str(item))

    if catatan:
        bagian.append(GARIS)
        bagian.append(f"<i>{catatan}</i>")

    return "\n".join(bagian)


async def balas_panel(event, judul, baris=None, catatan=""):
    """Ganti isi pesan perintah kita sendiri dengan panel rapi."""
    await event.edit(kutip(susun_panel(judul, baris, catatan)), parse_mode="html")


async def kirim_panel(klien, chat_id, judul, baris=None, catatan=""):
    """Kirim panel sebagai pesan baru (dipakai worker yang jalan di background)."""
    await klien.send_message(
        chat_id, kutip(susun_panel(judul, baris, catatan)), parse_mode="html"
    )


async def hapus_setelah(event, jeda: int = JEDA_HAPUS_OTOMATIS):
    """
    Hapus pesan perintah setelah jeda singkat.
    Dipakai buat perintah blacklist: konfirmasinya cukup kita lihat sebentar,
    jangan sampai anggota grup lain ikut baca kalau kita nge-blacklist grupnya.
    """
    await asyncio.sleep(jeda)
    try:
        await event.delete()
    except Exception:
        # Pesan bisa sudah dihapus manual atau kita kehilangan izin — bukan masalah fatal.
        pass


# ---------------------------------------------------------------------------
# Helper durasi
# ---------------------------------------------------------------------------
def baca_durasi(teks: str) -> int:
    """
    Ubah durasi versi manusia jadi detik.
    Contoh: '1 jam', '2 hours', '10 menit', '30m', '45 detik', '60s', '1.5 jam'.
    Angka telanjang dianggap menit (paling sering dipakai). 0 = format gak dikenali.
    """
    if not teks:
        return 0
    teks = teks.lower().strip()

    total_detik = 0
    pola_satuan = [
        (r"(\d+(?:\.\d+)?)\s*(?:jam|hours?|hr|h|j)\b", 3600),
        (r"(\d+(?:\.\d+)?)\s*(?:menit|mins?|minute|m)\b", 60),
        (r"(\d+(?:\.\d+)?)\s*(?:detik|secs?|second|s)\b", 1),
    ]

    ketemu = False
    for pola, pengali in pola_satuan:
        cocok = re.search(pola, teks)
        if cocok:
            ketemu = True
            total_detik += float(cocok.group(1)) * pengali

    if not ketemu:
        try:
            return int(float(teks) * 60)
        except ValueError:
            return 0

    return int(total_detik)


def format_durasi(detik: int) -> str:
    """Kebalikan dari baca_durasi(): detik -> teks yang enak dibaca."""
    if detik >= 3600:
        jam = detik // 3600
        menit = (detik % 3600) // 60
        return f"{jam} jam {menit} menit" if menit else f"{jam} jam"
    if detik >= 60:
        menit = detik // 60
        sisa = detik % 60
        return f"{menit} menit {sisa} detik" if sisa else f"{menit} menit"
    return f"{detik} detik"


def baca_argumen_promosi(teks_argumen: str):
    """
    Pecah argumen `.promosi` jadi (teks, jumlah_putaran, interval_detik).

    - '5 1 jam'                    -> ('', 5, 3600)
    - 'Jual Akun Murah 3 30 menit' -> ('Jual Akun Murah', 3, 1800)
    - 'Jual Akun Murah'            -> ('Jual Akun Murah', None, None)
    - ''                           -> ('', None, None)

    Kalau jumlah/interval gak lengkap, semuanya dianggap teks promosi —
    biar user gak kehilangan pesannya cuma karena salah format angka.
    """
    if not teks_argumen:
        return "", None, None

    teks_argumen = teks_argumen.strip()
    pola = (
        r"^(?:([\s\S]+?)\s+)?(\d+)\s+"
        r"(\d+(?:\.\d+)?\s*(?:jam|hours?|hr|h|j|menit|mins?|minute|m|detik|secs?|second|s)"
        r"(?:[\s\S]*)?)$"
    )
    cocok = re.match(pola, teks_argumen, re.IGNORECASE)
    if cocok:
        bagian_teks = (cocok.group(1) or "").strip()
        jumlah_putaran = int(cocok.group(2))
        interval_detik = baca_durasi(cocok.group(3).strip())
        if jumlah_putaran > 0 and interval_detik > 0:
            return bagian_teks, jumlah_putaran, interval_detik

    return teks_argumen, None, None


async def tunggu_jawaban(klien, chat_id, batas_detik=60):
    """
    Tunggu satu pesan berikutnya yang kita ketik sendiri di chat ini (buat menu interaktif).
    Jawabannya langsung dihapus supaya chat gak penuh angka '1', '2', '30 menit'.
    Return teks jawaban, atau None kalau kehabisan waktu.
    """
    loop = asyncio.get_running_loop()
    janji = loop.create_future()

    async def _penangkap(e):
        if e.chat_id == chat_id and not janji.done():
            janji.set_result(e)

    klien.add_event_handler(
        _penangkap, events.NewMessage(chats=chat_id, outgoing=True)
    )

    try:
        event_jawaban = await asyncio.wait_for(janji, timeout=batas_detik)
        jawaban = (event_jawaban.text or "").strip()
        try:
            await event_jawaban.delete()
        except Exception:
            pass
        return jawaban
    except asyncio.TimeoutError:
        return None
    finally:
        klien.remove_event_handler(_penangkap)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def pastikan_kredensial_api():
    """Minta api_id / api_hash sekali di awal, lalu simpan ke config.json."""
    if not konfig.get("api_id") or not konfig.get("api_hash"):
        print("== Setup API (sekali saja) ==")
        print("Ambil di https://my.telegram.org > API development tools\n")
        while True:
            try:
                konfig["api_id"] = int(input("Masukkan api_id  : ").strip())
                break
            except ValueError:
                print("api_id harus angka.")
        konfig["api_hash"] = input("Masukkan api_hash: ").strip()
        simpan_konfigurasi(konfig)


# ---------------------------------------------------------------------------
# Daftar hitam (blacklist)
# ---------------------------------------------------------------------------
async def cari_id_target(klien, acuan):
    """Ubah @username / id / -100id jadi id numerik. None kalau gagal diresolve."""
    acuan = str(acuan).strip()
    try:
        if acuan.lstrip("-").isdigit():
            entitas = await klien.get_entity(int(acuan))
        else:
            entitas = await klien.get_entity(acuan)
        return entitas.id
    except Exception:
        return None


def sedang_diblacklist(chat_id) -> bool:
    return int(chat_id) in [int(x) for x in konfig.get("blacklist", [])]


# ---------------------------------------------------------------------------
# Pengiriman promosi
# ---------------------------------------------------------------------------
async def kirim_promosi_ke(klien, tujuan, pesan_sumber, teks_biasa):
    """
    Kirim satu promosi ke satu grup.

    Kalau kita reply ke sebuah pesan, pesan itu DI-FORWARD, bukan disalin.
    Ini penting: emoji premium dan format dari akun premium/channel cuma tetap utuh
    kalau di-forward — begitu disalin, akun kita yang jadi "pengirim" dan emoji
    premium-nya rontok karena akun kita belum tentu premium. Forward juga bikin
    label "Diteruskan dari ..." nempel, jadi kredit tetap ke sumber aslinya.

    Kalau grup tujuan mematikan forward (protected content), baru kita salin manual
    sebagai jalan terakhir daripada promosinya gagal total.
    """
    if pesan_sumber is not None:
        try:
            await klien.forward_messages(tujuan, pesan_sumber)
            return
        except FloodWaitError:
            # Biar diurus pemanggil yang punya logika tunggu + retry.
            raise
        except Exception:
            await klien.send_message(
                tujuan,
                message=pesan_sumber.message or "",
                formatting_entities=pesan_sumber.entities or None,
                file=pesan_sumber.media if pesan_sumber.media else None,
            )
            return

    await klien.send_message(tujuan, teks_biasa)


# ---------------------------------------------------------------------------
# Klien + pendaftaran perintah
# ---------------------------------------------------------------------------
pastikan_kredensial_api()
klien = TelegramClient(NAMA_SESI, konfig["api_id"], konfig["api_hash"])


def daftarkan_perintah():
    """Semua handler perintah dikumpulkan di sini biar gampang dilacak."""

    def perintah(pola):
        # outgoing=True: hanya bereaksi ke perintah yang kita ketik sendiri.
        return events.NewMessage(outgoing=True, pattern=pola)

    # .ping ---------------------------------------------------------------
    @klien.on(perintah(r"^\.ping$"))
    async def _ping(event):
        await balas_panel(event, "🏓 PONG", ["Userbot aktif dan siap dipakai."])

    # .id -----------------------------------------------------------------
    @klien.on(perintah(r"^\.id$"))
    async def _info_id(event):
        pengirim = await event.get_sender()
        await balas_panel(
            event,
            "🆔 INFORMASI ID",
            [
                ("Chat ID", event.chat_id),
                ("User ID", getattr(pengirim, "id", "-")),
            ],
        )

    # .help ---------------------------------------------------------------
    @klien.on(perintah(r"^\.help$"))
    async def _bantuan(event):
        isi = [
            "🚀 <b>PROMOSI</b>",
            "<code>.promosi</code> — buka menu (reply pesan dulu)",
            "<code>.promosi &lt;kali&gt; &lt;interval&gt;</code>",
            "<i>contoh: .promosi 5 1 jam (sambil reply)</i>",
            "<code>.promosi &lt;teks&gt; &lt;kali&gt; &lt;interval&gt;</code>",
            "<i>contoh: .promosi Promo Hebat 3 30 menit</i>",
            "<code>.stop</code> — hentikan semua promosi",
            "",
            "🚫 <b>DAFTAR HITAM</b>",
            "<code>.addbl [@user/id]</code> — kecualikan grup",
            "<code>.delbl [@user/id]</code> — batalkan pengecualian",
            "<code>.listbl</code> — lihat daftarnya",
            "",
            "⚙️ <b>LAIN-LAIN</b>",
            "<code>.setdelay &lt;min&gt; &lt;max&gt;</code> — jeda antar grup",
            "<code>.ping</code> / <code>.id</code> — cek status & ID",
        ]
        await balas_panel(
            event,
            "📖 DAFTAR PERINTAH IVASBOT",
            isi,
            catatan="Pesan yang di-reply akan diteruskan apa adanya, "
                    "termasuk emoji premium dari pengirim aslinya.",
        )

    # .setdelay -----------------------------------------------------------
    @klien.on(perintah(r"^\.setdelay(?:\s+(\d+)\s+(\d+))?$"))
    async def _atur_jeda(event):
        cocok = event.pattern_match
        if not cocok.group(1):
            await balas_panel(
                event,
                "⏱ JEDA ANTAR GRUP",
                [("Sekarang", f"{konfig['delay_min']}–{konfig['delay_max']} detik")],
                catatan="Ubah dengan: .setdelay &lt;min&gt; &lt;max&gt;",
            )
            return

        minimal, maksimal = int(cocok.group(1)), int(cocok.group(2))
        if minimal > maksimal:
            # Kebalik itu manusiawi, tinggal ditukar aja daripada dimarahin error.
            minimal, maksimal = maksimal, minimal

        konfig["delay_min"], konfig["delay_max"] = minimal, maksimal
        simpan_konfigurasi(konfig)
        await balas_panel(
            event,
            "✅ JEDA DIPERBARUI",
            [("Jeda baru", f"{minimal}–{maksimal} detik")],
            catatan="Jeda dipilih acak dalam rentang ini setiap kirim ke grup.",
        )

    # .stop ---------------------------------------------------------------
    @klien.on(perintah(r"^\.stop$"))
    async def _hentikan(event):
        job_aktif = [j for j in DAFTAR_JOB.values() if not j["stop"]]
        if not job_aktif:
            await balas_panel(event, "ℹ️ TIDAK ADA PROMOSI", ["Semua job sudah berhenti."])
            return

        for job in DAFTAR_JOB.values():
            job["stop"] = True

        await balas_panel(
            event,
            "🛑 PROMOSI DIHENTIKAN",
            [("Job dihentikan", f"{len(job_aktif)} job")],
            catatan="Pengiriman berhenti setelah grup yang sedang diproses selesai.",
        )

    # .addbl --------------------------------------------------------------
    @klien.on(perintah(r"^\.addbl(?:\s+(.+))?$"))
    async def _tambah_blacklist(event):
        argumen = event.pattern_match.group(1)
        if argumen:
            id_target = await cari_id_target(klien, argumen.strip())
            if id_target is None:
                await balas_panel(event, "❌ TARGET TIDAK DITEMUKAN", ["Cek lagi @username atau ID-nya."])
                await hapus_setelah(event)
                return
        else:
            id_target = event.chat_id  # tanpa argumen = grup tempat perintah diketik

        daftar = konfig.setdefault("blacklist", [])
        if int(id_target) in [int(x) for x in daftar]:
            await balas_panel(event, "ℹ️ SUDAH DI DAFTAR HITAM", [("ID", id_target)])
        else:
            daftar.append(int(id_target))
            simpan_konfigurasi(konfig)
            await balas_panel(
                event,
                "✅ MASUK DAFTAR HITAM",
                [("ID", id_target), ("Total", f"{len(daftar)} grup")],
                catatan="Grup ini dilewati saat promosi.",
            )

        # Hapus jejaknya — jangan sampai anggota grup tahu grupnya kita kecualikan.
        await hapus_setelah(event)

    # .delbl --------------------------------------------------------------
    @klien.on(perintah(r"^\.delbl(?:\s+(.+))?$"))
    async def _hapus_blacklist(event):
        argumen = event.pattern_match.group(1)
        if argumen:
            id_target = await cari_id_target(klien, argumen.strip())
            if id_target is None:
                await balas_panel(event, "❌ TARGET TIDAK DITEMUKAN", ["Cek lagi @username atau ID-nya."])
                await hapus_setelah(event)
                return
        else:
            id_target = event.chat_id

        daftar = konfig.setdefault("blacklist", [])
        if int(id_target) not in [int(x) for x in daftar]:
            await balas_panel(event, "ℹ️ TIDAK ADA DI DAFTAR HITAM", [("ID", id_target)])
        else:
            konfig["blacklist"] = [x for x in daftar if int(x) != int(id_target)]
            simpan_konfigurasi(konfig)
            await balas_panel(
                event,
                "✅ KELUAR DARI DAFTAR HITAM",
                [("ID", id_target), ("Sisa", f"{len(konfig['blacklist'])} grup")],
                catatan="Grup ini ikut dipromosikan lagi.",
            )

        await hapus_setelah(event)

    # .listbl -------------------------------------------------------------
    @klien.on(perintah(r"^\.listbl$"))
    async def _lihat_blacklist(event):
        daftar = konfig.get("blacklist", [])
        if not daftar:
            await balas_panel(event, "📭 DAFTAR HITAM KOSONG", ["Semua grup ikut dipromosikan."])
            return

        baris = [f"{no}. <code>{id_grup}</code>" for no, id_grup in enumerate(daftar, 1)]
        await balas_panel(
            event,
            f"🚫 DAFTAR HITAM ({len(daftar)} GRUP)",
            baris,
            catatan="Hapus dengan: .delbl &lt;id&gt;",
        )

    # .promosi / .promote -------------------------------------------------
    @klien.on(perintah(r"^\.(?:promosi|promote)(?:\s+([\s\S]+))?$"))
    async def _promosi(event):
        pesan_sumber = await event.get_reply_message()
        argumen_mentah = event.pattern_match.group(1)

        if pesan_sumber is None and not argumen_mentah:
            await balas_panel(
                event,
                "📖 CARA PAKAI PROMOSI",
                [
                    "<b>Menu interaktif</b>",
                    "Reply pesan promosi lalu ketik <code>.promosi</code>",
                    "",
                    "<b>Format cepat</b>",
                    "<code>.promosi &lt;kali&gt; &lt;interval&gt;</code> (sambil reply)",
                    "<i>contoh: .promosi 5 1 jam</i>",
                    "<code>.promosi &lt;teks&gt; &lt;kali&gt; &lt;interval&gt;</code>",
                    "<i>contoh: .promosi Jual Diamond 3 30 menit</i>",
                ],
                catatan="Reply lebih disarankan: pesannya diteruskan utuh "
                        "beserta emoji premium & media dari sumber aslinya.",
            )
            return

        teks_diurai, putaran_diurai, interval_diurai = baca_argumen_promosi(argumen_mentah)
        teks_biasa = (teks_diurai or "").strip()
        chat_id = event.chat_id
        sumber = "Diteruskan dari pesan yang di-reply" if pesan_sumber else "Teks sendiri"

        # Kasus 1: jumlah putaran & interval sudah ditulis langsung di perintah.
        if putaran_diurai is not None and interval_diurai is not None:
            await mulai_job(
                event,
                chat_id,
                pesan_sumber,
                teks_biasa,
                putaran_diurai,
                interval_diurai,
                sumber,
            )
            return

        # Kasus 2: buka menu interaktif.
        await balas_panel(
            event,
            "🚀 MENU PROMOSI",
            [
                "<b>[ 1 ]</b>  Kirim sekali sekarang",
                "<b>[ 2 ]</b>  Atur jumlah &amp; interval",
                "<b>[ 0 ]</b>  Batal",
                "",
                f"📨 Sumber : <b>{sumber}</b>",
            ],
            catatan="Ketik angka pilihanmu (otomatis terhapus).",
        )

        jawaban = await tunggu_jawaban(klien, chat_id, batas_detik=60)
        if not jawaban:
            await balas_panel(event, "⌛ WAKTU HABIS", ["Promosi dibatalkan otomatis."])
            return

        if jawaban in ("0", "batal", "cancel", "b"):
            await balas_panel(event, "❌ DIBATALKAN", ["Tidak ada pesan yang dikirim."])
            return

        if jawaban == "1":
            await mulai_job(event, chat_id, pesan_sumber, teks_biasa, 1, 0, sumber)
            return

        if jawaban == "2":
            # Langkah 1 — jumlah putaran.
            await balas_panel(
                event,
                "📝 LANGKAH 1/2 — JUMLAH KIRIM",
                ["Mau berapa kali pesan dikirim ke semua grup?", "<i>contoh: 2, 5, atau 10</i>"],
                catatan="Ketik angka, atau 0 untuk batal.",
            )
            jawaban_jumlah = await tunggu_jawaban(klien, chat_id, batas_detik=60)
            if not jawaban_jumlah or jawaban_jumlah in ("0", "batal"):
                await balas_panel(event, "❌ DIBATALKAN", ["Tidak ada pesan yang dikirim."])
                return

            try:
                jumlah_putaran = int(jawaban_jumlah)
                if jumlah_putaran <= 0:
                    raise ValueError
            except ValueError:
                await balas_panel(event, "❌ FORMAT SALAH", ["Jumlah kirim harus angka bulat positif."])
                return

            # Langkah 2 — interval antar putaran.
            await balas_panel(
                event,
                f"⏱ LANGKAH 2/2 — INTERVAL ({jumlah_putaran}x KIRIM)",
                ["Kirim ulang setiap berapa lama?", "<i>contoh: 1 jam, 30 menit, atau 10m</i>"],
                catatan="Ketik durasinya, atau 0 untuk batal.",
            )
            jawaban_waktu = await tunggu_jawaban(klien, chat_id, batas_detik=60)
            if not jawaban_waktu or jawaban_waktu in ("0", "batal"):
                await balas_panel(event, "❌ DIBATALKAN", ["Tidak ada pesan yang dikirim."])
                return

            interval_detik = baca_durasi(jawaban_waktu)
            if interval_detik <= 0:
                await balas_panel(
                    event,
                    "❌ FORMAT WAKTU SALAH",
                    ["Gunakan format seperti <code>1 jam</code> atau <code>15 menit</code>."],
                )
                return

            await mulai_job(
                event, chat_id, pesan_sumber, teks_biasa, jumlah_putaran, interval_detik, sumber
            )
            return

        await balas_panel(event, "❌ PILIHAN TIDAK VALID", ["Ulangi dengan <code>.promosi</code>."])


async def mulai_job(event, chat_id, pesan_sumber, teks_biasa, jumlah_putaran, interval_detik, sumber):
    """Daftarkan job promosi baru, tampilkan ringkasannya, lalu lepas ke background."""
    NOMOR_JOB["terakhir"] += 1
    id_job = NOMOR_JOB["terakhir"]

    ringkasan = [
        ("Job", f"#{id_job}"),
        ("Jumlah kirim", f"{jumlah_putaran}x"),
        ("Interval", format_durasi(interval_detik) if interval_detik else "sekali jalan"),
        ("Jeda/grup", f"{konfig['delay_min']}–{konfig['delay_max']} detik"),
        ("Sumber", sumber),
    ]
    await balas_panel(
        event,
        "🚀 PROMOSI DIMULAI",
        ringkasan,
        catatan="Jalan di background. Ketik .stop untuk menghentikan.",
    )

    tugas = asyncio.create_task(
        jalankan_promosi(id_job, chat_id, pesan_sumber, teks_biasa, jumlah_putaran, interval_detik)
    )
    DAFTAR_JOB[id_job] = {"task": tugas, "stop": False, "chat_id": chat_id}


async def jalankan_promosi(id_job, chat_id, pesan_sumber, teks_biasa, jumlah_putaran=1, interval_detik=0):
    """
    Worker promosi di background.
    Daftar grup di-ambil ulang tiap putaran, jadi grup baru yang kita masuki
    di tengah jadwal ikut kena promosi tanpa perlu restart bot.
    """
    job = DAFTAR_JOB[id_job]
    akumulasi_sukses = 0
    akumulasi_gagal = 0
    akumulasi_dilewati = 0
    putaran_terakhir = 0

    try:
        for putaran in range(1, jumlah_putaran + 1):
            if job["stop"]:
                break
            putaran_terakhir = putaran

            daftar_grup = []
            async for dialog in klien.iter_dialogs():
                if dialog.is_group and not sedang_diblacklist(dialog.id):
                    daftar_grup.append(dialog)

            jumlah_grup = len(daftar_grup)
            if jumlah_grup == 0:
                await kirim_panel(
                    klien,
                    chat_id,
                    f"⚠️ PROMOSI #{id_job} BERHENTI",
                    ["Tidak ada grup yang bisa dikirimi.", "Semua grup masuk daftar hitam?"],
                )
                return

            if jumlah_putaran > 1:
                await kirim_panel(
                    klien,
                    chat_id,
                    f"🚀 PROMOSI #{id_job} — PUTARAN {putaran}/{jumlah_putaran}",
                    [("Target", f"{jumlah_grup} grup")],
                    catatan="Sedang mengirim...",
                )

            sukses, gagal, dilewati = 0, 0, 0
            for nomor, dialog in enumerate(daftar_grup, 1):
                if job["stop"]:
                    break
                try:
                    await kirim_promosi_ke(klien, dialog.id, pesan_sumber, teks_biasa)
                    sukses += 1
                except FloodWaitError as e:
                    # Telegram minta kita sabar. Dibatasi 300 detik biar job gak ngegantung kelamaan.
                    await asyncio.sleep(min(e.seconds + 2, 300))
                    try:
                        await kirim_promosi_ke(klien, dialog.id, pesan_sumber, teks_biasa)
                        sukses += 1
                    except Exception:
                        gagal += 1
                except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError):
                    # Bukan error kita: memang gak boleh nulis di situ. Lewati tanpa drama.
                    dilewati += 1
                except Exception:
                    gagal += 1

                if nomor < jumlah_grup and not job["stop"]:
                    await asyncio.sleep(random.uniform(konfig["delay_min"], konfig["delay_max"]))

            akumulasi_sukses += sukses
            akumulasi_gagal += gagal
            akumulasi_dilewati += dilewati

            await kirim_panel(
                klien,
                chat_id,
                f"📊 PROMOSI #{id_job} — PUTARAN {putaran}/{jumlah_putaran}",
                [
                    ("✅ Berhasil", sukses),
                    ("❌ Gagal", gagal),
                    ("⏩ Dilewati", dilewati),
                    ("👥 Total grup", jumlah_grup),
                ],
            )

            if putaran < jumlah_putaran and not job["stop"]:
                await kirim_panel(
                    klien,
                    chat_id,
                    f"⏳ PROMOSI #{id_job} — JEDA",
                    [
                        ("Menunggu", format_durasi(interval_detik)),
                        ("Putaran berikutnya", f"{putaran + 1}/{jumlah_putaran}"),
                    ],
                    catatan="Ketik .stop untuk berhenti.",
                )

                # Tidur dicicil per detik supaya .stop terasa responsif.
                for _ in range(interval_detik):
                    if job["stop"]:
                        break
                    await asyncio.sleep(1)

        judul_akhir = (
            f"🛑 PROMOSI #{id_job} DIHENTIKAN" if job["stop"]
            else f"🎉 PROMOSI #{id_job} SELESAI"
        )
        await kirim_panel(
            klien,
            chat_id,
            judul_akhir,
            [
                ("🔁 Putaran", f"{putaran_terakhir}/{jumlah_putaran}"),
                ("✅ Total berhasil", akumulasi_sukses),
                ("❌ Total gagal", akumulasi_gagal),
                ("⏩ Total dilewati", akumulasi_dilewati),
            ],
        )

    except asyncio.CancelledError:
        raise
    except Exception as e:
        await kirim_panel(klien, chat_id, f"❌ PROMOSI #{id_job} ERROR", [str(e)])
    finally:
        DAFTAR_JOB.pop(id_job, None)


# ---------------------------------------------------------------------------
# Titik masuk
# ---------------------------------------------------------------------------
async def utama():
    daftarkan_perintah()
    print("Menghubungkan ke Telegram...")
    await klien.connect()

    if not await klien.is_user_authorized():
        nomor = input("Masukkan nomor telepon (mis. +628123456789): ").strip()
        await klien.send_code_request(nomor)
        try:
            kode = input("Masukkan kode OTP: ").strip()
            await klien.sign_in(phone=nomor, code=kode)
        except SessionPasswordNeededError:
            sandi = input("Akun pakai 2FA. Masukkan password: ").strip()
            await klien.sign_in(password=sandi)

    saya = await klien.get_me()
    nama = saya.first_name or ""
    username = f" (@{saya.username})" if saya.username else ""
    print(f"\n✅ Login sukses sebagai: {nama}{username}")
    print("Userbot berjalan. Ketik .help di Telegram. Tekan Ctrl+C untuk berhenti.\n")

    await klien.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(utama())
    except KeyboardInterrupt:
        print("\nUserbot dihentikan.")
