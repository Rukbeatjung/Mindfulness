"""
Mindful — แอปฝึกสติและนั่งสมาธิ (Single-file edition)
=====================================================
วิธีรัน:
    pip install flask
    python app.py
แล้วเปิดเบราว์เซอร์ที่ http://127.0.0.1:5000

ไฟล์นี้รวมทุกอย่างไว้ในไฟล์เดียว: Flask routes, SQLite schema, และหน้าเว็บ
(HTML/CSS/JS ฝังอยู่ในตัวแปร Python string) — ไม่มีโฟลเดอร์ templates/static
เพราะ Tailwind โหลดผ่าน CDN และไม่มีไฟล์เสียง/รูปในเครื่อง

หมายเหตุ: audio_url ตัวอย่างในคลังธรรมะเป็น placeholder เท่านั้น
ให้แก้เป็นลิงก์ไฟล์เสียงจริงของคุณก่อนใช้งานจริง
"""

import json
import sqlite3
from datetime import date, datetime

from flask import Flask, g, jsonify, request

app = Flask(__name__)
DATABASE = "mindfulness.db"
USER_ID = 1  # แอปนี้ออกแบบเป็น single-user เพื่อความเรียบง่าย (ไม่มีระบบ login)


# ============================================================
# 1) DATABASE LAYER
# ============================================================

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    cur = db.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS session_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            sound_enabled INTEGER NOT NULL DEFAULT 1,
            completed_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS mindfulness_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, log_date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS library_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('text','audio')),
            title TEXT NOT NULL,
            category TEXT,
            content_text TEXT,
            audio_url TEXT,
            duration_seconds INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            notification_enabled INTEGER NOT NULL DEFAULT 1,
            start_time TEXT NOT NULL DEFAULT '08:00',
            end_time TEXT NOT NULL DEFAULT '21:00',
            frequency_hours INTEGER NOT NULL DEFAULT 3,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
    )

    if not cur.execute("SELECT id FROM users WHERE id=?", (USER_ID,)).fetchone():
        cur.execute(
            "INSERT INTO users (id, display_name, created_at) VALUES (?,?,?)",
            (USER_ID, "ผู้ฝึกสติ", datetime.now().isoformat()),
        )

    if not cur.execute("SELECT id FROM user_settings WHERE user_id=?", (USER_ID,)).fetchone():
        cur.execute(
            """INSERT INTO user_settings
               (user_id, notification_enabled, start_time, end_time, frequency_hours, updated_at)
               VALUES (?,?,?,?,?,?)""",
            (USER_ID, 1, "08:00", "21:00", 3, datetime.now().isoformat()),
        )

    if cur.execute("SELECT COUNT(*) c FROM library_content").fetchone()["c"] == 0:
        now = datetime.now().isoformat()
        samples = [
            ("text", "บทแผ่เมตตาให้ตนเอง", "บทสวดมนต์แปล",
             "ขอให้ข้าพเจ้าจงเป็นผู้มีความสุข\n"
             "ขอให้ปราศจากความทุกข์กายทุกข์ใจ\n"
             "ขอให้ปลอดภัยจากอันตรายทั้งปวง\n"
             "ขอให้มีชีวิตอยู่อย่างสงบสุข", None, None),
            ("text", "อานาปานสติเบื้องต้น", "ธรรมะ",
             "เพียงแค่รู้ลมหายใจเข้า และรู้ลมหายใจออก\n"
             "ไม่ต้องบังคับ ไม่ต้องเปลี่ยนแปลงมัน\n"
             "แค่เฝ้าดูมันไปตามธรรมชาติ นี่คือจุดเริ่มต้นของสติ", None, None),
            ("text", "บทสวดก่อนนอน (แปล)", "บทสวดมนต์แปล",
             "ขอตั้งจิตอุทิศบุญกุศลนี้แผ่ไป\n"
             "ถึงสรรพสัตว์ทั้งหลาย\n"
             "ขอให้พ้นจากทุกข์ภัยทั่วกัน", None, None),
            ("audio", "เสียงระฆังสำหรับนั่งสมาธิ", "เสียงประกอบ",
             None, "https://example.com/audio/bell.mp3", 600),
        ]
        for t, title, cat, txt, audio, dur in samples:
            cur.execute(
                """INSERT INTO library_content
                   (type,title,category,content_text,audio_url,duration_seconds,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (t, title, cat, txt, audio, dur, now),
            )

    db.commit()
    db.close()


init_db()


# ============================================================
# 2) PAGE LAYOUT (string templating — ไม่ใช้ Jinja เพื่อความง่าย
#    และเพื่อไม่ให้ { } ใน JavaScript ชนกับ syntax ของ template engine)
# ============================================================

BASE_HTML = """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{TITLE}} · Mindful</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+Thai:wght@300;400;600&family=Sarabun:wght@300;400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          paper: '#F6F2E9',
          ink: '#262E27',
          moss: { 50:'#EEF1E9', 100:'#DEE4D4', 200:'#C3CDB4', 400:'#7C9574', 700:'#3F5D48', 800:'#2C4234' },
          ochre: '#B08B57'
        },
        fontFamily: {
          serif: ['"Noto Serif Thai"', 'serif'],
          sans: ['"Sarabun"', 'sans-serif']
        }
      }
    }
  }
</script>
<style>
  body { -webkit-tap-highlight-color: transparent; }
  @keyframes breathe {
    0%, 100% { transform: scale(1); opacity: .7; }
    50% { transform: scale(1.2); opacity: 1; }
  }
  .breathe { animation: breathe 4.2s ease-in-out infinite; }
</style>
</head>
<body class="bg-paper text-ink font-sans antialiased min-h-screen pb-24">
  <header class="pt-7 pb-3 text-center">
    <p class="font-serif text-lg text-moss-800">Mindful</p>
  </header>
  <main class="max-w-md mx-auto px-5">
{{BODY}}
  </main>
  <nav class="fixed bottom-0 left-0 right-0 bg-paper/95 backdrop-blur border-t border-moss-100 flex justify-around py-2">
{{NAV}}
  </nav>
</body>
</html>"""

NAV_ITEMS = [
    ("home", "/", "🏠", "หน้าหลัก"),
    ("timer", "/timer", "⏱️", "ตั้งเวลา"),
    ("tracker", "/tracker", "🧘", "นับสติ"),
    ("library", "/library", "📖", "คลังธรรมะ"),
    ("settings", "/settings", "⚙️", "ตั้งค่า"),
]


def render_page(active, title, body_html):
    nav_html = ""
    for key, href, icon, label in NAV_ITEMS:
        color = "text-moss-800" if key == active else "text-ink/40"
        nav_html += (
            f'<a href="{href}" class="flex flex-col items-center gap-0.5 px-3 py-1 {color}">'
            f'<span class="text-lg leading-none">{icon}</span>'
            f'<span class="text-[11px] font-medium">{label}</span></a>'
        )
    html = BASE_HTML.replace("{{TITLE}}", title)
    html = html.replace("{{NAV}}", nav_html)
    html = html.replace("{{BODY}}", body_html)
    return html


# ============================================================
# 3) PAGES
# ============================================================

@app.route("/")
def page_home():
    db = get_db()
    today = date.today().isoformat()
    sess = db.execute(
        "SELECT COALESCE(SUM(duration_minutes),0) m, COUNT(*) c FROM session_logs "
        "WHERE user_id=? AND date(completed_at)=?", (USER_ID, today),
    ).fetchone()
    mind = db.execute(
        "SELECT count FROM mindfulness_logs WHERE user_id=? AND log_date=?", (USER_ID, today),
    ).fetchone()
    mindful_count = mind["count"] if mind else 0

    body = f"""
    <section class="mt-3 mb-8 text-center">
      <h2 class="font-serif text-2xl font-light text-ink">สวัสดี</h2>
      <p class="text-ink/50 text-sm mt-1">วันนี้ให้เวลากับลมหายใจของคุณสักครู่ไหม</p>
    </section>

    <section class="grid grid-cols-2 gap-3 mb-8">
      <div class="border border-moss-100 rounded-2xl p-4 text-center">
        <p class="text-3xl font-light text-moss-800">{sess['m']}</p>
        <p class="text-xs text-ink/40 mt-1">นาทีที่นั่งสมาธิวันนี้</p>
      </div>
      <div class="border border-moss-100 rounded-2xl p-4 text-center">
        <p class="text-3xl font-light text-moss-800">{mindful_count}</p>
        <p class="text-xs text-ink/40 mt-1">ครั้งที่ดึงสติวันนี้</p>
      </div>
    </section>

    <a href="/timer" class="block bg-moss-700 text-white text-center rounded-full py-4 mb-3">
      เริ่มนั่งสมาธิ
    </a>
    <a href="/tracker" class="block border border-moss-200 text-moss-800 text-center rounded-full py-4">
      บันทึกการดึงสติ
    </a>
    """
    return render_page("home", "หน้าหลัก", body)


TIMER_BODY = """
<section class="mt-3 mb-6 text-center">
  <h2 class="font-serif text-xl font-light text-ink">ตั้งเวลานั่งสมาธิ</h2>
  <p class="text-ink/50 text-sm mt-1">เลือกระยะเวลาที่พอดีกับวันนี้ของคุณ</p>
</section>

<div id="setupPanel">
  <div class="grid grid-cols-4 gap-2 mb-4">
    <button class="preset-btn border border-moss-200 rounded-xl py-3 text-moss-800 text-sm" data-min="5">5 นาที</button>
    <button class="preset-btn border border-moss-200 rounded-xl py-3 text-moss-800 text-sm" data-min="10">10 นาที</button>
    <button class="preset-btn border border-moss-200 rounded-xl py-3 text-moss-800 text-sm" data-min="15">15 นาที</button>
    <button class="preset-btn border border-moss-200 rounded-xl py-3 text-moss-800 text-sm" data-min="20">20 นาที</button>
  </div>

  <div class="flex items-center gap-2 mb-6">
    <input id="customMin" type="number" min="1" max="180" placeholder="กำหนดเอง (นาที)"
      class="flex-1 border border-moss-200 rounded-xl px-4 py-3 text-sm bg-transparent focus:outline-none focus:ring-2 focus:ring-moss-200">
    <button id="useCustomBtn" class="border border-moss-200 text-moss-800 rounded-xl px-4 py-3 text-sm">ใช้</button>
  </div>

  <div class="flex items-center justify-between border border-moss-100 rounded-2xl px-4 py-3 mb-8">
    <span class="text-sm">เสียงเตือนเมื่อหมดเวลา</span>
    <button id="soundToggle" class="w-11 h-6 rounded-full bg-moss-700 relative transition-colors">
      <span id="soundKnob" class="absolute top-1 w-4 h-4 bg-white rounded-full transition-all" style="right:4px;"></span>
    </button>
  </div>

  <div class="text-center">
    <p id="selectedMinutes" class="font-serif text-4xl font-light text-moss-800 mb-6">10 <span class="text-lg text-ink/40">นาที</span></p>
    <button id="startBtn" class="w-full bg-moss-700 text-white rounded-full py-4 text-base">เริ่มนั่งสมาธิ</button>
  </div>
</div>

<!-- หน้าจอระหว่างนั่งสมาธิ: นิ่ง สงบ ไม่มีสีสันรบกวน -->
<div id="focusOverlay" class="hidden fixed inset-0 z-50 flex flex-col items-center justify-center text-center px-6"
     style="background: linear-gradient(to bottom, #141C17, #0A0D0B);">
  <div class="breathe w-40 h-40 rounded-full mb-10 flex items-center justify-center" style="background: radial-gradient(circle, rgba(176,139,87,0.18), rgba(176,139,87,0) 70%); border: 1px solid rgba(176,139,87,0.25);">
    <div class="w-24 h-24 rounded-full" style="border: 1px solid rgba(176,139,87,0.2);"></div>
  </div>
  <p id="countdownText" class="text-white text-5xl font-extralight tracking-widest mb-3">10:00</p>
  <p class="text-sm mb-14" style="color: rgba(222,228,212,0.55);">หายใจเข้า... หายใจออก...</p>
  <button id="stopBtn" class="text-sm rounded-full px-6 py-2" style="color: rgba(222,228,212,0.55); border: 1px solid rgba(222,228,212,0.2);">
    หยุดก่อนเวลา
  </button>
</div>

<div id="completePanel" class="hidden text-center mt-14">
  <p class="text-4xl mb-4">🙏</p>
  <p class="font-serif text-lg text-ink mb-1">เสร็จสิ้นการฝึกสติ</p>
  <p class="text-ink/50 text-sm mb-8">ขอบคุณที่ให้เวลากับตัวเอง</p>
  <button onclick="location.reload()" class="bg-moss-700 text-white rounded-full px-8 py-3">กลับไปตั้งเวลาใหม่</button>
</div>

<script>
let selectedMinutes = 10;
let soundEnabled = true;
let remainingSeconds = 0;
let timerInterval = null;

const setupPanel = document.getElementById('setupPanel');
const focusOverlay = document.getElementById('focusOverlay');
const completePanel = document.getElementById('completePanel');
const countdownText = document.getElementById('countdownText');
const selectedMinutesEl = document.getElementById('selectedMinutes');
const soundToggle = document.getElementById('soundToggle');
const soundKnob = document.getElementById('soundKnob');

function setSelected(min) {
  selectedMinutes = min;
  selectedMinutesEl.innerHTML = min + ' <span class="text-lg text-ink/40">นาที</span>';
}

document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => setSelected(parseInt(btn.dataset.min, 10)));
});

document.getElementById('useCustomBtn').addEventListener('click', () => {
  const val = parseInt(document.getElementById('customMin').value, 10);
  if (val > 0) setSelected(val);
});

soundToggle.addEventListener('click', () => {
  soundEnabled = !soundEnabled;
  soundToggle.style.backgroundColor = soundEnabled ? '' : '#C3CDB4';
  soundKnob.style.right = soundEnabled ? '4px' : 'auto';
  soundKnob.style.left = soundEnabled ? 'auto' : '4px';
});

function formatTime(sec) {
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = (sec % 60).toString().padStart(2, '0');
  return m + ':' + s;
}

function playBell() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 528;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 3);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 3);
  } catch (e) { /* บางเบราว์เซอร์อาจไม่รองรับ ข้ามไปเงียบๆ */ }
}

function startTimer() {
  remainingSeconds = selectedMinutes * 60;
  setupPanel.classList.add('hidden');
  focusOverlay.classList.remove('hidden');
  countdownText.textContent = formatTime(remainingSeconds);
  timerInterval = setInterval(() => {
    remainingSeconds -= 1;
    countdownText.textContent = formatTime(remainingSeconds);
    if (remainingSeconds <= 0) finishTimer(true);
  }, 1000);
}

function finishTimer(completed) {
  clearInterval(timerInterval);
  focusOverlay.classList.add('hidden');
  if (completed && soundEnabled) playBell();
  completePanel.classList.remove('hidden');
  fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ duration_minutes: selectedMinutes, sound_enabled: soundEnabled, completed: completed })
  }).catch(() => {});
}

document.getElementById('startBtn').addEventListener('click', startTimer);
document.getElementById('stopBtn').addEventListener('click', () => finishTimer(false));
</script>
"""


@app.route("/timer")
def page_timer():
    return render_page("timer", "ตั้งเวลา", TIMER_BODY)


@app.route("/tracker")
def page_tracker():
    db = get_db()
    today = date.today().isoformat()
    row = db.execute(
        "SELECT count FROM mindfulness_logs WHERE user_id=? AND log_date=?", (USER_ID, today),
    ).fetchone()
    today_count = row["count"] if row else 0

    body = """
    <section class="mt-3 mb-10 text-center">
      <h2 class="font-serif text-xl font-light text-ink">นับสติวันนี้</h2>
      <p class="text-ink/50 text-sm mt-1">แตะทุกครั้งที่คุณรู้ตัวว่าเผลอ แล้วดึงสติกลับมา</p>
    </section>

    <div class="text-center mb-10">
      <p id="countDisplay" class="font-serif text-7xl font-light text-moss-800">{{COUNT}}</p>
      <p class="text-ink/40 text-sm mt-1">ครั้ง</p>
    </div>

    <button id="mindfulBtn" class="w-44 h-44 mx-auto flex items-center justify-center rounded-full
      bg-moss-700 text-white text-base leading-tight active:scale-95 transition-transform">
      🧘‍♀️<br>ดึงสติ
    </button>

    <p class="text-center text-xs text-ink/35 mt-10">ไม่มีจำนวนที่ "ถูกต้อง" แค่สังเกตอย่างอ่อนโยน</p>

    <script>
      document.getElementById('mindfulBtn').addEventListener('click', () => {
        fetch('/api/mindfulness/increment', { method: 'POST' })
          .then(r => r.json())
          .then(data => { document.getElementById('countDisplay').textContent = data.count; });
      });
    </script>
    """.replace("{{COUNT}}", str(today_count))
    return render_page("tracker", "นับสติ", body)


@app.route("/library")
def page_library():
    db = get_db()
    rows = db.execute("SELECT * FROM library_content ORDER BY type, id").fetchall()
    items = [dict(r) for r in rows]

    rows_html = ""
    for item in items:
        icon = "📖" if item["type"] == "text" else "🎧"
        rows_html += f"""
        <div class="lib-row border-b border-moss-100 py-4 cursor-pointer" data-id="{item['id']}">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium text-ink">{icon} {item['title']}</p>
              <p class="text-xs text-ink/40 mt-0.5">{item['category'] or ''}</p>
            </div>
            <span class="text-moss-400 text-sm">›</span>
          </div>
          <div class="lib-content hidden mt-3 text-sm text-ink/70 whitespace-pre-line"></div>
        </div>
        """

    body = """
    <section class="mt-3 mb-4 text-center">
      <h2 class="font-serif text-xl font-light text-ink">คลังธรรมะ</h2>
      <p class="text-ink/50 text-sm mt-1">บทอ่านและเสียงเพื่อการฝึกสติ</p>
    </section>
    <div>{{ROWS}}</div>
    <script>
      const LIBRARY_DATA = {{DATA_JSON}};
      document.querySelectorAll('.lib-row').forEach(row => {
        row.addEventListener('click', () => {
          const id = parseInt(row.dataset.id, 10);
          const item = LIBRARY_DATA.find(x => x.id === id);
          const box = row.querySelector('.lib-content');
          const wasHidden = box.classList.contains('hidden');
          document.querySelectorAll('.lib-content').forEach(b => b.classList.add('hidden'));
          if (wasHidden) {
            if (item.type === 'text') {
              box.textContent = item.content_text;
            } else {
              box.innerHTML = '<audio controls class="w-full" src="' + item.audio_url + '"></audio>';
            }
            box.classList.remove('hidden');
          }
        });
      });
    </script>
    """.replace("{{ROWS}}", rows_html).replace("{{DATA_JSON}}", json.dumps(items, ensure_ascii=False))
    return render_page("library", "คลังธรรมะ", body)


@app.route("/settings")
def page_settings():
    db = get_db()
    s = db.execute("SELECT * FROM user_settings WHERE user_id=?", (USER_ID,)).fetchone()
    checked = "checked" if s["notification_enabled"] else ""

    body = """
    <section class="mt-3 mb-6 text-center">
      <h2 class="font-serif text-xl font-light text-ink">ตั้งค่าการแจ้งเตือน</h2>
      <p class="text-ink/50 text-sm mt-1">กำหนดช่วงเวลาแบบยืดหยุ่น ไม่ถี่จนรบกวน</p>
    </section>

    <div class="border border-moss-100 rounded-2xl p-5 space-y-5">
      <div class="flex items-center justify-between">
        <span class="text-sm">เปิดการแจ้งเตือน</span>
        <input type="checkbox" id="notifEnabled" {{CHECKED}} class="w-5 h-5 accent-[#3F5D48]">
      </div>
      <div>
        <label class="text-xs text-ink/40 block mb-1">เริ่มแจ้งเตือนตั้งแต่</label>
        <input type="time" id="startTime" value="{{START}}" class="w-full border border-moss-200 rounded-xl px-3 py-2 text-sm bg-transparent">
      </div>
      <div>
        <label class="text-xs text-ink/40 block mb-1">แจ้งเตือนถึงเวลา</label>
        <input type="time" id="endTime" value="{{END}}" class="w-full border border-moss-200 rounded-xl px-3 py-2 text-sm bg-transparent">
      </div>
      <div>
        <label class="text-xs text-ink/40 block mb-1">ความถี่ในการแจ้งเตือน</label>
        <select id="frequency" class="w-full border border-moss-200 rounded-xl px-3 py-2 text-sm bg-transparent">
          <option value="2">ทุก 2 ชั่วโมง</option>
          <option value="3">ทุก 3 ชั่วโมง</option>
          <option value="4">ทุก 4 ชั่วโมง</option>
          <option value="6">ทุก 6 ชั่วโมง (แนะนำ)</option>
          <option value="8">วันละ 1-2 ครั้ง</option>
        </select>
      </div>
    </div>

    <button id="saveBtn" class="w-full bg-moss-700 text-white rounded-full py-4 mt-6">บันทึกการตั้งค่า</button>
    <p id="savedMsg" class="hidden text-center text-moss-700 text-sm mt-3">บันทึกเรียบร้อย</p>

    <script>
      document.getElementById('frequency').value = "{{FREQ}}";
      document.getElementById('saveBtn').addEventListener('click', () => {
        const payload = {
          notification_enabled: document.getElementById('notifEnabled').checked,
          start_time: document.getElementById('startTime').value,
          end_time: document.getElementById('endTime').value,
          frequency_hours: parseInt(document.getElementById('frequency').value, 10)
        };
        fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).then(() => {
          const msg = document.getElementById('savedMsg');
          msg.classList.remove('hidden');
          setTimeout(() => msg.classList.add('hidden'), 2000);
        });
      });
    </script>
    """
    body = (
        body.replace("{{CHECKED}}", checked)
        .replace("{{START}}", s["start_time"])
        .replace("{{END}}", s["end_time"])
        .replace("{{FREQ}}", str(s["frequency_hours"]))
    )
    return render_page("settings", "ตั้งค่า", body)


# ============================================================
# 4) API ENDPOINTS (เขียนข้อมูลเท่านั้น — การอ่านฝังไว้ตอน render หน้าแล้ว)
# ============================================================

@app.route("/api/sessions", methods=["POST"])
def api_create_session():
    data = request.get_json(force=True, silent=True) or {}
    duration = int(data.get("duration_minutes", 0))
    sound_enabled = 1 if data.get("sound_enabled") else 0
    db = get_db()
    db.execute(
        "INSERT INTO session_logs (user_id, duration_minutes, sound_enabled, completed_at) VALUES (?,?,?,?)",
        (USER_ID, duration, sound_enabled, datetime.now().isoformat()),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/mindfulness/increment", methods=["POST"])
def api_increment_mindfulness():
    db = get_db()
    today = date.today().isoformat()
    row = db.execute(
        "SELECT id FROM mindfulness_logs WHERE user_id=? AND log_date=?", (USER_ID, today),
    ).fetchone()
    if row:
        db.execute("UPDATE mindfulness_logs SET count = count + 1 WHERE id=?", (row["id"],))
    else:
        db.execute(
            "INSERT INTO mindfulness_logs (user_id, log_date, count) VALUES (?,?,1)", (USER_ID, today),
        )
    db.commit()
    new_count = db.execute(
        "SELECT count FROM mindfulness_logs WHERE user_id=? AND log_date=?", (USER_ID, today),
    ).fetchone()["count"]
    return jsonify({"count": new_count})


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.get_json(force=True, silent=True) or {}
    db = get_db()
    db.execute(
        """UPDATE user_settings SET notification_enabled=?, start_time=?, end_time=?,
           frequency_hours=?, updated_at=? WHERE user_id=?""",
        (
            1 if data.get("notification_enabled") else 0,
            data.get("start_time", "08:00"),
            data.get("end_time", "21:00"),
            int(data.get("frequency_hours", 3)),
            datetime.now().isoformat(),
            USER_ID,
        ),
    )
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
