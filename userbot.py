"""
Userbot Telegram - Promosi ke Grup
Pakai Telethon (login akun asli, bukan bot token).

Jalankan: python userbot.py
Perintah: .promote | .promosi | .addbl | .delbl | .listbl | .setdelay | .stop | .ping | .id | .help
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

CONFIG_FILE = "config.json"
SESSION_NAME = "userbot"

DEFAULT_CONFIG = {
    "api_id": 0,
    "api_hash": "",
    "delay_min": 5,
    "delay_max": 12,
    "blacklist": [],
}



# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            print("[!] config.json rusak, memakai default.")
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


config = load_config()

# State runtime: banyak job promosi bisa jalan bersamaan.
# jobs[id] = {"task": asyncio.Task, "stop": bool, "chat_id": int}
JOBS = {}
JOB_SEQ = {"n": 0}


# ---------------------------------------------------------------------------
# Helper Tampilan & Durasi
# ---------------------------------------------------------------------------
def bq(text: str) -> str:
    """Bungkus teks jadi blockquote HTML."""
    return "<blockquote>" + text + "</blockquote>"


async def reply_bq(event, text: str):
    """Balas pesan dalam format blockquote."""
    await event.reply(bq(text), parse_mode="html")


def parse_duration(text: str) -> int:
    """
    Parse durasi teks ke detik.
    Contoh: '1 jam', '2 hours', '10 menit', '30m', '45 detik', '60s', '1.5 jam'
    Return total detik (int). Return 0 jika tidak valid.
    """
    if not text:
        return 0
    text = text.lower().strip()

    # Cek format gabungan seperti '1 jam 30 menit' atau '10m'
    total_seconds = 0
    patterns = [
        (r'(\d+(?:\.\d+)?)\s*(?:jam|hours?|hr|h|j)\b', 3600),
        (r'(\d+(?:\.\d+)?)\s*(?:menit|mins?|minute|m)\b', 60),
        (r'(\d+(?:\.\d+)?)\s*(?:detik|secs?|second|s)\b', 1),
    ]

    matched = False
    for pat, multiplier in patterns:
        m = re.search(pat, text)
        if m:
            matched = True
            total_seconds += float(m.group(1)) * multiplier

    if not matched:
        # Cek jika cuma angka (asumsikan menit)
        try:
            val = float(text)
            return int(val * 60)
        except ValueError:
            return 0

    return int(total_seconds)


def format_duration(seconds: int) -> str:
    """Format detik ke teks yang mudah dibaca."""
    if seconds >= 3600:
        jam = seconds // 3600
        sisa = seconds % 3600
        menit = sisa // 60
        if menit > 0:
            return f"{jam} jam {menit} menit"
        return f"{jam} jam"
    elif seconds >= 60:
        menit = seconds // 60
        sisa = seconds % 60
        if sisa > 0:
            return f"{menit} menit {sisa} detik"
        return f"{menit} menit"
    return f"{seconds} detik"


def parse_promote_args(arg_text: str):
    """
    Parse argument promote:
    Bisa berupa:
    - '5 1 jam' -> ('', 5, 3600)
    - 'Jual Akun Murah 3 30 menit' -> ('Jual Akun Murah', 3, 1800)
    - 'Jual Akun Murah' -> ('Jual Akun Murah', None, None)
    - '' -> ('', None, None)
    """
    if not arg_text:
        return "", None, None

    arg_text = arg_text.strip()

    # Match format [teks opsional] <repeat_count> <interval>
    # Contoh: "5 1 jam", "3 10m", "jual akun 10 30 menit"
    pattern = r'^(?:([\s\S]+?)\s+)?(\d+)\s+(\d+(?:\.\d+)?\s*(?:jam|hours?|hr|h|j|menit|mins?|minute|m|detik|secs?|second|s)(?:[\s\S]*)?)$'
    m = re.match(pattern, arg_text, re.IGNORECASE)
    if m:
        text_part = (m.group(1) or "").strip()
        repeat_count = int(m.group(2))
        dur_str = m.group(3).strip()
        interval_secs = parse_duration(dur_str)
        if repeat_count > 0 and interval_secs > 0:
            return text_part, repeat_count, interval_secs

    return arg_text, None, None


async def wait_user_input(client, chat_id, timeout=60):
    """
    Menunggu respon berikutnya yang diketik oleh kita sendiri di chat ini.
    Mengembalikan (text, event) atau (None, None) jika timeout.
    """
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    async def _handler(e):
        # Pastikan dari chat yang sama dan pesan baru
        if e.chat_id == chat_id and not fut.done():
            fut.set_result(e)

    client.add_event_handler(_handler, events.NewMessage(chats=chat_id, outgoing=True))

    try:
        resp_event = await asyncio.wait_for(fut, timeout=timeout)
        text = resp_event.text.strip()
        # Otomatis hapus pesan input kita agar tampilan chat tetap bersih
        try:
            await resp_event.delete()
        except Exception:
            pass
        return text, resp_event
    except asyncio.TimeoutError:
        return None, None
    finally:
        client.remove_event_handler(_handler)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def ensure_api_credentials():
    """Minta api_id / api_hash kalau belum ada, lalu simpan."""
    if not config.get("api_id") or not config.get("api_hash"):
        print("== Setup API (sekali saja) ==")
        print("Ambil di https://my.telegram.org > API development tools\n")
        while True:
            try:
                config["api_id"] = int(input("Masukkan api_id  : ").strip())
                break
            except ValueError:
                print("api_id harus angka.")
        config["api_hash"] = input("Masukkan api_hash: ").strip()
        save_config(config)


# ---------------------------------------------------------------------------
# Blacklist helpers
# ---------------------------------------------------------------------------
async def resolve_target_id(client, ref):
    """Ubah @username / id / -100id jadi id numerik. None kalau gagal."""
    ref = str(ref).strip()
    try:
        if ref.lstrip("-").isdigit():
            ent = await client.get_entity(int(ref))
        else:
            ent = await client.get_entity(ref)
        return ent.id
    except Exception:
        return None


def in_blacklist(chat_id) -> bool:
    return int(chat_id) in [int(x) for x in config.get("blacklist", [])]


# ---------------------------------------------------------------------------
# Bangun konten promosi
# ---------------------------------------------------------------------------
async def send_promo_to(client, target, source_msg, plain_text):
    """
    Kirim promosi ke satu target.
    - Kalau source_msg (pesan yang di-reply) ada -> teruskan apa adanya
      (teks + entities termasuk emoji premium/custom + media).
    - Kalau tidak, kirim plain_text biasa.
    """
    if source_msg is not None:
        # Pertahankan teks, formatting, custom/premium emoji, dan media.
        await client.send_message(
            target,
            message=source_msg.message or "",
            formatting_entities=source_msg.entities or None,
            file=source_msg.media if source_msg.media else None,
        )
    else:
        await client.send_message(target, plain_text)


# ---------------------------------------------------------------------------
# Client + handler registration
# ---------------------------------------------------------------------------
ensure_api_credentials()
client = TelegramClient(SESSION_NAME, config["api_id"], config["api_hash"])


def register_handlers():
    # Cuma perintah dari akun sendiri (outgoing)
    def cmd(pattern):
        return events.NewMessage(outgoing=True, pattern=pattern)

    # .ping ---------------------------------------------------------------
    @client.on(cmd(r"^\.ping$"))
    async def _ping(event):
        await event.edit(bq("🏓 Pong! Userbot aktif."), parse_mode="html")

    # .id -----------------------------------------------------------------
    @client.on(cmd(r"^\.id$"))
    async def _id(event):
        chat = await event.get_chat()
        me = await event.get_sender()
        text = (
            f"🆔 Info\n"
            f"Chat ID : {event.chat_id}\n"
            f"User ID : {getattr(me, 'id', '-')}"
        )
        await event.edit(bq(text), parse_mode="html")

    # .help ---------------------------------------------------------------
    @client.on(cmd(r"^\.help$"))
    async def _help(event):
        text = (
            "📖 <b>Daftar Perintah Userbot</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "• <code>.promote &lt;teks&gt;</code> atau reply pesan\n"
            "  <i>Buka menu: [1] Kirim 1x, [2] Manual, [0] Batal</i>\n"
            "• <code>.promote &lt;teks&gt; &lt;kali&gt; &lt;interval&gt;</code>\n"
            "  <i>Contoh: .promote 5 1 jam (sambil reply)</i>\n"
            "  <i>Contoh: .promote Promo Hebat 3 30 menit</i>\n"
            "• <code>.addbl [@user/id]</code> — Blacklist grup\n"
            "• <code>.delbl [@user/id]</code> — Hapus dari blacklist\n"
            "• <code>.listbl</code> — Lihat daftar blacklist\n"
            "• <code>.setdelay &lt;min&gt; &lt;max&gt;</code> — Atur jeda per grup\n"
            "• <code>.stop</code> — Hentikan semua promosi\n"
            "• <code>.ping</code> / <code>.id</code> — Cek status & ID"
        )
        await event.edit(bq(text), parse_mode="html")

    # .setdelay -----------------------------------------------------------
    @client.on(cmd(r"^\.setdelay(?:\s+(\d+)\s+(\d+))?$"))
    async def _setdelay(event):
        m = event.pattern_match
        if not m.group(1):
            await event.edit(
                bq(f"⏱ Delay sekarang: {config['delay_min']}–{config['delay_max']} detik.\n"
                   "Ubah: .setdelay <min> <max>"),
                parse_mode="html",
            )
            return
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        config["delay_min"], config["delay_max"] = lo, hi
        save_config(config)
        await event.edit(bq(f"✅ Delay diset {lo}–{hi} detik."), parse_mode="html")

    # .stop ---------------------------------------------------------------
    @client.on(cmd(r"^\.stop$"))
    async def _stop(event):
        active = [j for j in JOBS.values() if not j["stop"]]
        if not active:
            await event.edit(bq("Tidak ada promosi yang berjalan."), parse_mode="html")
            return
        for j in JOBS.values():
            j["stop"] = True
        await event.edit(
            bq(f"🛑 Menghentikan {len(active)} promosi yang berjalan..."),
            parse_mode="html",
        )

    # .addbl --------------------------------------------------------------
    @client.on(cmd(r"^\.addbl(?:\s+(.+))?$"))
    async def _addbl(event):
        arg = event.pattern_match.group(1)
        if arg:
            tid = await resolve_target_id(client, arg.strip())
            if tid is None:
                await event.edit(bq("❌ Grup/target tidak ditemukan."), parse_mode="html")
                return
        else:
            tid = event.chat_id  # grup tempat perintah diketik
        bl = config.setdefault("blacklist", [])
        if int(tid) in [int(x) for x in bl]:
            await event.edit(bq("ℹ️ Grup itu sudah di blacklist."), parse_mode="html")
            return
        bl.append(int(tid))
        save_config(config)
        await event.edit(bq(f"✅ Ditambahkan ke blacklist: {tid}"), parse_mode="html")

    # .delbl --------------------------------------------------------------
    @client.on(cmd(r"^\.delbl(?:\s+(.+))?$"))
    async def _delbl(event):
        arg = event.pattern_match.group(1)
        if arg:
            tid = await resolve_target_id(client, arg.strip())
            if tid is None:
                await event.edit(bq("❌ Grup/target tidak ditemukan."), parse_mode="html")
                return
        else:
            tid = event.chat_id
        bl = config.setdefault("blacklist", [])
        bl_int = [int(x) for x in bl]
        if int(tid) not in bl_int:
            await event.edit(bq("ℹ️ Grup itu tidak ada di blacklist."), parse_mode="html")
            return
        config["blacklist"] = [x for x in bl if int(x) != int(tid)]
        save_config(config)
        await event.edit(bq(f"✅ Dihapus dari blacklist: {tid}"), parse_mode="html")

    # .listbl -------------------------------------------------------------
    @client.on(cmd(r"^\.listbl$"))
    async def _listbl(event):
        bl = config.get("blacklist", [])
        if not bl:
            await event.edit(bq("📭 Blacklist kosong."), parse_mode="html")
            return
        lines = ["🚫 Daftar Blacklist:"]
        for i, x in enumerate(bl, 1):
            lines.append(f"{i}. {x}")
        await event.edit(bq("\n".join(lines)), parse_mode="html")

    # .promote / .promosi -------------------------------------------------
    @client.on(cmd(r"^\.(?:promote|promosi)(?:\s+([\s\S]+))?$"))
    async def _promote(event):
        reply_msg = await event.get_reply_message()
        raw_arg = event.pattern_match.group(1)

        # Cek apakah tidak ada reply dan tidak ada argumen
        if reply_msg is None and not raw_arg:
            panduan = (
                "📖 <b>Cara Pakai Promosi:</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "• <b>Menu Interaktif:</b>\n"
                "  Reply pesan lalu ketik <code>.promote</code>\n"
                "  <i>(Akan muncul pilihan Kirim 1x / Manual / Batal)</i>\n\n"
                "• <b>Format Cepat:</b>\n"
                "  <code>.promote &lt;teks&gt; &lt;jumlah_kali&gt; &lt;interval&gt;</code>\n"
                "  <i>Contoh: .promote 5 1 jam</i> (sambil reply)\n"
                "  <i>Contoh: .promote Jual Diamond 3 30 menit</i>"
            )
            await event.edit(bq(panduan), parse_mode="html")
            return

        # Parsing argumen jika ada
        text_parsed, repeat_parsed, interval_parsed = parse_promote_args(raw_arg)
        plain_text = text_parsed.strip() if text_parsed else ""

        chat_id = event.chat_id

        # KASUS 1: Parameter repeat & interval sudah lengkap diberikan di command
        if repeat_parsed is not None and interval_parsed is not None:
            JOB_SEQ["n"] += 1
            job_id = JOB_SEQ["n"]
            info = (
                f"🚀 <b>Promosi #{job_id} Dimulai!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔁 Jumlah Kirim : <b>{repeat_parsed}x</b>\n"
                f"⏱ Interval      : <b>{format_duration(interval_parsed)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<i>Berjalan di background. Ketik <code>.stop</code> untuk batal.</i>"
            )
            await event.edit(bq(info), parse_mode="html")
            task = asyncio.create_task(
                _run_promo(job_id, chat_id, reply_msg, plain_text, repeat_parsed, interval_parsed)
            )
            JOBS[job_id] = {"task": task, "stop": False, "chat_id": chat_id}
            return

        # KASUS 2: Buka Menu Interaktif ([1] Kirim 1x, [2] Manual, [0] Batal)
        menu_text = (
            "🚀 <b>PILIHAN PROMOSI</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>[ 1 ]</b> Kirim 1 Kali\n"
            "<b>[ 2 ]</b> Manual <i>(Set Jumlah & Interval)</i>\n"
            "<b>[ 0 ]</b> Batal ❌\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Balas / ketik: <b>1</b>, <b>2</b>, atau <b>0</b></i>"
        )
        await event.edit(bq(menu_text), parse_mode="html")

        # Tunggu respon pilihan menu
        ans, ans_event = await wait_user_input(client, chat_id, timeout=60)
        if not ans:
            await event.edit(bq("⌛ Waktu habis. Promosi dibatalkan."), parse_mode="html")
            return

        # PILIHAN 0: Batal
        if ans in ("0", "batal", "cancel", "b"):
            await event.edit(bq("❌ <b>Promosi Dibatalkan.</b>"), parse_mode="html")
            return

        # PILIHAN 1: Kirim 1 Kali
        if ans == "1":
            JOB_SEQ["n"] += 1
            job_id = JOB_SEQ["n"]
            await event.edit(
                bq(f"🚀 <b>Promosi #{job_id} (1x) Dimulai!</b>\n"
                   f"<i>Berjalan di background. Ketik <code>.stop</code> untuk batal.</i>"),
                parse_mode="html",
            )
            task = asyncio.create_task(
                _run_promo(job_id, chat_id, reply_msg, plain_text, repeat_count=1, interval_secs=0)
            )
            JOBS[job_id] = {"task": task, "stop": False, "chat_id": chat_id}
            return

        # PILIHAN 2: Manual
        if ans == "2":
            # Langkah 1: Minta jumlah kali kirim
            prompt_kali = (
                "📝 <b>Langkah 1/2 — Frekuensi Kirim</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Mau berapa kali pesan dikirim ke semua grup?\n"
                "<i>(Contoh ketik: <b>2</b>, <b>5</b>, atau <b>10</b>)</i>\n\n"
                "<i>Ketik angka, atau <b>0</b> untuk batal</i>"
            )
            await event.edit(bq(prompt_kali), parse_mode="html")

            ans_kali, _ = await wait_user_input(client, chat_id, timeout=60)
            if not ans_kali or ans_kali in ("0", "batal"):
                await event.edit(bq("❌ <b>Promosi Dibatalkan.</b>"), parse_mode="html")
                return

            try:
                repeat_count = int(ans_kali)
                if repeat_count <= 0:
                    raise ValueError
            except ValueError:
                await event.edit(bq("❌ Jumlah kirim harus berupa angka bulat positif."), parse_mode="html")
                return

            # Langkah 2: Minta interval waktu
            prompt_waktu = (
                f"⏱ <b>Langkah 2/2 — Interval Waktu ({repeat_count}x kirim)</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Kirim setiap berapa jam atau menit?\n"
                "<i>(Contoh: <b>1 jam</b>, <b>30 menit</b>, atau <b>10m</b>)</i>\n\n"
                "<i>Ketik durasi waktu, atau <b>0</b> untuk batal</i>"
            )
            await event.edit(bq(prompt_waktu), parse_mode="html")

            ans_waktu, _ = await wait_user_input(client, chat_id, timeout=60)
            if not ans_waktu or ans_waktu in ("0", "batal"):
                await event.edit(bq("❌ <b>Promosi Dibatalkan.</b>"), parse_mode="html")
                return

            interval_secs = parse_duration(ans_waktu)
            if interval_secs <= 0:
                await event.edit(
                    bq("❌ Format waktu tidak valid. Gunakan misal: <code>1 jam</code> atau <code>15 menit</code>."),
                    parse_mode="html",
                )
                return

            # Mulai job background
            JOB_SEQ["n"] += 1
            job_id = JOB_SEQ["n"]
            info = (
                f"✅ <b>Promosi Terjadwal #{job_id}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔁 Jumlah Kirim : <b>{repeat_count}x</b>\n"
                f"⏱ Interval      : <b>{format_duration(interval_secs)}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<i>Memulai putaran ke-1 di background...</i>\n"
                f"<i>Ketik <code>.stop</code> untuk menghentikan.</i>"
            )
            await event.edit(bq(info), parse_mode="html")

            task = asyncio.create_task(
                _run_promo(job_id, chat_id, reply_msg, plain_text, repeat_count, interval_secs)
            )
            JOBS[job_id] = {"task": task, "stop": False, "chat_id": chat_id}
            return

        # Pilihan tidak dikenal
        await event.edit(bq("❌ Pilihan tidak valid. Silakan ulangi <code>.promote</code>."), parse_mode="html")


async def _run_promo(job_id, chat_id, reply_msg, plain_text, repeat_count=1, interval_secs=0):
    """
    Worker promosi yang jalan di background.
    Mendukung perulangan (repeat_count) dengan jeda interval (interval_secs).
    """
    job = JOBS[job_id]
    total_sukses = 0
    total_gagal = 0
    total_dilewati = 0

    try:
        for current_round in range(1, repeat_count + 1):
            if job["stop"]:
                break

            # Ambil semua grup terbaru yang bukan blacklist
            groups = []
            async for dialog in client.iter_dialogs():
                if dialog.is_group and not in_blacklist(dialog.id):
                    groups.append(dialog)

            total_groups = len(groups)
            if total_groups == 0:
                await client.send_message(
                    chat_id,
                    bq(f"⚠️ <b>Promosi #{job_id}</b>: Tidak ada grup yang ditemukan / semua di-blacklist."),
                    parse_mode="html",
                )
                return

            if repeat_count > 1:
                await client.send_message(
                    chat_id,
                    bq(f"🚀 <b>Promosi #{job_id} — Putaran {current_round}/{repeat_count}</b>\n"
                       f"Mengirim ke {total_groups} grup (jeda {config['delay_min']}–{config['delay_max']} dtk/grup)..."),
                    parse_mode="html",
                )

            sukses, gagal, dilewati = 0, 0, 0
            for idx, dialog in enumerate(groups, 1):
                if job["stop"]:
                    break
                try:
                    await send_promo_to(client, dialog.id, reply_msg, plain_text)
                    sukses += 1
                except FloodWaitError as e:
                    wait = min(e.seconds + 2, 300)
                    await asyncio.sleep(wait)
                    try:
                        await send_promo_to(client, dialog.id, reply_msg, plain_text)
                        sukses += 1
                    except Exception:
                        gagal += 1
                except (ChatWriteForbiddenError, UserBannedInChannelError, ChannelPrivateError):
                    dilewati += 1
                except Exception:
                    gagal += 1

                # Jeda acak antar grup
                if idx < total_groups and not job["stop"]:
                    await asyncio.sleep(random.uniform(config["delay_min"], config["delay_max"]))

            total_sukses += sukses
            total_gagal += gagal
            total_dilewati += dilewati

            # Notifikasi hasil per putaran
            status_round = (
                f"📊 <b>Promosi #{job_id} — Putaran {current_round}/{repeat_count}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"✅ Berhasil : {sukses}\n"
                f"❌ Gagal    : {gagal}\n"
                f"⏩ Dilewati : {dilewati}\n"
                f"👥 Total    : {total_groups} grup"
            )
            await client.send_message(chat_id, bq(status_round), parse_mode="html")

            # Jika masih ada putaran berikutnya, tunggu selama interval_secs
            if current_round < repeat_count and not job["stop"]:
                await client.send_message(
                    chat_id,
                    bq(f"⏳ <b>Promosi #{job_id}</b>\n"
                       f"Menunggu <b>{format_duration(interval_secs)}</b> sebelum putaran ke-{current_round + 1}...\n"
                       f"<i>Ketik <code>.stop</code> untuk berhenti.</i>"),
                    parse_mode="html",
                )

                # Tidur bertahap agar bisa dihentikan kapan saja via .stop
                for _ in range(interval_secs):
                    if job["stop"]:
                        break
                    await asyncio.sleep(1)

        # Laporan Akhir Keseluruhan
        status_final = "🛑 <b>Promosi Dihentikan</b>" if job["stop"] else "🎉 <b>Semua Putaran Promosi Selesai!</b>"
        hasil_total = (
            f"{status_final} — Job #{job_id}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔁 Total Putaran : {current_round}/{repeat_count}\n"
            f"✅ Total Sukses  : {total_sukses}\n"
            f"❌ Total Gagal   : {total_gagal}\n"
            f"⏩ Total Dilewati: {total_dilewati}"
        )
        await client.send_message(chat_id, bq(hasil_total), parse_mode="html")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        await client.send_message(
            chat_id, bq(f"❌ <b>Promosi #{job_id} Error:</b> {e}"), parse_mode="html"
        )
    finally:
        JOBS.pop(job_id, None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    register_handlers()
    print("Menghubungkan ke Telegram...")
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Masukkan nomor telepon (mis. +628123456789): ").strip()
        await client.send_code_request(phone)
        try:
            code = input("Masukkan kode OTP: ").strip()
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            pw = input("Akun pakai 2FA. Masukkan password: ").strip()
            await client.sign_in(password=pw)

    me = await client.get_me()
    nama = me.first_name or ""
    uname = f" (@{me.username})" if me.username else ""
    print(f"\n✅ Login sukses sebagai: {nama}{uname}")
    print("Userbot berjalan. Ketik .help di Telegram. Tekan Ctrl+C untuk berhenti.\n")

    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nUserbot dihentikan.")
