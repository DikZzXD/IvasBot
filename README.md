<div align="center">

# 🤖 IvasBot

**Userbot Telegram buat promosi massal ke semua grup — sekali ketik, langsung jalan.**

Pesan yang kamu reply akan **diteruskan (forward) apa adanya**, jadi emoji premium,
format teks, dan media dari akun/channel aslinya tetap utuh.

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Telethon-userbot-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://docs.telethon.dev/)
[![Status](https://img.shields.io/badge/status-aktif-success?style=flat-square)](#)

</div>

---

## ✨ Apa yang Bisa Dilakukan

| Fitur | Penjelasan |
|---|---|
| 📣 **Promosi massal** | Kirim ke semua grup yang kamu ikuti sekaligus, otomatis |
| 🔁 **Promosi terjadwal** | Ulangi beberapa kali dengan interval yang kamu tentukan |
| 💎 **Forward asli** | Reply pesan premium/channel → diteruskan utuh, emoji premium gak rontok |
| 🚫 **Daftar hitam** | Kecualikan grup tertentu, dan chat perintahnya otomatis terhapus |
| ⏱ **Jeda acak** | Jeda antar grup dibuat acak biar gak gampang kena limit Telegram |
| 🧵 **Multi-job** | Beberapa jadwal promosi bisa jalan barengan |
| 🎨 **Tampilan panel** | Semua balasan rapi dalam blockquote yang seragam |

---

## 📦 Instalasi

```bash
git clone https://github.com/DikZzXD/IvasBot.git
cd IvasBot
pip install telethon
python userbot.py
```

Saat pertama kali jalan, bot akan minta:

1. **`api_id`** dan **`api_hash`** — ambil di [my.telegram.org](https://my.telegram.org) → *API development tools*
2. **Nomor telepon** + kode OTP dari Telegram
3. **Password 2FA** (kalau akunmu mengaktifkan verifikasi dua langkah)

Semuanya cuma ditanya sekali. Setelah itu sesi login disimpan di `userbot.session`.

> ⚠️ **Jangan pernah commit** `config.json` dan `userbot.session` ke repository publik —
> keduanya berisi kredensial dan sesi login akun Telegram kamu.

---

## 🚀 Cara Pakai Promosi

### Cara 1 — Menu interaktif (paling gampang)

Reply pesan yang mau dipromosikan, lalu ketik:

```
.promosi
```

Muncul menu:

```
🚀 MENU PROMOSI
━━━━━━━━━━━━━━━━━━━━
[ 1 ]  Kirim sekali sekarang
[ 2 ]  Atur jumlah & interval
[ 0 ]  Batal

📨 Sumber : Diteruskan dari pesan yang di-reply
━━━━━━━━━━━━━━━━━━━━
Ketik angka pilihanmu (otomatis terhapus).
```

Tinggal balas `1`, `2`, atau `0`. Jawabanmu langsung dihapus supaya chat tetap bersih.

### Cara 2 — Format cepat (satu baris langsung jalan)

```
.promosi 5 1 jam                    ← sambil reply pesan
.promosi Jual Diamond 3 30 menit    ← pakai teks sendiri
```

Polanya: `.promosi <teks opsional> <jumlah kirim> <interval>`

Format waktu yang dikenali: `1 jam`, `30 menit`, `10m`, `45 detik`, `1.5 jam`, `2h`.
Angka polos seperti `15` dianggap **15 menit**.

---

## 📖 Daftar Perintah

### Promosi

| Perintah | Fungsi |
|---|---|
| `.promosi` | Buka menu interaktif (reply pesan dulu) |
| `.promosi <kali> <interval>` | Promosi terjadwal dari pesan yang di-reply |
| `.promosi <teks> <kali> <interval>` | Promosi terjadwal pakai teks sendiri |
| `.stop` | Hentikan semua promosi yang sedang jalan |

### Daftar Hitam

| Perintah | Fungsi |
|---|---|
| `.addbl` | Blacklist grup tempat perintah diketik |
| `.addbl @user / <id>` | Blacklist grup tertentu |
| `.delbl` / `.delbl <id>` | Keluarkan grup dari daftar hitam |
| `.listbl` | Lihat semua grup yang di-blacklist |

> 💡 `.addbl` dan `.delbl` **otomatis menghapus pesan perintahnya** setelah beberapa detik,
> jadi anggota grup lain gak sadar grup mereka kamu kecualikan.

### Lain-lain

| Perintah | Fungsi |
|---|---|
| `.setdelay <min> <max>` | Atur jeda acak antar grup (detik) |
| `.setdelay` | Lihat jeda yang sedang aktif |
| `.ping` | Cek userbot masih hidup |
| `.id` | Lihat Chat ID & User ID |
| `.help` | Tampilkan semua perintah |

---

## 💎 Kenapa Pakai Forward, Bukan Salin Ulang?

Ini bagian yang paling sering bikin bingung, jadi dijelaskan pelan-pelan:

- **Emoji premium** cuma bisa tampil kalau **pengirimnya** punya Telegram Premium.
  Kalau pesan orang premium kita *salin*, akun kita jadi pengirimnya — emoji premiumnya rontok jadi emoji biasa.
- Dengan **forward**, pesannya tetap milik pengirim asli. Emoji premium, format, media,
  semuanya utuh, plus ada label *"Diteruskan dari …"* sebagai kredit ke sumbernya.

Kalau grup tujuan mematikan penerusan pesan (*protected content*), bot otomatis
jatuh ke mode salin manual — daripada promosinya gagal total.

---

## ⚙️ Konfigurasi

`config.json` dibuat otomatis, tapi bisa diedit manual:

```json
{
  "api_id": 12345678,
  "api_hash": "isi_api_hash_kamu",
  "delay_min": 3,
  "delay_max": 5,
  "blacklist": [-1001234567890]
}
```

| Kunci | Arti |
|---|---|
| `api_id` / `api_hash` | Kredensial dari my.telegram.org |
| `delay_min` / `delay_max` | Rentang jeda acak antar grup, dalam detik |
| `blacklist` | Daftar ID grup yang dilewati saat promosi |

---

## 🗂 Struktur Proyek

```
IvasBot/
├── userbot.py      # Semua logika bot: perintah, worker promosi, helper
├── config.json     # Konfigurasi & daftar hitam (JANGAN di-commit)
└── README.md       # Dokumen ini
```

Isi `userbot.py` dibagi per bagian dengan pemisah komentar:

| Bagian | Isinya |
|---|---|
| Konfigurasi | Baca & simpan `config.json` |
| Helper tampilan | `susun_panel()`, `kutip()`, `hapus_setelah()` |
| Helper durasi | `baca_durasi()`, `format_durasi()` |
| Daftar hitam | `cari_id_target()`, `sedang_diblacklist()` |
| Pengiriman promosi | `kirim_promosi_ke()` — logika forward vs salin |
| Pendaftaran perintah | Semua handler `.promosi`, `.addbl`, dst |
| Worker | `jalankan_promosi()` — job background |

---

## 🛡 Tips Biar Akun Aman

1. **Jangan pasang jeda terlalu pendek.** `3–5 detik` masih aman, di bawah itu rawan limit.
2. **Jangan promosi tiap 5 menit.** Interval satu jam ke atas jauh lebih wajar.
3. **Blacklist grup penting** (grup kerja, keluarga) sebelum promosi pertama.
4. Kalau kena `FloodWait`, bot otomatis menunggu — biarkan saja, jangan restart paksa.
5. Pakai akun cadangan kalau kamu promosi dalam volume besar.

---

## ⚠️ Disclaimer

Alat ini dibuat untuk keperluan pribadi dan edukasi. Spam berlebihan bisa
berujung **pembatasan atau banned permanen** akun Telegram kamu. Risiko
pemakaian sepenuhnya ada di tangan pengguna.

---

<div align="center">

Dibuat dengan ☕ oleh [DikZzXD](https://github.com/DikZzXD)

</div>
