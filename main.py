import sys
import os
import customtkinter as ctk

# --- MÀN HÌNH SPLASH (INTRO & LOADING) CHẠY ĐẦU TIÊN ---
app = ctk.CTk()
app.withdraw() # Ẩn cửa sổ chính trong lúc load

splash = ctk.CTkToplevel(app)
splash.overrideredirect(True)
splash_w, splash_h = 500, 300
sw, sh = splash.winfo_screenwidth(), splash.winfo_screenheight()
splash.geometry(f'{splash_w}x{splash_h}+{int((sw/2)-(splash_w/2))}+{int((sh/2)-(splash_h/2))}')
splash.configure(fg_color='#0F1014')
ctk.CTkLabel(splash, text="V O C A B", font=("Segoe UI", 46, "bold"), text_color='#4F46E5').pack(pady=(70, 5))
ctk.CTkLabel(splash, text="Master Your English", font=("Segoe UI", 16), text_color='#94A3B8').pack(pady=(0, 40))
lbl_status = ctk.CTkLabel(splash, text="Đang khởi động hệ thống...", font=("Segoe UI", 12, "italic"), text_color='white')
lbl_status.pack()
splash.update()
# -------------------------------------------------------

from tkinter import messagebox
import sqlite3
from datetime import datetime, timedelta
import requests
from io import BytesIO
from PIL import Image
import threading
import pygame
from gtts import gTTS
from deep_translator import GoogleTranslator
import random
import hashlib
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import time
import shutil
import webbrowser

# --- THÊM BỘ ĐỆM (CACHE) ENGINE TTS ĐỂ KHÔNG PHẢI KHỞI TẠO LẠI ---
tts_local = threading.local()
def get_tts_engine():
    if not hasattr(tts_local, "engine"):
        if sys.platform == "win32":
            import pythoncom
            pythoncom.CoInitialize()
        import pyttsx3
        tts_local.engine = pyttsx3.init()
    return tts_local.engine
# -----------------------------------------------------------------

lbl_status.configure(text="Đang thiết lập môi trường...")
splash.update()
# ================== CẤU HÌNH & KHỞI TẠO ==================
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# ================== CẤU HÌNH ĐƯỜNG DẪN AN TOÀN ==================
# 1. Tìm thư mục AppData của Windows (Nơi an toàn nhất để lưu dữ liệu)
if sys.platform == "win32":
    APP_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'VocabMasterPremium')
else:
    APP_DATA_DIR = os.path.join(os.path.expanduser('~'), '.vocabmasterpremium')

# 2. Bắt buộc tạo thư mục trước khi làm bất cứ việc gì khác
try:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
except Exception as e:
    import tkinter.messagebox as mb
    mb.showerror("Lỗi hệ thống", f"Không thể tạo thư mục dữ liệu:\n{e}")

# 3. Gán đường dẫn cố định
BASE_DIR = APP_DATA_DIR
DB_PATH = os.path.join(BASE_DIR, "vocab.db")
CACHE_DIR = os.path.join(BASE_DIR, "image_cache")
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
LOFI_DIR = os.path.join(BASE_DIR, "lofi_music")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(LOFI_DIR, exist_ok=True)

# 4. Tự động Copy dữ liệu cũ (Xử lý mượt cả khi chạy file .py và .exe)
if getattr(sys, 'frozen', False):
    LOCAL_DIR = os.path.dirname(sys.executable) # Thư mục chứa file .exe
else:
    LOCAL_DIR = os.path.dirname(os.path.abspath(__file__)) # Thư mục chứa file .py

LOCAL_DB_PATH = os.path.join(LOCAL_DIR, "vocab.db")

# Nếu có DB cũ mà DB mới chưa có thì copy sang
if os.path.exists(LOCAL_DB_PATH) and not os.path.exists(DB_PATH):
    try:
        shutil.copy2(LOCAL_DB_PATH, DB_PATH)
    except:
        pass
# ================================================================

lbl_status.configure(text="Đang nạp dữ liệu & thư viện Audio...")
splash.update()
pygame.mixer.init()
pygame.mixer.set_num_channels(8) # Khởi tạo 8 luồng âm thanh song song
VOICE_CHANNEL = pygame.mixer.Channel(1) # Dành riêng luồng số 1 cho giọng đọc từ vựng
translator = GoogleTranslator(source='en', target='vi')

executor = ThreadPoolExecutor(max_workers=15)
DB_LOCK = threading.Lock()

BG_MAIN = ("#F8FAFC", "#0F1014")
BG_SIDEBAR = ("#FFFFFF", "#18191E")
BG_CARD = ("#FFFFFF", "#212229")
BORDER_COLOR = ("#E2E8F0", "#2E303D")
HOVER_COLOR_TRANSPARENT = ("#F1F5F9", "#2A2C36")
HOVER_COLOR_CARD = ("#F8FAFC", "#2D2E3A")
COLOR_ACCENT = ("#4F46E5", "#6366F1")
COLOR_ACCENT_HOVER = ("#4338CA", "#4F46E5")
COLOR_SUCCESS = ("#10B981", "#22C55E")
COLOR_DANGER = ("#EF4444", "#F87171")
COLOR_WARNING = ("#F59E0B", "#FBBF24")
TEXT_SUB = ("#64748B", "#94A3B8")
FONT_TITLE = ("Segoe UI", 46, "bold")
FONT_VN = ("Segoe UI", 24, "bold")
FONT_BODY = ("Segoe UI", 15)
FONT_ITALIC = ("Segoe UI", 16, "italic")

POS_MAP = {
    "noun": "Danh từ", "verb": "Động từ", "adjective": "Tính từ",
    "adverb": "Trạng từ", "pronoun": "Đại từ", "preposition": "Giới từ",
    "conjunction": "Liên từ", "interjection": "Thán từ"
}

# ================== RAM-FIRST DATA MANAGER (SIÊU TỐC) ==================
class DataManager:
    def __init__(self):
        self.vocab = {}
        self.phrase = {}
        self.tracker = {} # {date: set(words)}
        self._init_db()
        self._load_to_ram()

    def _init_db(self):
        with DB_LOCK:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA journal_mode=WAL;")
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS vocab
                         (word TEXT PRIMARY KEY, sentence TEXT, pos TEXT, vn_meaning TEXT,
                          last_studied TEXT, study_count INTEGER DEFAULT 0, custom_sentence TEXT, item_type TEXT DEFAULT 'vocab')''')
            try:
                c.execute("ALTER TABLE vocab ADD COLUMN is_mastered INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            c.execute('''CREATE TABLE IF NOT EXISTS phrase
                         (word TEXT PRIMARY KEY, sentence TEXT, pos TEXT, vn_meaning TEXT,
                          last_studied TEXT, study_count INTEGER DEFAULT 0, custom_sentence TEXT, item_type TEXT DEFAULT 'phrase')''')
            try:
                c.execute("ALTER TABLE phrase ADD COLUMN is_mastered INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            c.execute('''CREATE TABLE IF NOT EXISTS daily_tracker
                         (date TEXT, word TEXT, PRIMARY KEY (date, word))''')
                         
            c.execute('''CREATE TABLE IF NOT EXISTS settings
                         (key TEXT PRIMARY KEY, value TEXT)''')
            conn.commit()
            conn.close()

    def _load_to_ram(self):
        with DB_LOCK:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            for row in c.execute("SELECT word, sentence, pos, vn_meaning, last_studied, study_count, custom_sentence, item_type, is_mastered FROM vocab"):
                self.vocab[row[0]] = {'sentence': row[1], 'pos': row[2], 'vn_meaning': row[3], 'last_studied': row[4], 'study_count': row[5], 'custom_sentence': row[6], 'item_type': row[7], 'is_mastered': row[8]}
            for row in c.execute("SELECT word, sentence, pos, vn_meaning, last_studied, study_count, custom_sentence, item_type, is_mastered FROM phrase"):
                self.phrase[row[0]] = {'sentence': row[1], 'pos': row[2], 'vn_meaning': row[3], 'last_studied': row[4], 'study_count': row[5], 'custom_sentence': row[6], 'item_type': row[7], 'is_mastered': row[8]}
            for row in c.execute("SELECT date, word FROM daily_tracker"):
                if row[0] not in self.tracker: self.tracker[row[0]] = set()
                self.tracker[row[0]].add(row[1])
            conn.close()

    def get_setting(self, key, default=""):
        with DB_LOCK:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            res = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            conn.close()
            return res[0] if res else default
            
    def set_setting(self, key, value):
        with DB_LOCK:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
            conn.commit()
            conn.close()

    def get_all(self, item_type):
        d = self.vocab if item_type == 'vocab' else self.phrase
        return [(w, v['vn_meaning'], v['study_count'], v['last_studied'], v.get('is_mastered', 0)) for w, v in d.items()]

    def get_detail(self, word, item_type):
        d = self.vocab if item_type == 'vocab' else self.phrase
        return d.get(word)

    def update_progress(self, word, item_type):
        """Xử lý RAM cực nhanh: Tăng số lần học 1 lần/ngày. Cập nhật thời gian thực"""
        d = self.vocab if item_type == 'vocab' else self.phrase
        if word not in d: return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        if today not in self.tracker: self.tracker[today] = set()

        increased = False
        if word not in self.tracker[today]:
            d[word]['study_count'] += 1
            self.tracker[today].add(word)
            increased = True
            
        d[word]['last_studied'] = now_str

        # Chạy đồng bộ Database ngầm (Không làm lag UI)
        def save_to_db():
            with DB_LOCK:
                conn = sqlite3.connect(DB_PATH)
                if increased:
                    conn.execute(f"UPDATE {item_type} SET study_count=?, last_studied=? WHERE word=?", (d[word]['study_count'], now_str, word))
                    conn.execute("INSERT OR IGNORE INTO daily_tracker (date, word) VALUES (?,?)", (today, word))
                else:
                    conn.execute(f"UPDATE {item_type} SET last_studied=? WHERE word=?", (now_str, word))
                conn.commit()
                conn.close()
        executor.submit(save_to_db)
        return increased

    def add_or_update(self, word, item_type, sentence, pos, vn_meaning, custom_sentence="", sync_db=True):
        d = self.vocab if item_type == 'vocab' else self.phrase
        if word in d:
            d[word].update({'sentence': sentence, 'pos': pos, 'vn_meaning': vn_meaning, 'custom_sentence': custom_sentence})
        else:
            d[word] = {'sentence': sentence, 'pos': pos, 'vn_meaning': vn_meaning, 'last_studied': "", 'study_count': 0, 'custom_sentence': custom_sentence, 'item_type': item_type, 'is_mastered': 0}
        
        if sync_db:
            def save_to_db():
                with DB_LOCK:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    if c.execute(f"SELECT 1 FROM {item_type} WHERE word=?", (word,)).fetchone():
                        conn.execute(f"UPDATE {item_type} SET sentence=?, pos=?, vn_meaning=?, custom_sentence=? WHERE word=?", (sentence, pos, vn_meaning, custom_sentence, word))
                    else:
                        conn.execute(f"INSERT INTO {item_type} (word, sentence, pos, vn_meaning, custom_sentence, last_studied, study_count, is_mastered) VALUES (?,?,?,?,?,?,?,?)", (word, sentence, pos, vn_meaning, custom_sentence, "", 0, 0))
                    conn.commit()
                    conn.close()
            executor.submit(save_to_db)

    def update_field(self, word, item_type, field, value):
        d = self.vocab if item_type == 'vocab' else self.phrase
        if word in d:
            d[word][field] = value
            def save_to_db():
                with DB_LOCK:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute(f"UPDATE {item_type} SET {field}=? WHERE word=?", (value, word))
                    conn.commit(); conn.close()
            executor.submit(save_to_db)

    def delete(self, word, item_type):
        d = self.vocab if item_type == 'vocab' else self.phrase
        if word in d:
            del d[word]
            def save_to_db():
                with DB_LOCK:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute(f"DELETE FROM {item_type} WHERE word=?", (word,))
                    conn.commit(); conn.close()
            executor.submit(save_to_db)
    
    def get_user_stats(self):
        # Tính tổng số lần tưới cây (tổng study_count)
        total_reps = sum(v['study_count'] for v in self.vocab.values()) + sum(v['study_count'] for v in self.phrase.values())
        
        # Kiểm tra xem có bỏ bê quá 3 ngày không (cây héo)
        last_date_str = ""
        for collection in (self.vocab.values(), self.phrase.values()):
            for item in collection:
                if item['last_studied'] and item['last_studied'] > last_date_str:
                    last_date_str = item['last_studied']
                    
        is_withered = False
        if last_date_str:
            try:
                last_d = datetime.strptime(last_date_str[:10], "%Y-%m-%d")
                if (datetime.now() - last_d).days >= 3:
                    is_withered = True
            except: pass
            
        # Tính Chuỗi ngày học liên tục (Streak)
        today = datetime.now().date()
        streak = 0
        
        if today.strftime("%Y-%m-%d") in self.tracker:
            streak += 1
            check_date = today - timedelta(days=1)
        elif (today - timedelta(days=1)).strftime("%Y-%m-%d") in self.tracker:
            check_date = today - timedelta(days=1)
        else:
            return total_reps, is_withered, 0
            
        while check_date.strftime("%Y-%m-%d") in self.tracker:
            streak += 1
            check_date -= timedelta(days=1)
            
        return total_reps, is_withered, streak

data_manager = DataManager()

# ================== BỘ NHỚ ĐỆM (CACHE) ==================
class TimedLRUCache:
    def __init__(self, max_size=200, ttl=86400):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                self.cache.move_to_end(key)
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = (value, time.time())
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

image_cache = TimedLRUCache(max_size=150, ttl=3600)
meaning_cache = TimedLRUCache(max_size=500, ttl=86400)

# ================== API & XỬ LÝ ==================
def get_word_info(word):
    cached = meaning_cache.get(word)
    if cached: return cached
    example, pos_str = "Chưa có ví dụ tự động.", "Chưa phân loại"
    try:
        res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=3)
        if res.status_code == 200:
            d = res.json()[0]
            pos_list = list(set([POS_MAP.get(m['partOfSpeech'], m['partOfSpeech']) for m in d['meanings']]))
            pos_str = " | ".join(pos_list)
            for m in d['meanings']:
                for df in m['definitions']:
                    if 'example' in df:
                        example = df['example']
                        break
                if example != "Chưa có ví dụ tự động.": break
    except: pass
    try: vn_meaning = translator.translate(word)
    except: vn_meaning = "Lỗi dịch"
    result = (example, pos_str, vn_meaning)
    meaning_cache.set(word, result)
    return result

def get_phrase_info(phrase):
    cached = meaning_cache.get(phrase)
    if cached: return cached
    try: vn_meaning = translator.translate(phrase)
    except: vn_meaning = "Lỗi dịch"
    result = ("Hãy tự đặt một câu ví dụ cho cụm từ này.", "Cụm từ / Câu", vn_meaning)
    meaning_cache.set(phrase, result)
    return result

AUDIO_LOCK = threading.Lock()
LATEST_AUDIO_REQ = 0
CURRENT_AUDIO_LENGTH = 0
CURRENT_AUDIO_START_TIME = 0

def play_sound_system(text, lang='en', tld=None, is_random=False, on_finish=None):
    global LATEST_AUDIO_REQ, CURRENT_AUDIO_LENGTH, CURRENT_AUDIO_START_TIME
    if not text: return
    
    # Dừng ngay giọng đọc cũ nếu đang phát (KHÔNG làm tắt nhạc nền Lo-fi)
    try:
        VOICE_CHANNEL.stop()
    except Exception:
        pass
        
    req_id = time.time()
    LATEST_AUDIO_REQ = req_id
    
    # Xử lý cài đặt giọng đọc
    if is_random and lang == 'en':
        voice_choice = random.choice(["Nữ (US - Google)", "Nữ (UK - Google)", "Nam (US - Hệ thống)", "Nam (UK - Hệ thống)"])
    else:
        voice_choice = data_manager.get_setting("global_voice", "Nữ (US - Google)")
        
    is_male = "Nam" in voice_choice
    
    # Xử lý ngôn ngữ vùng miền (Accent)
    if tld:
        current_tld = tld
    else:
        if "UK" in voice_choice: current_tld = 'co.uk'
        elif "Úc" in voice_choice: current_tld = 'com.au'
        else: current_tld = 'com'
        
    safe_name = hashlib.md5(f"{text}_{lang}_{current_tld}_{is_male}".encode()).hexdigest()
    initial_audio_path = os.path.join(AUDIO_CACHE_DIR, f"{safe_name}.wav" if is_male else f"{safe_name}.mp3")
    
    def task():
        audio_path = initial_audio_path
        try:
            if not os.path.exists(audio_path):
                with AUDIO_LOCK:
                    if not os.path.exists(audio_path):
                        success = False
                        # Cố gắng sử dụng giọng Nam của hệ thống SAPI5 (pyttsx3)
                        if is_male and lang == 'en':
                            try:
                                engine = get_tts_engine()
                                voices = engine.getProperty('voices')
                                target = next((v.id for v in voices if (current_tld == 'co.uk' and 'uk' in v.name.lower() and ('george' in v.name.lower() or 'male' in v.name.lower())) or (current_tld == 'com' and 'us' in v.name.lower() and ('david' in v.name.lower() or 'male' in v.name.lower()))), None)
                                if not target: target = next((v.id for v in voices if 'david' in v.name.lower() or 'male' in v.name.lower()), None)
                                if target: engine.setProperty('voice', target)
                                engine.save_to_file(text, audio_path)
                                engine.runAndWait()
                                success = True
                            except Exception as e: pass
                            
                        # Fallback về gTTS (Giọng Nữ) nếu thất bại hoặc người dùng chọn Nữ
                        if not success:
                            audio_path = audio_path.replace(".wav", ".mp3")
                            if not os.path.exists(audio_path):
                                tts = gTTS(text=text, lang=lang, tld=current_tld)
                                tts.save(audio_path)
            
            # Chỉ phát ra âm thanh nếu đây vẫn là từ cuối cùng được bấm
            if LATEST_AUDIO_REQ == req_id:
                with AUDIO_LOCK:
                    try:
                        sound = pygame.mixer.Sound(audio_path)
                        CURRENT_AUDIO_LENGTH = sound.get_length()
                        CURRENT_AUDIO_START_TIME = time.time()
                        VOICE_CHANNEL.play(sound)
                    except Exception:
                        CURRENT_AUDIO_LENGTH = 0
                    
                # Chờ âm thanh phát xong (không làm treo giao diện vì chạy ở luồng phụ)
                while VOICE_CHANNEL.get_busy() and LATEST_AUDIO_REQ == req_id:
                    time.sleep(0.1)
                    
                # Nếu không bị ngắt ngang bởi từ khác, tự động chạy hiệu ứng/đọc tiếp
                if on_finish and LATEST_AUDIO_REQ == req_id:
                    try:
                        app.after(400, on_finish) # Nghỉ 0.4s rồi sang câu tiếp theo
                    except: pass
        except Exception:
            pass
            
    executor.submit(task)

def download_and_cache_image(word):
    cache_path = os.path.join(CACHE_DIR, f"{hashlib.md5(word.encode()).hexdigest()}.jpg")
    if os.path.exists(cache_path): return cache_path
    img_data = image_cache.get(word)
    if img_data:
        with open(cache_path, "wb") as f: f.write(img_data)
        return cache_path
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    safe_word = word.replace(' ', '+')
    # Danh sách các nguồn ảnh dự phòng khi nguồn chính bị quá tải (Rate Limit)
    image_sources = [
        f"https://tse2.mm.bing.net/th?q={safe_word}+png+isolated&w=400&h=400&c=7&rs=1",
        f"https://image.pollinations.ai/prompt/a+simple+illustration+of+{safe_word}?width=400&height=400&nologo=true"
    ]
    for url in image_sources:
        try:
            res = requests.get(url, headers=headers, timeout=3)
            # Chỉ lưu nếu server trả về đúng định dạng hình ảnh (chống lưu nhầm mã HTML Captcha)
            if res.status_code == 200 and 'image' in res.headers.get('Content-Type', '').lower():
                with open(cache_path, "wb") as f: f.write(res.content)
                image_cache.set(word, res.content)
                return cache_path
        except: continue
    return None

def safe_set_image(label_widget, new_image=None, new_text=""):
    try:
        if not label_widget.winfo_exists():
            return
        old_img = label_widget.cget("image")
        label_widget.configure(image=new_image, text=new_text)
        if old_img is not None:
            # Giữ reference của ảnh cũ trong 200ms để Tkinter kịp vẽ lại mà không bị lỗi GC
            label_widget.after(200, lambda img=old_img: None)
    except Exception:
        pass

def load_image_async(word, label_widget):
    def update_ui(p_img):
        # Khởi tạo CTkImage ở luồng chính (Main Thread) để tránh lỗi TclError
        ctk_img = ctk.CTkImage(p_img, size=(180, 180))
        safe_set_image(label_widget, new_image=ctk_img, new_text="")

    def task():
        cache_path = download_and_cache_image(word)
        if cache_path and os.path.exists(cache_path):
            try:
                pil_img = Image.open(cache_path)
                pil_img.verify() # Kiểm tra tính hợp lệ của ảnh
                
                pil_img = Image.open(cache_path) # Phải mở lại ảnh sau khi gọi hàm verify
                pil_img.thumbnail((200, 200), Image.Resampling.BILINEAR)
                app.after(0, lambda: update_ui(pil_img))
                return
            except Exception:
                # Nếu ảnh bị lỗi (file hỏng, HTML rác...), xóa cache đi để lần sau tải lại
                try: os.remove(cache_path)
                except: pass
        app.after(0, lambda: safe_set_image(label_widget, new_image=None, new_text="[ Không tải được ảnh ]"))
    executor.submit(task)

# ================== TỐI ƯU VIRTUAL SCROLL LIST ==================
# ================== TỐI ƯU VIRTUAL SCROLL LIST (60FPS RENDER ENGINE) ==================
class VirtualScrollList(ctk.CTkFrame):
    def __init__(self, master, item_type, **kwargs):
        bg_color = kwargs.pop('bg', BG_SIDEBAR[1])
        super().__init__(master, fg_color="transparent", **kwargs)
        self.item_type = item_type
        self.items = []
        self.item_height = 64
        
        self.canvas = ctk.CTkCanvas(self, highlightthickness=0, bg=bg_color, borderwidth=0)
        # Tối ưu: Event-driven render thay vì Polling Loop liên tục
        self.scrollbar = ctk.CTkScrollbar(self, command=self.on_scrollbar)
        self.canvas.configure(yscrollcommand=self.on_canvas_scroll)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.canvas.bind('<Configure>', self.on_resize)
        self.bind_scroll(self.canvas)
        
        self.total_height = 0
        self.sort_criteria = "recent"
        
        self.pool_size = 50 # Tăng lên 50 để chống viền trắng trên màn hình 2K/4K
        self.row_pool = []
        self._redraw_pending = False
        self.init_pool()
        self.load_data()
        
        self.after(50, self.schedule_redraw)

    def on_scrollbar(self, *args):
        self.canvas.yview(*args)
        self.schedule_redraw()

    def on_canvas_scroll(self, *args):
        self.scrollbar.set(*args)
        self.schedule_redraw()

    def bind_scroll(self, widget):
        widget.bind('<MouseWheel>', self.on_mousewheel)
        widget.bind('<Button-4>', self.on_mousewheel)
        widget.bind('<Button-5>', self.on_mousewheel)

    def on_mousewheel(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            delta = event.delta
            units = int(-1*(delta/120)) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            self.canvas.yview_scroll(units, "units")
        self.schedule_redraw()
        return "break" # Tối ưu: Ngăn event cuộn lan truyền ra nền gây giật

    def schedule_redraw(self):
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after(5, self.redraw)

    def init_pool(self):
        for _ in range(self.pool_size):
            row_dict = {'_hover_bg': BG_CARD, '_text_icon': '', '_col_icon': '', '_text_word': '', '_text_vn': '', '_text_count': '', '_last_y': -1000}
            frame = ctk.CTkFrame(self.canvas, fg_color=BG_CARD, corner_radius=12, height=54, border_width=1, border_color=BORDER_COLOR)
            frame.grid_columnconfigure(1, weight=1); frame.grid_columnconfigure(2, weight=1)
            frame.grid_propagate(False)
            
            lbl_icon = ctk.CTkLabel(frame, text="", font=("Segoe UI", 18, "bold"), width=35)
            lbl_icon.grid(row=0, column=0, pady=8, padx=5)
            lbl_word = ctk.CTkLabel(frame, text="", font=("Segoe UI", 15, "bold"), anchor="w")
            lbl_word.grid(row=0, column=1, sticky="we", pady=8, padx=(0, 5))
            lbl_vn = ctk.CTkLabel(frame, text="", font=FONT_BODY, text_color=TEXT_SUB, anchor="w")
            lbl_vn.grid(row=0, column=2, sticky="we", pady=8, padx=5)
            lbl_count = ctk.CTkLabel(frame, text="", font=("Segoe UI", 15, "bold"), text_color=COLOR_SUCCESS[0], width=30)
            lbl_count.grid(row=0, column=3, pady=8, padx=5)
            
            # Tối ưu siêu cấp: Không cần gán lại command khi cuộn, dùng con trỏ tĩnh qua dict
            def on_click(r=row_dict):
                if r['data_idx'] != -1 and r['data_idx'] < len(self.items):
                    w = self.items[r['data_idx']][0]
                    select_item(w, self.item_type)
                    
            btn_view = ctk.CTkButton(frame, text="Xem", width=60, height=32, corner_radius=8, font=("Segoe UI", 13, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=on_click)
            btn_view.grid(row=0, column=4, padx=10, pady=8)
            
            # Tối ưu siêu cấp 2: Chặn spam Hover bằng Cache Ram
            def on_enter(e, f=frame, r=row_dict): 
                if r['_hover_bg'] != HOVER_COLOR_CARD:
                    f.configure(fg_color=HOVER_COLOR_CARD); r['_hover_bg'] = HOVER_COLOR_CARD
            def on_leave(e, f=frame, r=row_dict): 
                if r['_hover_bg'] != BG_CARD:
                    f.configure(fg_color=BG_CARD); r['_hover_bg'] = BG_CARD

            for w in [frame, lbl_icon, lbl_word, lbl_vn, lbl_count]:
                w.bind("<Enter>", on_enter, add="+")
                w.bind("<Leave>", on_leave, add="+")

            for w in [frame, lbl_icon, lbl_word, lbl_vn, lbl_count, btn_view]:
                self.bind_scroll(w)
            
            wid = self.canvas.create_window(0, -1000, anchor='nw', window=frame)
            row_dict.update({
                'frame': frame, 'icon': lbl_icon, 'word': lbl_word, 
                'vn': lbl_vn, 'count': lbl_count, 'btn': btn_view, 
                'id': wid, 'data_idx': -1
            })
            self.row_pool.append(row_dict)

    def load_data(self):
        self.full_items = data_manager.get_all(self.item_type)
        self.items = list(self.full_items)
        self.set_sort(self.sort_criteria) 
    
    def filter_items(self, query):
        query = query.lower().strip()
        if not query:
            self.items = list(self.full_items)
        else:
            self.items = [item for item in self.full_items if query in item[0] or (item[1] and query in item[1].lower())]
        self.set_sort(self.sort_criteria)

    def set_sort(self, criteria):
        self.sort_criteria = criteria
        if criteria == "name": self.items.sort(key=lambda x: x[0])
        elif criteria == "recent": self.items.sort(key=lambda x: x[3] if x[3] else "0000", reverse=True)
        elif criteria == "oldest": self.items.sort(key=lambda x: x[3] if x[3] else "0000")
        elif criteria == "most": self.items.sort(key=lambda x: x[2], reverse=True)
        elif criteria == "least": self.items.sort(key=lambda x: x[2])
        self.update_total_height()
        for row in self.row_pool: row['data_idx'] = -1
        self.schedule_redraw()
        
    def update_total_height(self):
        self.total_height = max(len(self.items) * self.item_height, self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.total_height))
    
    def on_resize(self, event):
        self.update_total_height()
        for row in self.row_pool:
            self.canvas.itemconfig(row['id'], width=event.width)
        self.schedule_redraw()
    
    def redraw(self):
        self._redraw_pending = False
        view_top = self.canvas.canvasy(0)
        first = max(0, int(view_top // self.item_height))
        last = min(len(self.items), first + self.pool_size)
        
        active_pool_indices = set()
        
        # Tối ưu siêu cấp 4: Không gọi thư viện xử lý DateTime trong vòng lặp Render
        three_days_ago_str = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        
        for data_idx in range(first, last):
            pool_idx = data_idx % self.pool_size
            active_pool_indices.add(pool_idx)
            row = self.row_pool[pool_idx]
            
            if row['data_idx'] != data_idx:
                word, vn_meaning, study_count, last_studied, is_mastered = self.items[data_idx]
                is_old = False
                if last_studied and not is_mastered:
                    # So sánh chuỗi ngày (vd "2023-10-01" <= "2023-10-04") nhanh gấp 100 lần parse date
                    if last_studied[:10] <= three_days_ago_str:
                        is_old = True
                
                # Tối ưu siêu cấp 3: Tải lại thuộc tính từ Cache RAM thay vì gọi .cget() của Tkinter
                if is_mastered:
                    if row['_text_icon'] != "✅":
                        row['icon'].configure(text="✅", text_color=COLOR_SUCCESS[0])
                        row['_text_icon'] = "✅"
                        row['_col_icon'] = COLOR_SUCCESS[0]
                else:
                    t_icon = "⚠" if is_old else "✦"
                    t_col = COLOR_DANGER[0] if is_old else COLOR_ACCENT
                    if row['_text_icon'] != t_icon or row['_col_icon'] != t_col:
                        row['icon'].configure(text=t_icon, text_color=t_col)
                        row['_text_icon'] = t_icon
                        row['_col_icon'] = t_col
                    
                t_word = word.capitalize()
                if is_mastered:
                    t_word += " ✅"
                    
                if row['_text_word'] != t_word:
                    row['word'].configure(text=t_word)
                    row['_text_word'] = t_word
                    
                t_vn = vn_meaning.capitalize() if vn_meaning else ""
                if row['_text_vn'] != t_vn:
                    row['vn'].configure(text=t_vn)
                    row['_text_vn'] = t_vn
                    
                t_count = str(study_count)
                if row['_text_count'] != t_count:
                    row['count'].configure(text=t_count)
                    row['_text_count'] = t_count

                row['data_idx'] = data_idx
            
            target_y = data_idx * self.item_height
            if row['_last_y'] != target_y:
                self.canvas.coords(row['id'], 0, target_y)
                row['_last_y'] = target_y
            
        for i in range(self.pool_size):
            if i not in active_pool_indices and self.row_pool[i]['data_idx'] != -1:
                self.canvas.coords(self.row_pool[i]['id'], 0, -1000)
                self.row_pool[i]['data_idx'] = -1
                self.row_pool[i]['_last_y'] = -1000
                
    def refresh_item(self, word):
        detail = data_manager.get_detail(word, self.item_type)
        if not detail: return
        for i, item in enumerate(self.full_items):
            if item[0] == word:
                self.full_items[i] = (word, detail['vn_meaning'], detail['study_count'], detail['last_studied'], detail.get('is_mastered', 0))
                break
        for i, item in enumerate(self.items):
            if item[0] == word:
                self.items[i] = (word, detail['vn_meaning'], detail['study_count'], detail['last_studied'], detail.get('is_mastered', 0))
                pool_idx = i % self.pool_size
                if self.row_pool[pool_idx]['data_idx'] == i:
                    self.row_pool[pool_idx]['data_idx'] = -1 
                self.schedule_redraw()
                break
# ================== GIAO DIỆN CHÍNH ==================
app.title("Vocab Master Premium")
app.geometry("1400x850")
app.grid_columnconfigure(1, weight=1)
app.grid_rowconfigure(1, weight=1)

top_bar = ctk.CTkFrame(app, height=60, corner_radius=0, fg_color=BG_MAIN)
top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")

def open_batch_add(): BatchAddDialog(app)
def open_image_preloader(): ImagePreloaderDialog(app)
def open_reminder_setup(): ReminderSetupDialog(app)

pomodoro_frame_instance = None
def toggle_pomodoro():
    global pomodoro_frame_instance
    if pomodoro_frame_instance is None:
        pomodoro_frame_instance = PomodoroFrame(main_view)
        pomodoro_frame_instance.pack(side="right", fill="y", padx=(0, 20), pady=20)
    else:
        if pomodoro_frame_instance.winfo_ismapped():
            pomodoro_frame_instance.pack_forget()
        else:
            pomodoro_frame_instance.pack(side="right", fill="y", padx=(0, 20), pady=20)

def show_statistics(): StatisticsWindow(app)
def backup_data():
    backup_path = os.path.join(BASE_DIR, f"backup_vocab_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
    messagebox.showinfo("Sao lưu", f"Đã lưu cơ sở dữ liệu tại:\n{backup_path}")

lbl_streak = ctk.CTkLabel(top_bar, text="🔥 0 Ngày", font=("Segoe UI", 16, "bold"), text_color="#FF9500")
lbl_streak.pack(side="left", padx=20)

ctk.CTkButton(top_bar, text="▶ Học Tự Động", font=("Segoe UI", 14, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="white", corner_radius=8, height=36, command=lambda: open_auto_learn()).pack(side="left", padx=5, pady=10)
ctk.CTkButton(top_bar, text="🎮 Game Ôn Tập", font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", text_color="white", corner_radius=8, height=36, command=lambda: open_game_setup()).pack(side="left", padx=5, pady=10)

theme_menu = ctk.CTkOptionMenu(top_bar, values=["System", "Dark", "Light"], command=lambda m: ctk.set_appearance_mode(m), width=110, fg_color=BG_CARD, text_color=("black", "white"), button_color=BG_CARD, button_hover_color=HOVER_COLOR_CARD)
theme_menu.pack(side="right", padx=15, pady=10)
theme_menu.set("Giao diện")

def handle_tool_menu(choice):
    if choice == "📊 Thống kê học tập": show_statistics()
    elif choice == "➕ Thêm hàng loạt": open_batch_add()
    elif choice == "🖼 Tải tất cả ảnh": open_image_preloader()
    elif choice == "🛠 Công cụ dữ liệu": DataToolsDialog(app)
    elif choice == "⏰ Cài đặt nhắc nhở": open_reminder_setup()
    elif choice == "💾 Sao lưu dữ liệu": backup_data()
    tool_menu.set("⚙️ Công cụ")

tool_menu = ctk.CTkOptionMenu(top_bar, values=["📊 Thống kê học tập", "➕ Thêm hàng loạt", "🖼 Tải tất cả ảnh", "🛠 Công cụ dữ liệu", "⏰ Cài đặt nhắc nhở", "💾 Sao lưu dữ liệu"], command=handle_tool_menu, width=130, fg_color=BG_MAIN, text_color=("black", "white"), button_color=BG_MAIN, button_hover_color=HOVER_COLOR_TRANSPARENT, font=("Segoe UI", 14, "bold"))
tool_menu.pack(side="right", padx=5, pady=10)
tool_menu.set("⚙️ Công cụ")

def handle_feature_menu(choice):
    if choice == "🍅 Đồng hồ Pomodoro": toggle_pomodoro()
    elif choice == "📻 Vocab Radio": open_radio_setup()
    feature_menu.set("🌟 Tiện ích")

feature_menu = ctk.CTkOptionMenu(top_bar, values=["🍅 Đồng hồ Pomodoro", "📻 Vocab Radio"], command=handle_feature_menu, width=120, fg_color=BG_MAIN, text_color=("black", "white"), button_color=BG_MAIN, button_hover_color=HOVER_COLOR_TRANSPARENT, font=("Segoe UI", 14, "bold"))
feature_menu.pack(side="right", padx=5, pady=10)
feature_menu.set("🌟 Tiện ích")

sidebar = ctk.CTkFrame(app, width=550, corner_radius=0, fg_color=BG_SIDEBAR, border_width=1, border_color=BORDER_COLOR)
sidebar.grid(row=1, column=0, sticky="nsew")
sidebar.grid_propagate(False)

ctk.CTkLabel(sidebar, text="V O C A B", font=("Segoe UI", 26, "bold"), text_color=COLOR_ACCENT).pack(pady=(30, 5))
ctk.CTkLabel(sidebar, text="Master Your English", font=FONT_BODY, text_color=TEXT_SUB).pack(pady=(0, 15))

add_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
add_frame.pack(fill="x", padx=20, pady=10)
entry_add = ctk.CTkEntry(add_frame, placeholder_text="Nhập nhanh 1 từ/cụm từ...", height=48, font=FONT_BODY, corner_radius=12, border_color=BORDER_COLOR)
entry_add.pack(side="left", fill="x", expand=True)
btn_add = ctk.CTkButton(add_frame, text="+", width=48, height=48, corner_radius=12, font=("Segoe UI", 24, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=lambda: add_item())
btn_add.pack(side="right", padx=(10, 0))
entry_add.bind('<Return>', lambda e: add_item())

search_entry = ctk.CTkEntry(sidebar, placeholder_text="🔍 Tìm kiếm từ vựng...", height=42, font=FONT_BODY, corner_radius=10, border_color=BORDER_COLOR)
search_entry.pack(fill="x", padx=20, pady=(0, 10))

search_timer = None
def on_search_change(*args):
    global search_timer
    if search_timer:
        app.after_cancel(search_timer)
    search_timer = app.after(300, perform_search)

def perform_search():
    query = search_entry.get()
    if tab_view.get() == "Từ Đơn":
        scroll_vocab.filter_items(query)
    else:
        scroll_phrase.filter_items(query)

search_entry.bind("<KeyRelease>", on_search_change)

sort_var = ctk.StringVar(value="Sắp xếp: Ngày học (Gần nhất)")
sort_options = ["Sắp xếp: Tên (A-Z)", "Sắp xếp: Ngày học (Gần nhất)", "Sắp xếp: Ngày học (Xa nhất)", "Sắp xếp: Số lần học (Nhiều nhất)", "Sắp xếp: Số lần học (Ít nhất)"]
def on_sort_change(choice):
    mapping = {"Sắp xếp: Tên (A-Z)": "name", "Sắp xếp: Ngày học (Gần nhất)": "recent", "Sắp xếp: Ngày học (Xa nhất)": "oldest", "Sắp xếp: Số lần học (Nhiều nhất)": "most", "Sắp xếp: Số lần học (Ít nhất)": "least"}
    (scroll_vocab if tab_view.get() == "Từ Đơn" else scroll_phrase).set_sort(mapping.get(choice, "recent"))
ctk.CTkOptionMenu(sidebar, variable=sort_var, values=sort_options, command=on_sort_change, font=FONT_BODY).pack(fill="x", padx=20, pady=(0,10))

voice_var = ctk.StringVar(value=data_manager.get_setting("global_voice", "Nữ (US - Google)"))
voice_options = ["Nữ (US - Google)", "Nữ (UK - Google)", "Nữ (Úc - Google)", "Nam (US - Hệ thống)", "Nam (UK - Hệ thống)"]
def on_voice_change(choice):
    data_manager.set_setting("global_voice", choice)
    play_sound_system("Voice updated")
ctk.CTkOptionMenu(sidebar, variable=voice_var, values=voice_options, command=on_voice_change, font=FONT_BODY).pack(fill="x", padx=20, pady=(0,10))

tab_view = ctk.CTkTabview(sidebar, width=500, command=on_search_change)
tab_view.pack(fill="both", expand=True, padx=20, pady=5)
tab_view.add("Từ Đơn")
tab_view.add("Cụm Từ")

scroll_vocab = VirtualScrollList(tab_view.tab("Từ Đơn"), item_type='vocab', bg=BG_SIDEBAR[1])
scroll_vocab.pack(fill="both", expand=True)
scroll_phrase = VirtualScrollList(tab_view.tab("Cụm Từ"), item_type='phrase', bg=BG_SIDEBAR[1])
scroll_phrase.pack(fill="both", expand=True)

main_view = ctk.CTkFrame(app, corner_radius=0, fg_color=BG_MAIN)
main_view.grid(row=1, column=1, sticky="nsew")

# --- TRỒNG CÂY TỪ VỰNG Ở MÀN HÌNH CHÍNH ---
frame_welcome = ctk.CTkFrame(main_view, fg_color="transparent")
frame_welcome.pack(expand=True)

lbl_tree_icon = ctk.CTkLabel(frame_welcome, text="🌱", font=("Segoe UI", 120))
lbl_tree_icon.pack(pady=10)
lbl_tree_msg = ctk.CTkLabel(frame_welcome, text="Học từ mới để tưới cây nhé!", font=("Segoe UI", 24, "bold"))
lbl_tree_msg.pack()
lbl_tree_progress = ctk.CTkLabel(frame_welcome, text="Giọt nước: 0", font=("Segoe UI", 16), text_color=TEXT_SUB)
lbl_tree_progress.pack(pady=5)

def update_home_screen():
    total_reps, is_withered, streak = data_manager.get_user_stats()
    
    # Cập nhật ngọn lửa
    lbl_streak.configure(text=f"🔥 {streak} Ngày")
    
    # Cập nhật Cây
    if is_withered:
        icon, msg, color = "🍂", "Cây đang héo vì thiếu nước...", COLOR_DANGER[0]
    elif total_reps >= 500:
        icon, msg, color = "🍎", "Cây đã đơm hoa kết trái!", COLOR_SUCCESS[0]
    elif total_reps >= 150:
        icon, msg, color = "🌳", "Cây đang lớn rất khỏe mạnh!", COLOR_SUCCESS[0]
    elif total_reps >= 30:
        icon, msg, color = "🌿", "Cây non đang vươn lên!", COLOR_SUCCESS[0]
    else:
        icon, msg, color = "🌱", "Gieo mầm từ vựng!", COLOR_ACCENT
        
    lbl_tree_icon.configure(text=icon)
    lbl_tree_msg.configure(text=msg, text_color=color)
    lbl_tree_progress.configure(text=f"💧 Tổng số lần đã học (Giọt nước): {total_reps}")

# Gọi hàm này khi khởi động app
update_home_screen()
ctk.CTkLabel(frame_welcome, text="📚", font=("Segoe UI", 70)).pack(pady=10)
ctk.CTkLabel(frame_welcome, text="Học thôi nào!", font=("Segoe UI", 24, "bold")).pack()

detail_container = ctk.CTkScrollableFrame(main_view, fg_color="transparent")

current_item, current_type = None, None

def refresh_lists():
    scroll_vocab.load_data()
    scroll_phrase.load_data()

def select_item(word, item_type):
    global current_item, current_type
    current_item, current_type = word, item_type
    
    # Cập nhật siêu tốc RAM-First
    data_manager.update_progress(word, item_type)
    detail = data_manager.get_detail(word, item_type)
    if not detail: return
    
    # Cập nhật danh sách in-place
    (scroll_vocab if item_type == 'vocab' else scroll_phrase).refresh_item(word)
    
    frame_welcome.pack_forget()
    detail_container.pack(fill="both", expand=True, padx=40, pady=20)
    
    title_text = word.lower()
    if detail.get('is_mastered', 0):
        title_text += " ✅"
        
    lbl_title.configure(text=title_text)
    lbl_vn.configure(text=detail['vn_meaning'].capitalize() if detail['vn_meaning'] else "")
    lbl_pos_text.configure(text=detail['pos'])
    lbl_ex.configure(text=f'"{detail["sentence"]}"')
    lbl_stats.configure(text=f"🔥 Số lần: {detail['study_count']}  •  🕒 Lần cuối: {detail['last_studied']}")
    lbl_ex_vn.configure(text="")
    
    check_mastered_var.set(detail.get('is_mastered', 0))
    
    lbl_alert.pack_forget()
    if detail['study_count'] >= 10 and detail['last_studied'] and (datetime.now() - datetime.strptime(detail['last_studied'], "%Y-%m-%d %H:%M")).days >= 3 and not detail.get('is_mastered', 0):
        lbl_alert.configure(text="🚨 Cảnh báo: Từ/Cụm này lâu rồi chưa ôn lại!")
        lbl_alert.pack(anchor="w", padx=25, pady=(10, 0))
    txt_note.delete("1.0", "end")
    txt_note.insert("1.0", detail.get("custom_sentence", ""))
    safe_set_image(lbl_img, new_image=None, new_text="Đang tìm ảnh...")
    play_sound_system(word)
    load_image_async(word, lbl_img)

def add_item():
    word = entry_add.get().strip().lower()
    if not word: return
    
    if word in data_manager.vocab:
        entry_add.delete(0, 'end'); tab_view.set("Từ Đơn"); select_item(word, 'vocab'); return
    if word in data_manager.phrase:
        entry_add.delete(0, 'end'); tab_view.set("Cụm Từ"); select_item(word, 'phrase'); return
    
    is_single = len(word.split()) == 1
    item_type = 'vocab' if is_single else 'phrase'
    entry_add.configure(state="disabled", placeholder_text="⏳ Đang tải dữ liệu...")
    
    def fetch_and_add():
        ex, pos, vn = get_word_info(word) if is_single else get_phrase_info(word)
        data_manager.add_or_update(word, item_type, ex, pos, vn, "")
        app.after(0, lambda: [entry_add.configure(state="normal", placeholder_text="Nhập nhanh 1 từ/cụm từ..."), entry_add.delete(0, 'end'), tab_view.set("Từ Đơn" if item_type == 'vocab' else "Cụm Từ"), refresh_lists(), select_item(word, item_type)])
    executor.submit(fetch_and_add)

def edit_vn_meaning():
    if not current_item: return
    new_vn = ctk.CTkInputDialog(text=f"Sửa nghĩa tiếng Việt của '{current_item}':", title="Sửa nghĩa").get_input()
    if new_vn and new_vn.strip():
        data_manager.update_field(current_item, current_type, 'vn_meaning', new_vn.strip())
        lbl_vn.configure(text=new_vn.strip().capitalize())
        (scroll_vocab if current_type == 'vocab' else scroll_phrase).refresh_item(current_item)

def item_delete_cmd():
    global current_item, current_type
    if current_item and messagebox.askyesno("Xóa", f"Xóa '{current_item}'?"):
        data_manager.delete(current_item, current_type)
        detail_container.pack_forget(); frame_welcome.pack(expand=True)
        refresh_lists()
        current_item, current_type = None, None

def save_custom_note():
    if current_item:
        data_manager.update_field(current_item, current_type, 'custom_sentence', txt_note.get("1.0", "end-1c"))
        messagebox.showinfo("OK", "Đã lưu ghi chú")

c1 = ctk.CTkFrame(detail_container, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
c1.pack(fill="x", pady=(10, 20))
hl = ctk.CTkFrame(c1, fg_color="transparent")
hl.pack(side="left", padx=25, pady=20)
lbl_title = ctk.CTkLabel(hl, text="", font=FONT_TITLE, wraplength=500, justify="left")
lbl_title.pack(anchor="w")
vf = ctk.CTkFrame(hl, fg_color="transparent")
vf.pack(anchor="w")
lbl_vn = ctk.CTkLabel(vf, text="", font=FONT_VN, text_color=COLOR_SUCCESS[0], wraplength=350, justify="left")
lbl_vn.pack(side="left")
ctk.CTkButton(vf, text="✏️", width=30, height=30, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, text_color=COLOR_ACCENT, command=edit_vn_meaning).pack(side="left", padx=(10, 0))
pf = ctk.CTkFrame(hl, corner_radius=8, fg_color=COLOR_ACCENT)
pf.pack(anchor="w", pady=(10,0))
lbl_pos_text = ctk.CTkLabel(pf, text="", font=("Segoe UI", 13, "bold"), text_color="white")
lbl_pos_text.pack(padx=12, pady=4)

ctk.CTkButton(c1, text="🔊 Anh-Anh", width=100, height=45, corner_radius=12, fg_color=BG_MAIN, border_width=1, border_color=BORDER_COLOR, text_color=("black", "white"), hover_color=HOVER_COLOR_CARD, command=lambda: play_sound_system(current_item, tld='co.uk') if current_item else None).pack(side="right", pady=25, padx=(10, 25))
ctk.CTkButton(c1, text="🔊 Anh-Mỹ", width=100, height=45, corner_radius=12, fg_color=BG_MAIN, border_width=1, border_color=BORDER_COLOR, text_color=("black", "white"), hover_color=HOVER_COLOR_CARD, command=lambda: play_sound_system(current_item, tld='com') if current_item else None).pack(side="right", pady=25)

def toggle_mastered():
    if current_item:
        val = 1 if check_mastered_var.get() else 0
        data_manager.update_field(current_item, current_type, 'is_mastered', val)
        (scroll_vocab if current_type == 'vocab' else scroll_phrase).refresh_item(current_item)

check_mastered_var = ctk.IntVar()
chk_mastered = ctk.CTkCheckBox(c1, text="Đã thuộc", variable=check_mastered_var, command=toggle_mastered, font=("Segoe UI", 15, "bold"), text_color=COLOR_SUCCESS[0], hover_color="#28a745", fg_color=COLOR_SUCCESS[0])
chk_mastered.pack(side="right", padx=20, pady=20)

c2 = ctk.CTkFrame(detail_container, fg_color="transparent")
c2.pack(fill="x", pady=10)
img_f = ctk.CTkFrame(c2, corner_radius=16, fg_color=BG_CARD, width=200, height=200, border_width=1, border_color=BORDER_COLOR)
img_f.pack(side="left"); img_f.pack_propagate(False)
lbl_img = ctk.CTkLabel(img_f, text="⌛", font=FONT_BODY, text_color=TEXT_SUB)
lbl_img.pack(expand=True)
c2_info = ctk.CTkFrame(c2, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
c2_info.pack(side="left", fill="both", expand=True, padx=(20, 0))
lbl_alert = ctk.CTkLabel(c2_info, text="", font=("Segoe UI", 13, "bold"), text_color=COLOR_DANGER[0])
lbl_stats = ctk.CTkLabel(c2_info, text="", font=FONT_BODY, text_color=TEXT_SUB)
lbl_stats.pack(anchor="w", padx=25, pady=(20, 5))
lbl_ex = ctk.CTkLabel(c2_info, text="", font=FONT_ITALIC, wraplength=450, justify="left")
lbl_ex.pack(anchor="w", padx=25, pady=(5, 5))
lbl_ex_vn = ctk.CTkLabel(c2_info, text="", font=("Segoe UI", 15, "italic"), wraplength=450, justify="left", text_color=TEXT_SUB)
lbl_ex_vn.pack(anchor="w", padx=25, pady=(0, 10))

def translate_example():
    if not current_item: return
    sentence = data_manager.get_detail(current_item, current_type)['sentence']
    if not sentence or "Chưa có" in sentence or "Hãy tự đặt" in sentence: return
    
    lbl_ex_vn.configure(text="⏳ Đang dịch...")
    def task():
        try:
            vn_text = translator.translate(sentence)
            app.after(0, lambda: lbl_ex_vn.configure(text=f"Dịch: {vn_text}") if current_item else None)
        except:
            app.after(0, lambda: lbl_ex_vn.configure(text="❌ Lỗi dịch thuật. Hãy kiểm tra kết nối mạng."))
    executor.submit(task)

ex_audio_frame = ctk.CTkFrame(c2_info, fg_color="transparent")
ex_audio_frame.pack(anchor="w", padx=25)
ctk.CTkButton(ex_audio_frame, text="▶ Ví dụ (Mỹ)", width=120, height=35, corner_radius=8, border_width=1, border_color=BORDER_COLOR, fg_color="transparent", text_color=("black", "white"), hover_color=HOVER_COLOR_TRANSPARENT, command=lambda: play_sound_system(data_manager.get_detail(current_item, current_type)['sentence'] if current_item else "", tld='com')).pack(side="left", padx=(0, 10))
ctk.CTkButton(ex_audio_frame, text="▶ Ví dụ (Anh)", width=120, height=35, corner_radius=8, border_width=1, border_color=BORDER_COLOR, fg_color="transparent", text_color=("black", "white"), hover_color=HOVER_COLOR_TRANSPARENT, command=lambda: play_sound_system(data_manager.get_detail(current_item, current_type)['sentence'] if current_item else "", tld='co.uk')).pack(side="left")
ctk.CTkButton(ex_audio_frame, text="🌍 Dịch nghĩa", width=120, height=35, corner_radius=8, border_width=1, border_color=BORDER_COLOR, fg_color="transparent", text_color=("black", "white"), hover_color=HOVER_COLOR_TRANSPARENT, command=translate_example).pack(side="left", padx=(10, 0))

c3 = ctk.CTkFrame(detail_container, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
c3.pack(fill="x", pady=20)
ctk.CTkLabel(c3, text="📝 Ghi chú của bạn / Đặt câu tự do", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=25, pady=(20, 10))
txt_note = ctk.CTkTextbox(c3, height=100, corner_radius=12, border_width=1, border_color=BORDER_COLOR, fg_color=BG_MAIN, font=FONT_BODY)
txt_note.pack(fill="x", padx=25, pady=(0, 20))
bf = ctk.CTkFrame(c3, fg_color="transparent")
bf.pack(fill="x", padx=25, pady=(0, 25))
ctk.CTkButton(bf, text="💾 Lưu ghi chú", height=38, corner_radius=8, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", width=120, command=save_custom_note).pack(side="left")
ctk.CTkButton(bf, text="🗑 Xóa Mục", height=38, corner_radius=8, fg_color="transparent", hover_color=("#FFD1D1", "#5C1A1A"), text_color=COLOR_DANGER[0], border_width=1, border_color=COLOR_DANGER[0], width=100, command=item_delete_cmd).pack(side="right")

# ================== GAME ÔN TẬP (GIAO DIỆN HIỆN ĐẠI & SỬA LỖI) ==================
def check_spaced_repetition(item):
    """Thuật toán tính ngày ôn tập (Spaced Repetition)"""
    if not item['last_studied']: return True
    try:
        last_date = datetime.strptime(item['last_studied'][:10], "%Y-%m-%d")
        days_passed = (datetime.now() - last_date).days
        c = item['study_count']
        # Mốc thời gian: 1 ngày -> 3 ngày -> 7 ngày -> 14 ngày -> 30 ngày
        if c <= 1: interval = 1
        elif c == 2: interval = 3
        elif c == 3: interval = 7
        elif c <= 5: interval = 14
        else: interval = 30
        return days_passed >= interval
    except:
        return True

def get_game_data(source_type, include_mastered=False):
    today = datetime.now().strftime("%Y-%m-%d")
    items = []
    for t, data_dict in [('vocab', data_manager.vocab), ('phrase', data_manager.phrase)]:
        for word, d in data_dict.items():
            if not include_mastered and d.get('is_mastered', 0):
                continue
            item_data = {"word": word, "vn_meaning": d['vn_meaning'], "sentence": d.get('sentence', ''), "item_type": t, "last_studied": d['last_studied'], "study_count": d['study_count'], "pos": d.get('pos', '')}
            if source_type == "Chưa ôn hôm nay":
                # Kích hoạt Spaced Repetition ở đây
                if check_spaced_repetition(item_data) and word not in data_manager.tracker.get(today, set()):
                    items.append(item_data)
            else:
                items.append(item_data)
                
    items.sort(key=lambda x: x['study_count'])
    return items

class GameSetupDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Cài đặt Game")
        self.geometry("550x500")
        self.transient(master)
        self.grab_set()
        self.result_num, self.result_mode, self.result_data = None, None, None
        
        # Main Card
        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=25, pady=25)

        ctk.CTkLabel(card, text="🎮 CÀI ĐẶT TRÒ CHƠI", font=("Segoe UI", 22, "bold"), text_color=COLOR_ACCENT).pack(pady=(25, 10))
        
        self.source_mode = ctk.CTkSegmentedButton(card, values=["Ngẫu nhiên", "Chưa ôn hôm nay"], font=FONT_BODY, command=self.update_slider_max)
        self.source_mode.set("Chưa ôn hôm nay")
        self.source_mode.pack(pady=10, fill="x", padx=40)
        
        self.chk_include_mastered_var = ctk.IntVar(value=0)
        self.chk_include_mastered = ctk.CTkCheckBox(card, text="Bao gồm cả từ đã thuộc", variable=self.chk_include_mastered_var, command=lambda: self.update_slider_max(self.source_mode.get()))
        self.chk_include_mastered.pack(pady=5)
        
        self.lbl_empty_alert = ctk.CTkLabel(card, text="", text_color=COLOR_SUCCESS[0], font=("Segoe UI", 12, "italic"))
        self.lbl_empty_alert.pack()
        
        self.game_mode = ctk.CTkOptionMenu(card, values=["Trắc nghiệm", "Đoán Chữ (Hangman)", "Đảo chữ", "Nối từ", "Lật Thẻ Bài", "Nghe & Gõ", "Điền Từ", "Sinh Tồn"], font=("Segoe UI", 16))
        self.game_mode.set("Trắc nghiệm")
        self.game_mode.pack(pady=10, fill="x", padx=40)
        
        self.lbl_val = ctk.CTkLabel(card, text="5 Từ", font=("Segoe UI", 32, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_val.pack(pady=(15, 0))
        
        self.slider = ctk.CTkSlider(card, from_=1, to=10, number_of_steps=9, command=lambda v: self.lbl_val.configure(text=f"{int(v)} Từ"))
        self.slider.pack(fill="x", padx=50, pady=10)
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(20, 25), fill="x", padx=40)
        ctk.CTkButton(btn_frame, text="Hủy", width=120, height=40, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, text_color=TEXT_SUB, command=self.destroy).pack(side="left")
        self.btn_start = ctk.CTkButton(btn_frame, text="Bắt đầu", width=120, height=40, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.on_ok)
        self.btn_start.pack(side="right")
        
        self.update_slider_max(self.source_mode.get())
        self.wait_window()
    
    def update_slider_max(self, mode):
        data = get_game_data(mode, self.chk_include_mastered_var.get())
        max_words = min(len(data), 50)
        if max_words == 0:
            self.lbl_empty_alert.configure(text="🎉 Bạn đã ôn hết từ vựng hôm nay.")
            self.slider.configure(state="disabled")
            self.btn_start.configure(state="disabled")
            self.lbl_val.configure(text="0 Từ")
        else:
            self.lbl_empty_alert.configure(text="")
            self.slider.configure(state="normal", from_=1, to=max_words, number_of_steps=max_words-1 if max_words>1 else 1)
            self.btn_start.configure(state="normal")
            val = min(5, max_words)
            self.slider.set(val)
            self.lbl_val.configure(text=f"{int(val)} Từ")
            
    def on_ok(self):
        self.result_num, self.result_mode, self.result_data = int(self.slider.get()), self.game_mode.get(), get_game_data(self.source_mode.get(), self.chk_include_mastered_var.get())
        self.destroy()

def open_game_setup():
    d = GameSetupDialog(app)
    if d.result_num and d.result_data:
        if d.result_mode == "Trắc nghiệm": QuizGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Đoán Chữ (Hangman)": HangmanGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Đảo chữ": ScrambleGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Nối từ": MatchGameWindow(app, min(d.result_num, 10), d.result_data)
        elif d.result_mode == "Lật Thẻ Bài": MemoryCardGameWindow(app, min(d.result_num, 8), d.result_data)
        elif d.result_mode == "Nghe & Gõ": DictationGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Sinh Tồn": SurvivalGameWindow(app, d.result_data)
        elif d.result_mode == "Điền Từ": ClozeGameWindow(app, d.result_num, d.result_data)

class BaseGameWindow(ctk.CTkToplevel):
    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.geometry("800x650")
        self.transient(master)
        self.grab_set()
        self.questions = []
        self.current_idx = 0
        self.score = 0
        
        # Thanh trạng thái phía trên (Progress)
        self.top_frame = ctk.CTkFrame(self, height=60, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=30, pady=(20, 10))
        
        self.lbl_progress_text = ctk.CTkLabel(self.top_frame, text="Câu 0/0", font=("Segoe UI", 16, "bold"), text_color=TEXT_SUB)
        self.lbl_progress_text.pack(side="left")
        
        self.lbl_score = ctk.CTkLabel(self.top_frame, text="Điểm: 0", font=("Segoe UI", 16, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_score.pack(side="right")
        
        self.progress_bar = ctk.CTkProgressBar(self, height=8, progress_color=COLOR_ACCENT)
        self.progress_bar.pack(fill="x", padx=30, pady=(0, 20))
        self.progress_bar.set(0)

        # Khu vực chơi chính
        self.game_area = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        self.game_area.pack(fill="both", expand=True, padx=30, pady=(0, 30))

class QuizGameWindow(BaseGameWindow):
    def __init__(self, master, num, data):
        super().__init__(master, "Game Trắc Nghiệm")
        self.game_data = data
        self.prepare(num)
        self.build()
        self.load()

    def prepare(self, num):
        selected = random.sample(self.game_data, min(num, len(self.game_data)))
        for item in selected:
            # Lấy list các từ khác làm đáp án nhiễu (Chống lỗi nếu DB ít hơn 4 từ)
            others = [x['word'] for x in self.game_data if x['word'] != item['word']]
            opts = [item['word']] + random.sample(others, min(3, len(others)))
            random.shuffle(opts)
            self.questions.append((item['word'], item['vn_meaning'], opts, item['item_type']))

    def build(self):
        self.lbl_q = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 28, "bold"), text_color=COLOR_ACCENT, wraplength=600)
        self.lbl_q.pack(pady=(40, 30), expand=True)
        
        # Grid 2x2 cho nút bấm
        self.btn_grid = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.btn_grid.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.btn_grid.grid_columnconfigure((0, 1), weight=1)
        
        self.btn_opts = []
        for i in range(4):
            btn = ctk.CTkButton(self.btn_grid, text="", height=75, corner_radius=16, font=("Segoe UI", 18, "bold"), border_width=1, border_color=BORDER_COLOR,
                                fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_ACCENT_HOVER,
                                command=lambda idx=i: self.check(idx))
            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
            self.btn_opts.append(btn)

    def load(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.questions):
            messagebox.showinfo("Kết thúc", f"Bạn làm đúng {self.score}/{len(self.questions)} câu.")
            refresh_lists()
            self.destroy()
            return
            
        word, vn, opts, _ = self.questions[self.current_idx]
        
        self.lbl_progress_text.configure(text=f"Câu {self.current_idx+1}/{len(self.questions)}")
        self.progress_bar.set((self.current_idx) / len(self.questions))
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        self.lbl_q.configure(text=vn.capitalize())
        
        for i, btn in enumerate(self.btn_opts):
            if i < len(opts):
                btn.configure(text=opts[i].capitalize(), state="normal")
            else:
                btn.configure(text="", state="disabled") # Ẩn nút nếu thiếu từ nhiễu

    def check(self, idx):
        cw, _, opts, ty = self.questions[self.current_idx]
        if opts[idx] == cw: 
            data_manager.update_progress(cw, ty)
            self.score += 1
            play_sound_system(cw)
        else: 
            messagebox.showerror("Sai rồi", f"Đáp án đúng là:\n{cw.upper()}")
        self.current_idx += 1
        self.load()
class SurvivalGameWindow(BaseGameWindow):
    def __init__(self, master, data):
        super().__init__(master, "Game Sinh Tồn (Survival)")
        # Xóa thanh progress bar cũ vì sinh tồn không có điểm kết thúc cố định
        self.progress_bar.pack_forget() 
        self.lbl_progress_text.pack_forget()
        
        # Sinh tồn thì lấy ngẫu nhiên liên tục từ toàn bộ dữ liệu
        self.all_data = [item for item in data if item['item_type'] == 'vocab'] 
        if len(self.all_data) < 4:
            messagebox.showerror("Lỗi", "Cần ít nhất 4 từ đơn để chơi Sinh Tồn!")
            self.destroy(); return
            
        self.lives = 3
        self.time_left = 10.0
        self.timer_id = None
        self.score = 0
        
        self.build()
        self.next_round()

    def build(self):
        # Trái tim
        self.lbl_lives = ctk.CTkLabel(self.top_frame, text="❤️❤️❤️", font=("Segoe UI", 24))
        self.lbl_lives.pack(side="left")
        
        # Thanh thời gian
        self.time_bar = ctk.CTkProgressBar(self.game_area, height=12, progress_color=COLOR_SUCCESS[0])
        self.time_bar.pack(fill="x", padx=40, pady=(20, 0))
        
        self.lbl_q = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 32, "bold"), text_color=COLOR_ACCENT, wraplength=600)
        self.lbl_q.pack(pady=(30, 20), expand=True)
        
        self.btn_grid = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.btn_grid.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.btn_grid.grid_columnconfigure((0, 1), weight=1)
        
        self.btn_opts = []
        for i in range(4):
            btn = ctk.CTkButton(self.btn_grid, text="", height=75, corner_radius=16, font=("Segoe UI", 18, "bold"), border_width=1, border_color=BORDER_COLOR,
                                fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_ACCENT_HOVER,
                                command=lambda idx=i: self.check(idx))
            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
            self.btn_opts.append(btn)

    def next_round(self):
        if not self.winfo_exists(): return
        if self.lives <= 0:
            self.game_over()
            return
            
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        self.lbl_lives.configure(text="❤️" * self.lives)
        
        # Tạo câu hỏi ngẫu nhiên
        item = random.choice(self.all_data)
        self.current_word = item['word']
        self.current_type = item['item_type']
        
        others = [x['word'] for x in self.all_data if x['word'] != self.current_word]
        self.opts = [self.current_word] + random.sample(others, min(3, len(others)))
        random.shuffle(self.opts)
        
        self.lbl_q.configure(text=item['vn_meaning'].capitalize())
        for i, btn in enumerate(self.btn_opts):
            btn.configure(text=self.opts[i].capitalize(), fg_color=BG_MAIN)
            
        # Reset thời gian (càng điểm cao càng chạy nhanh)
        self.time_left = max(3.0, 10.0 - (self.score * 0.2)) 
        self.max_time = self.time_left
        self.tick()

    def tick(self):
        if not self.winfo_exists(): return
        self.time_left -= 0.05
        progress = max(0.0, self.time_left / self.max_time)
        self.time_bar.set(progress)
        
        if progress < 0.3: self.time_bar.configure(progress_color=COLOR_DANGER[0])
        else: self.time_bar.configure(progress_color=COLOR_SUCCESS[0])
            
        if self.time_left <= 0:
            self.lose_life()
        else:
            self.timer_id = self.after(50, self.tick)

    def check(self, idx):
        if self.timer_id: self.after_cancel(self.timer_id)
        
        if self.opts[idx] == self.current_word:
            self.score += 1
            data_manager.update_progress(self.current_word, self.current_type)
            play_sound_system(self.current_word)
            self.next_round()
        else:
            self.btn_opts[idx].configure(fg_color=COLOR_DANGER[0])
            self.lose_life()

    def lose_life(self):
        if self.timer_id: self.after_cancel(self.timer_id)
        self.lives -= 1
        play_sound_system("Oops") # Hoặc bỏ dòng này nếu không có file âm thanh
        if self.lives > 0:
            self.after(500, self.next_round)
        else:
            self.game_over()

    def game_over(self):
        self.lbl_lives.configure(text="💀 HẾT MẠNG")
        self.lbl_q.configure(text=f"GAME OVER!\nBạn sống sót qua {self.score} câu.", text_color=COLOR_DANGER[0])
        for btn in self.btn_opts: btn.configure(state="disabled")
        update_home_screen()
# ================== BỘ 3 GAME 8-BIT RETRO ==================

class RPGBossGameWindow(BaseGameWindow):
    def __init__(self, master, data):
        super().__init__(master, "RPG Đánh Boss (8-bit)")
        self.game_area.configure(fg_color="#1E1E24") # Nền tối kiểu game cũ
        self.progress_bar.pack_forget()
        self.lbl_progress_text.pack_forget()
        
        self.all_data = [item for item in data if item['item_type'] == 'vocab']
        self.boss_hp = 1000
        self.boss_max_hp = 1000
        self.player_hp = 3
        self.time_left = 5.0
        self.timer_id = None
        
        self.build()
        self.next_round()

    def build(self):
        # Khu vực chiến đấu
        battle_frame = ctk.CTkFrame(self.game_area, fg_color="transparent")
        battle_frame.pack(fill="x", pady=20, padx=20)
        
        # Player (Trái)
        p_frame = ctk.CTkFrame(battle_frame, fg_color="transparent")
        p_frame.pack(side="left", padx=20)
        self.lbl_player = ctk.CTkLabel(p_frame, text="🤺", font=("Segoe UI", 60))
        self.lbl_player.pack()
        self.lbl_php = ctk.CTkLabel(p_frame, text="❤️❤️❤️", font=("Segoe UI", 16))
        self.lbl_php.pack()

        # Boss (Phải)
        b_frame = ctk.CTkFrame(battle_frame, fg_color="transparent")
        b_frame.pack(side="right", padx=20)
        self.lbl_boss = ctk.CTkLabel(b_frame, text="👾", font=("Segoe UI", 80))
        self.lbl_boss.pack()
        self.boss_hp_bar = ctk.CTkProgressBar(b_frame, width=150, height=15, progress_color="#FF3B30")
        self.boss_hp_bar.pack(pady=5)
        self.boss_hp_bar.set(1.0)
        
        # Thông báo (Console)
        self.lbl_console = ctk.CTkLabel(self.game_area, text="Quái vật xuất hiện!", font=("Courier New", 18, "bold"), text_color="#34C759")
        self.lbl_console.pack(pady=10)
        
        # Câu hỏi (Nghĩa tiếng Việt)
        self.lbl_q = ctk.CTkLabel(self.game_area, text="", font=("Courier New", 26, "bold"), text_color="white", wraplength=500)
        self.lbl_q.pack(pady=(10, 20))
        
        # Nút đánh
        self.btn_grid = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.btn_grid.pack(fill="both", expand=True, padx=20, pady=10)
        self.btn_grid.grid_columnconfigure((0, 1), weight=1)
        self.btn_opts = []
        for i in range(4):
            btn = ctk.CTkButton(self.btn_grid, text="", height=60, font=("Courier New", 16, "bold"), fg_color="#272730", border_width=2, border_color="#34C759", command=lambda idx=i: self.attack(idx))
            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
            self.btn_opts.append(btn)

    def next_round(self):
        if self.boss_hp <= 0:
            self.lbl_console.configure(text="WIN! CHÚA TỂ TỪ VỰNG ĐÃ BỊ HẠ GỤC!", text_color="#FFD700")
            self.lbl_boss.configure(text="💀")
            for b in self.btn_opts: b.configure(state="disabled")
            update_home_screen()
            return
        if self.player_hp <= 0:
            self.lbl_console.configure(text="GAME OVER! HIỆP SĨ GỤC NGÃ...", text_color="#FF3B30")
            self.lbl_player.configure(text="🪦")
            for b in self.btn_opts: b.configure(state="disabled")
            return

        item = random.choice(self.all_data)
        self.current_word = item['word']
        self.opts = [self.current_word] + random.sample([x['word'] for x in self.all_data if x['word'] != self.current_word], 3)
        random.shuffle(self.opts)
        
        self.lbl_q.configure(text=f"[{item['vn_meaning'].upper()}]")
        for i, btn in enumerate(self.btn_opts):
            btn.configure(text=self.opts[i].upper())
            
        self.time_left = 5.0
        self.lbl_console.configure(text="Quái đang gồng chiêu! Đỡ đòn nhanh!", text_color="white")
        self.tick()

    def tick(self):
        self.time_left -= 0.1
        if self.time_left <= 0:
            self.player_hp -= 1
            self.lbl_php.configure(text="❤️" * self.player_hp)
            self.lbl_console.configure(text="Chậm quá! Bị quái đập trúng!", text_color="#FF3B30")
            self.lbl_player.configure(text="😵")
            play_sound_system("Oops")
            self.after(1000, lambda: [self.lbl_player.configure(text="🤺"), self.next_round()])
        else:
            self.timer_id = self.after(100, self.tick)

    def attack(self, idx):
        if self.timer_id: self.after_cancel(self.timer_id)
        if self.opts[idx] == self.current_word:
            data_manager.update_progress(self.current_word, 'vocab')
            play_sound_system(self.current_word)
            
            # Đánh nhanh < 2 giây = Chí mạng
            if self.time_left >= 3.0:
                dmg = 200
                self.lbl_console.configure(text=f"CHÍ MẠNG! Trừ {dmg} HP!", text_color="#FFD700")
                self.lbl_player.configure(text="🗡️⚡")
            else:
                dmg = 100
                self.lbl_console.configure(text=f"Đánh thường! Trừ {dmg} HP", text_color="#34C759")
                self.lbl_player.configure(text="🗡️")
                
            self.boss_hp -= dmg
            self.boss_hp_bar.set(max(0, self.boss_hp / self.boss_max_hp))
            self.after(1000, lambda: [self.lbl_player.configure(text="🤺"), self.next_round()])
        else:
            self.player_hp -= 1
            self.lbl_php.configure(text="❤️" * self.player_hp)
            self.lbl_console.configure(text="Đánh trượt! Bị quái phản công!", text_color="#FF3B30")
            self.after(1000, self.next_round)

class InvadersGameWindow(BaseGameWindow):
    def __init__(self, master, data):
        super().__init__(master, "Bắn Ruồi Từ Vựng (Invaders)")
        self.all_data = [item for item in data if item['item_type'] == 'vocab']
        self.progress_bar.pack_forget(); self.lbl_progress_text.pack_forget()
        
        self.game_area.configure(fg_color="#000000")
        
        self.lives = 3
        self.score = 0
        self.speed = 2.0
        self.timer_id = None
        self.is_game_over = False
        
        self.build_ui()
        self.spawn_wave()
        self.game_loop()

    def build_ui(self):
        # Thanh trạng thái phía trên (Mạng, Điểm, Nút Thoát)
        top_hud = ctk.CTkFrame(self.game_area, fg_color="transparent")
        top_hud.pack(fill="x", padx=15, pady=10)
        
        self.lbl_stats = ctk.CTkLabel(top_hud, text="❤️❤️❤️   |   ĐIỂM: 0", font=("Courier New", 20, "bold"), text_color="#34C759")
        self.lbl_stats.pack(side="left")
        
        btn_exit = ctk.CTkButton(top_hud, text="🚪 THOÁT", font=("Segoe UI", 14, "bold"), fg_color="#FF3B30", hover_color="#C93429", width=90, command=self.exit_game)
        btn_exit.pack(side="right")
        
        # Màn hình chơi (Bầu trời sao)
        self.canvas_width = 650
        self.canvas_height = 350
        self.canvas = ctk.CTkCanvas(self.game_area, bg="#0B0B1A", highlightthickness=0, height=self.canvas_height)
        self.canvas.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Nghĩa mục tiêu ở dưới cùng
        self.lbl_target = ctk.CTkLabel(self.game_area, text="", font=("Courier New", 26, "bold"), text_color="#00FFFF", fg_color="transparent")
        self.lbl_target.pack(pady=(5, 0))
        
        # Hướng dẫn
        ctk.CTkLabel(self.game_area, text="BẤM PHÍM SỐ [1], [2], [3], [4] TRÊN BÀN PHÍM ĐỂ BẮN", font=("Courier New", 14), text_color="yellow").pack(pady=(0, 10))
        
        self.bind("<Key>", self.key_pressed)
        self.enemies = []

    def draw_background(self):
        self.canvas.delete("all")
        # Vẽ sao lấp lánh
        for _ in range(40):
            x = random.randint(0, self.canvas_width)
            y = random.randint(0, self.canvas_height)
            size = random.choice([1, 2])
            color = random.choice(["white", "#AAAAAA", "#FFFFCC"])
            self.canvas.create_oval(x, y, x+size, y+size, fill=color, outline=color)
        
        # Vẽ căn cứ Trái Đất ở dưới cùng
        self.base_x = self.canvas_width / 2
        self.base_y = self.canvas_height - 20
        self.canvas.create_text(self.base_x, self.base_y, text="🌍", font=("Segoe UI", 50))

    def spawn_wave(self):
        if self.is_game_over: return
        self.draw_background()
        self.enemies.clear()
        
        item = random.choice(self.all_data)
        self.target_word = item['word']
        self.target_type = item['item_type']
        self.lbl_target.configure(text=f"BẢO VỆ TRÁI ĐẤT KHỎI: [ {item['vn_meaning'].upper()} ]")
        
        opts = [self.target_word] + random.sample([x['word'] for x in self.all_data if x['word'] != self.target_word], 3)
        random.shuffle(opts)
        
        for i, word in enumerate(opts):
            x = (self.canvas_width / 4) * i + (self.canvas_width / 8)
            y = -20
            # Vẽ phi thuyền và số thứ tự
            ship = self.canvas.create_text(x, y, text="🛸", font=("Segoe UI", 35))
            txt = self.canvas.create_text(x, y-30, text=f"[{i+1}] {word.upper()}", font=("Courier New", 16, "bold"), fill="#00FF00")
            self.enemies.append({'ship': ship, 'txt': txt, 'word': word, 'x': x, 'y': y, 'active': True})
            
        play_sound_system(self.target_word) # Đọc từ lên để dễ nhận diện

    def game_loop(self):
        if self.is_game_over: return
        
        all_destroyed = True
        for e in self.enemies:
            if not e['active']: continue
            all_destroyed = False
            e['y'] += self.speed
            self.canvas.coords(e['ship'], e['x'], e['y'])
            self.canvas.coords(e['txt'], e['x'], e['y']-30)
            
            # Nếu phi thuyền chạm đất
            if e['y'] > self.canvas_height - 40:
                self.lose_life("QUÁI VẬT ĐÃ CHẠM ĐẤT!")
                return
                
        if all_destroyed:
            self.spawn_wave()
            
        self.timer_id = self.after(50, self.game_loop)

    def key_pressed(self, event):
        if self.is_game_over: return
        if event.char in ['1', '2', '3', '4']:
            idx = int(event.char) - 1
            if idx < len(self.enemies) and self.enemies[idx]['active']:
                e = self.enemies[idx]
                
                # Hiệu ứng bắn Laser từ Trái Đất lên Phi thuyền
                laser = self.canvas.create_line(self.base_x, self.base_y - 30, e['x'], e['y'], fill="#00FFFF", width=4)
                self.after(100, lambda: self.canvas.delete(laser))
                
                if e['word'] == self.target_word:
                    # Bắn ĐÚNG!
                    self.score += 1
                    self.speed = min(8.0, self.speed + 0.1) # Tăng độ khó từ từ
                    
                    # Hệ thống TỰ ĐỘNG LƯU (Chỉ cộng 1 lần/ngày nhờ logic của bạn)
                    data_manager.update_progress(self.target_word, self.target_type)
                    
                    self.update_stats_hud()
                    
                    # Hiệu ứng nổ tung
                    e['active'] = False
                    self.canvas.itemconfig(e['ship'], text="💥")
                    self.canvas.itemconfig(e['txt'], fill="gray")
                    self.after(300, lambda: [self.canvas.delete(e['ship']), self.canvas.delete(e['txt']), self.spawn_wave()])
                else:
                    # Bắn SAI!
                    self.lose_life("BẮN NHẦM ĐỒNG MINH!")

    def lose_life(self, reason):
        if self.timer_id: self.after_cancel(self.timer_id)
        self.lives -= 1
        self.update_stats_hud()
        
        if self.lives > 0:
            self.lbl_target.configure(text=f"⚠️ {reason} - MẤT 1 MẠNG!", text_color="#FF3B30")
            self.after(1500, lambda: [self.spawn_wave(), self.game_loop()])
        else:
            self.is_game_over = True
            self.lbl_target.configure(text="💀 GAME OVER! TRÁI ĐẤT ĐÃ BỊ XÚC!", text_color="#FF3B30")
            self.canvas.create_text(self.canvas_width/2, self.canvas_height/2, text="GAME OVER", font=("Courier New", 50, "bold"), fill="#FF3B30")

    def update_stats_hud(self):
        hearts = "❤️" * self.lives + "🖤" * (3 - self.lives)
        self.lbl_stats.configure(text=f"{hearts}   |   ĐIỂM: {self.score}")

    def exit_game(self):
        """Hàm này xử lý việc lưu dữ liệu và đóng cửa sổ khi bấm Nút Thoát"""
        self.is_game_over = True
        if self.timer_id: 
            self.after_cancel(self.timer_id)
            
        # Cập nhật danh sách từ vựng và Cây bên ngoài giao diện chính
        refresh_lists()
        try: update_home_screen() 
        except: pass
        
        self.destroy()

class NinjaGameWindow(BaseGameWindow):
    def __init__(self, master, data):
        super().__init__(master, "Ninja Vượt Ải (Listen & Jump)")
        self.all_data = [item for item in data if item['item_type'] == 'vocab']
        self.game_area.configure(fg_color="#87CEEB") # Nền trời xanh
        self.progress_bar.pack_forget(); self.lbl_progress_text.pack_forget()
        
        self.score = 0
        self.build()
        self.next_round()

    def build(self):
        # Nhân vật
        self.char_frame = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.char_frame.pack(fill="x", pady=20)
        self.lbl_ninja = ctk.CTkLabel(self.char_frame, text="🥷 💨", font=("Segoe UI", 50))
        self.lbl_ninja.pack(side="left", padx=50)
        
        # Bảng hướng dẫn
        self.lbl_guide = ctk.CTkLabel(self.game_area, text="NGHE VÀ CHỌN VIÊN GẠCH ĐÚNG ĐỂ NHẢY LÊN!", font=("Courier New", 18, "bold"), text_color="black", fg_color="white", corner_radius=10)
        self.lbl_guide.pack(pady=20, ipadx=10, ipady=5)
        
        ctk.CTkButton(self.game_area, text="🔊 NGHE LẠI", font=("Courier New", 16, "bold"), fg_color="#FF9500", command=self.play_audio).pack(pady=10)

        # 3 Viên gạch (Lựa chọn)
        self.brick_frame = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.brick_frame.pack(side="bottom", pady=40)
        
        self.bricks = []
        for i in range(3):
            btn = ctk.CTkButton(self.brick_frame, text="", height=80, width=150, font=("Courier New", 16, "bold"), fg_color="#8B4513", text_color="white", corner_radius=0, border_width=2, border_color="#5C4033", command=lambda idx=i: self.jump(idx))
            btn.pack(side="left", padx=15)
            self.bricks.append(btn)

    def next_round(self):
        self.lbl_ninja.configure(text="🥷 💨") # Reset dáng chạy
        item = random.choice(self.all_data)
        self.current_word = item['word']
        
        opts = [item['vn_meaning']] + random.sample([x['vn_meaning'] for x in self.all_data if x['word'] != self.current_word], 2)
        random.shuffle(opts)
        self.correct_meaning = item['vn_meaning']
        
        for i, btn in enumerate(self.bricks):
            btn.configure(text=opts[i].upper(), state="normal", fg_color="#8B4513")
            
        self.after(500, self.play_audio)

    def play_audio(self):
        play_sound_system(self.current_word)

    def jump(self, idx):
        if self.bricks[idx].cget("text").lower() == self.correct_meaning.lower():
            # Nhảy đúng
            self.score += 1
            self.lbl_score.configure(text=f"Điểm: {self.score}")
            data_manager.update_progress(self.current_word, 'vocab')
            self.bricks[idx].configure(fg_color="#32CD32") # Gạch sáng xanh lên
            self.lbl_ninja.configure(text="✨🥷✨") # Hiệu ứng nhặt đồ
            self.after(800, self.next_round)
        else:
            # Nhảy sai (Rơi xuống)
            self.bricks[idx].configure(fg_color="#FF0000", text="VỠ 💥") 
            self.lbl_ninja.configure(text="👻") 
            self.lbl_guide.configure(text=f"SAI RỒI! TỪ ĐÓ NGHĨA LÀ: {self.correct_meaning.upper()}", text_color="white", fg_color="red")
            for b in self.bricks: b.configure(state="disabled")
            update_home_screen()
class ScrambleGameWindow(BaseGameWindow):
    def __init__(self, master, num, data):
        super().__init__(master, "Game Đảo Chữ")
        self.game_data = data
        self.prepare(num)
        self.build()
        self.load()

    def prepare(self, num):
        for item in random.sample(self.game_data, min(num, len(self.game_data))): 
            self.questions.append((item['word'], item['vn_meaning'], item['item_type']))

    def build(self):
        self.lbl_vn = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 20, "bold"), text_color=TEXT_SUB, wraplength=600)
        self.lbl_vn.pack(pady=(30, 10))
        
        self.lbl_scr = ctk.CTkLabel(self.game_area, text="", font=("Courier New", 42, "bold"), text_color=COLOR_ACCENT, wraplength=600)
        self.lbl_scr.pack(pady=(10, 30))
        
        self.entry = ctk.CTkEntry(self.game_area, font=("Segoe UI", 24, "bold"), justify="center", height=60, corner_radius=12, border_color=BORDER_COLOR)
        self.entry.pack(fill="x", padx=60, pady=10)
        self.entry.bind('<Return>', lambda e: self.check())
        
        bf = ctk.CTkFrame(self.game_area, fg_color="transparent")
        bf.pack(pady=20, fill="x", padx=60)
        ctk.CTkButton(bf, text="🔊 Nghe gợi ý", width=140, height=45, corner_radius=10, border_width=1, border_color=BORDER_COLOR, fg_color=BG_MAIN, text_color=("black", "white"), hover_color=HOVER_COLOR_TRANSPARENT, command=lambda: play_sound_system(self.questions[self.current_idx][0])).pack(side="left")
        ctk.CTkButton(bf, text="Kiểm tra", width=140, height=45, corner_radius=10, font=("Segoe UI", 15, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.check).pack(side="right")

    def load(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.questions):
            messagebox.showinfo("Kết thúc", f"Bạn gõ đúng {self.score}/{len(self.questions)} từ.")
            refresh_lists()
            self.destroy()
            return
            
        word, vn, _ = self.questions[self.current_idx]
        self.lbl_progress_text.configure(text=f"Câu {self.current_idx+1}/{len(self.questions)}")
        self.progress_bar.set((self.current_idx) / len(self.questions))
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        self.lbl_vn.configure(text=vn.capitalize())
        
        scr = []
        for w in word.split():
            chars = list(w)
            random.shuffle(chars)
            attempts = 0 # Tránh lặp vô hạn nếu từ có các chữ giống nhau (vd: "eee")
            while ''.join(chars) == w and len(w) > 2 and attempts < 10: 
                random.shuffle(chars)
                attempts += 1
            scr.append(' '.join(chars).upper())
            
        self.lbl_scr.configure(text="   ".join(scr))
        self.entry.delete(0, 'end')
        self.entry.focus()

    def check(self):
        cw, _, ty = self.questions[self.current_idx]
        if self.entry.get().strip().lower() == cw: 
            data_manager.update_progress(cw, ty)
            self.score += 1
            play_sound_system(cw)
        else: 
            messagebox.showerror("Sai rồi", f"Chính tả đúng phải là:\n{cw.upper()}")
        self.current_idx += 1
        self.load()

class DictationGameWindow(BaseGameWindow):
    def __init__(self, master, num, data):
        super().__init__(master, "Game Nghe & Gõ")
        self.game_data = data
        self.prepare(num)
        self.build()
        self.load()

    def prepare(self, num):
        for item in random.sample(self.game_data, min(num, len(self.game_data))): 
            self.questions.append((item['word'], item['vn_meaning'], item['item_type']))

    def build(self):
        btn_play = ctk.CTkButton(self.game_area, text="▶ NGHE TỪ VỰNG", font=("Segoe UI", 24, "bold"), height=90, width=300, corner_radius=20, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=lambda: play_sound_system(self.questions[self.current_idx][0]))
        btn_play.pack(pady=(40, 20))
        
        self.lbl_hint = ctk.CTkLabel(self.game_area, text="---", font=("Segoe UI", 16, "italic"), text_color=TEXT_SUB, wraplength=500)
        self.lbl_hint.pack(pady=(0, 20))
        
        self.entry = ctk.CTkEntry(self.game_area, font=("Segoe UI", 24, "bold"), justify="center", height=60, corner_radius=12, border_color=BORDER_COLOR)
        self.entry.pack(fill="x", padx=60, pady=10)
        self.entry.bind('<Return>', lambda e: self.check())
        
        bf = ctk.CTkFrame(self.game_area, fg_color="transparent")
        bf.pack(pady=20, fill="x", padx=60)
        ctk.CTkButton(bf, text="💡 Gợi ý nghĩa", width=140, height=45, corner_radius=10, border_width=1, border_color=BORDER_COLOR, fg_color=BG_MAIN, text_color=("black", "white"), hover_color=HOVER_COLOR_TRANSPARENT, command=lambda: self.lbl_hint.configure(text=f"Nghĩa: {self.questions[self.current_idx][1].capitalize()}")).pack(side="left")
        ctk.CTkButton(bf, text="Kiểm tra", width=140, height=45, corner_radius=10, font=("Segoe UI", 15, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.check).pack(side="right")

    def load(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.questions):
            messagebox.showinfo("Kết thúc", f"Bạn nghe gõ đúng {self.score}/{len(self.questions)} từ.")
            refresh_lists()
            self.destroy()
            return
            
        self.lbl_progress_text.configure(text=f"Câu {self.current_idx+1}/{len(self.questions)}")
        self.progress_bar.set((self.current_idx) / len(self.questions))
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        self.lbl_hint.configure(text="---")
        self.entry.delete(0, 'end')
        self.entry.focus()
        play_sound_system(self.questions[self.current_idx][0])

    def check(self):
        cw, _, ty = self.questions[self.current_idx]
        if self.entry.get().strip().lower() == cw: 
            data_manager.update_progress(cw, ty)
            self.score += 1
            play_sound_system(cw)
        else: 
            messagebox.showerror("Sai rồi", f"Từ đúng phải là:\n{cw.upper()}")
        self.current_idx += 1
        self.load()

class MemoryCardGameWindow(ctk.CTkToplevel):
    def __init__(self, master, num, data):
        super().__init__(master)
        self.title("Game Lật Thẻ Bài (Memory Card)")
        self.geometry("900x700")
        self.transient(master)
        self.grab_set()
        
        self.score = 0
        self.num_pairs = min(num, 8) # Tối đa hiển thị lưới 4x4
        selected_data = random.sample(data, min(self.num_pairs, len(data)))
        self.pairs = [(i['word'], i['vn_meaning'], i['item_type']) for i in selected_data]
        self.num_pairs = len(self.pairs)
        
        self.cards = []
        for w, v, ty in self.pairs:
            self.cards.append({'type': 'en', 'value': w, 'pair_word': w, 'item_type': ty, 'id': f"en_{w}"})
            self.cards.append({'type': 'vi', 'value': v, 'pair_word': w, 'item_type': ty, 'id': f"vi_{v}"})
            
        random.shuffle(self.cards)
        
        self.buttons = []
        self.flipped = []
        self.matched = 0
        self.is_animating = False
        
        self.build()

    def build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(20, 0))
        ctk.CTkLabel(top, text="🃏 Lật Thẻ Bài - Tìm cặp Từ & Nghĩa", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(side="left")
        self.lbl_score = ctk.CTkLabel(top, text=f"Đã lật được: 0/{self.num_pairs}", font=("Segoe UI", 18, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_score.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self, height=8, progress_color=COLOR_ACCENT)
        self.progress_bar.pack(fill="x", padx=30, pady=(15, 0))
        self.progress_bar.set(0)

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=30, pady=20)
        
        cols = 4
        rows = (len(self.cards) + cols - 1) // cols
        
        for i in range(cols):
            self.grid_frame.grid_columnconfigure(i, weight=1)
        for i in range(rows):
            self.grid_frame.grid_rowconfigure(i, weight=1)
            
        for i, card in enumerate(self.cards):
            btn = ctk.CTkButton(self.grid_frame, text="❓", font=("Segoe UI", 24, "bold"), border_width=1, border_color=BORDER_COLOR,
                                fg_color=BG_CARD, text_color=COLOR_ACCENT, corner_radius=16, hover_color=HOVER_COLOR_CARD,
                                command=lambda idx=i: self.flip_card(idx))
            btn.grid(row=i//cols, column=i%cols, padx=10, pady=10, sticky="nsew")
            self.buttons.append(btn)

    def animate_flip(self, idx, direction="out", step=0, callback=None):
        if not self.winfo_exists(): return
        # Thuật toán thu nhỏ dần text để mô phỏng 3D Flip
        fonts = [20, 15, 10, 5, 1] if direction == "out" else [1, 5, 10, 15, 20]
        if step < len(fonts):
            self.buttons[idx].configure(font=("Segoe UI", fonts[step], "bold"))
            self.after(20, lambda: self.animate_flip(idx, direction, step+1, callback))
        else:
            if callback: callback()

    def flip_card(self, idx):
        if self.is_animating: return
        if idx in self.flipped: return
        if self.buttons[idx].cget("state") == "disabled": return
        
        self.flipped.append(idx)
        if len(self.flipped) == 2:
            self.is_animating = True

        self.animate_flip(idx, direction="out", callback=lambda: self.on_flipped(idx))

    def on_flipped(self, idx):
        if not self.winfo_exists(): return
        card = self.cards[idx]
        if card['type'] == 'en':
            self.buttons[idx].configure(text=card['value'].capitalize(), fg_color=COLOR_ACCENT, text_color="white")
            play_sound_system(card['value'])
        else:
            self.buttons[idx].configure(text=card['value'].capitalize(), fg_color=COLOR_SUCCESS[0], text_color="white")
            
        self.animate_flip(idx, direction="in", callback=lambda: self.check_match() if len(self.flipped) == 2 and self.flipped[-1] == idx else None)

    def flip_back(self, idx1, idx2):
        if not self.winfo_exists(): return
        # Hiệu ứng rung nhẹ bằng cách chớp màu đỏ
        self.buttons[idx1].configure(text_color=COLOR_DANGER[0])
        self.buttons[idx2].configure(text_color=COLOR_DANGER[0])
        self.after(400, lambda: self._do_flip_back(idx1, idx2))
        
    def _do_flip_back(self, idx1, idx2):
        if not self.winfo_exists(): return
        self.animate_flip(idx1, direction="out", callback=lambda: self.restore_card(idx1))
        self.animate_flip(idx2, direction="out", callback=lambda: self.restore_card(idx2))

    def restore_card(self, idx):
        if not self.winfo_exists(): return
        self.buttons[idx].configure(text="❓", fg_color=BG_CARD, text_color=COLOR_ACCENT)
        self.animate_flip(idx, direction="in", callback=lambda: self.on_restore_done())

    def on_restore_done(self):
        if not hasattr(self, 'restore_count'): self.restore_count = 0
        self.restore_count += 1
        if self.restore_count == 2:
            self.restore_count = 0
            self.flipped = []
            self.is_animating = False

    def check_match(self):
        if not self.winfo_exists(): return
        idx1, idx2 = self.flipped
        card1, card2 = self.cards[idx1], self.cards[idx2]
        
        if card1['pair_word'] == card2['pair_word'] and card1['type'] != card2['type']:
            self.buttons[idx1].configure(state="disabled", fg_color="transparent", text_color=COLOR_SUCCESS[0], border_width=2, border_color=COLOR_SUCCESS[0])
            self.buttons[idx2].configure(state="disabled", fg_color="transparent", text_color=COLOR_SUCCESS[0], border_width=2, border_color=COLOR_SUCCESS[0])
            self.matched += 1
            self.lbl_score.configure(text=f"Đã lật được: {self.matched}/{self.num_pairs}")
            self.progress_bar.set(self.matched / self.num_pairs)
            data_manager.update_progress(card1['pair_word'], card1['item_type'])
            
            self.flipped = []
            self.is_animating = False

            if self.matched == self.num_pairs:
                self.after(500, lambda: messagebox.showinfo("Hoàn thành", "Chúc mừng! Bạn đã lật đúng tất cả các thẻ!"))
                self.after(500, refresh_lists)
                self.after(500, self.destroy)
        else:
            self.after(600, lambda: self.flip_back(idx1, idx2))

class MatchGameWindow(ctk.CTkToplevel):
    def __init__(self, master, num, data):
        super().__init__(master)
        self.title("Game Nối Từ")
        self.geometry("850x650")
        self.transient(master)
        self.grab_set()
        self.score = 0
        self.sel_en = self.sel_vi = None
        self.game_data = data
        self.pairs = [(i['word'], i['vn_meaning'], i['item_type']) for i in random.sample(data, min(num, min(10, len(data))))]
        self.btn_en = {}
        self.btn_vi = {}
        self.build()

    def build(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(20, 0))
        ctk.CTkLabel(top, text="🔗 Ghép từ tiếng Anh với nghĩa tiếng Việt", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(side="left")
        self.lbl_score = ctk.CTkLabel(top, text=f"Điểm: 0/{len(self.pairs)}", font=("Segoe UI", 18, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_score.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(self, height=8, progress_color=COLOR_ACCENT)
        self.progress_bar.pack(fill="x", padx=30, pady=(15, 0))
        self.progress_bar.set(0)

        gf = ctk.CTkFrame(self, fg_color="transparent")
        gf.pack(fill="both", expand=True, padx=30, pady=20)
        gf.grid_columnconfigure(0, weight=1)
        gf.grid_columnconfigure(1, weight=1)
        
        el, vl = list(self.pairs), list(self.pairs)
        random.shuffle(el)
        random.shuffle(vl)
        
        fe = ctk.CTkFrame(gf, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        fe.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        fv = ctk.CTkFrame(gf, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        fv.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        for w, _, _ in el:
            b = ctk.CTkButton(fe, text=w.capitalize(), height=55, corner_radius=12, font=("Segoe UI", 16, "bold"), fg_color=BG_MAIN, text_color=("black", "white"), border_width=1, border_color=BORDER_COLOR, hover_color=COLOR_ACCENT_HOVER, command=lambda w=w: self.sel(w, 'en'))
            b.pack(fill="x", padx=15, pady=8)
            self.btn_en[w] = b
            
        for _, v, _ in vl:
            b = ctk.CTkButton(fv, text=v.capitalize(), height=55, corner_radius=12, font=("Segoe UI", 16, "bold"), fg_color=BG_MAIN, text_color=("black", "white"), border_width=1, border_color=BORDER_COLOR, hover_color="#28a745", command=lambda v=v: self.sel(v, 'vi'))
            b.pack(fill="x", padx=15, pady=8)
            self.btn_vi[v] = b

    def sel(self, val, lang):
        if lang == 'en':
            for b in self.btn_en.values(): b.configure(border_width=0)
            self.sel_en = val
            self.btn_en[val].configure(border_width=2, border_color=COLOR_ACCENT)
        else:
            for b in self.btn_vi.values(): b.configure(border_width=0)
            self.sel_vi = val
            self.btn_vi[val].configure(border_width=2, border_color=COLOR_SUCCESS[0])
            
        if self.sel_en and self.sel_vi:
            pair = next((p for p in self.pairs if p[0] == self.sel_en and p[1] == self.sel_vi), None)
            if pair:
                play_sound_system(pair[0])
                data_manager.update_progress(pair[0], pair[2])
                self.btn_en[pair[0]].destroy()
                self.btn_vi[pair[1]].destroy()
                del self.btn_en[pair[0]]
                del self.btn_vi[pair[1]]
                self.score += 1
                self.lbl_score.configure(text=f"Điểm: {self.score}/{len(self.pairs)}")
                
                if self.score == len(self.pairs): 
                    messagebox.showinfo("Hoàn thành", "Chúc mừng! Bạn đã nối đúng tất cả!")
                    refresh_lists()
                    self.destroy()
            else:
                messagebox.showerror("Sai", "Hai thẻ này không khớp nhau!")
                
            self.sel_en = self.sel_vi = None
            for b in self.btn_en.values(): b.configure(border_width=0)
            for b in self.btn_vi.values(): b.configure(border_width=0)
# ================== BATCH ADD ==================
class BatchAddDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master); self.title("Thêm Hàng Loạt"); self.geometry("500x450"); self.transient(master); self.grab_set()
        ctk.CTkLabel(self, text="📝 THÊM TỪ VỰNG HÀNG LOẠT", font=("Segoe UI", 18, "bold"), text_color=COLOR_ACCENT).pack(pady=(20,5))
        ctk.CTkLabel(self, text="Ngăn cách nhau bằng dấu phẩy (,)", text_color=TEXT_SUB, font=("Segoe UI", 13)).pack(pady=(0,15))
        self.textbox = ctk.CTkTextbox(self, height=200, font=("Segoe UI", 15)); self.textbox.pack(fill="x", padx=25, pady=10)
        self.lbl_status = ctk.CTkLabel(self, text="Sẵn sàng...", text_color=COLOR_SUCCESS[0]); self.lbl_status.pack(pady=5)
        bf = ctk.CTkFrame(self, fg_color="transparent"); bf.pack(pady=10)
        ctk.CTkButton(bf, text="Hủy bỏ", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, command=self.destroy).pack(side="left", padx=10)
        self.btn_start = ctk.CTkButton(bf, text="Bắt đầu", width=140, command=self.start); self.btn_start.pack(side="right", padx=10)
    
    def start(self):
        content = self.textbox.get("1.0", "end").strip()
        if not content: return
        words = list(dict.fromkeys([w.strip().lower() for w in content.split(",") if w.strip()]))
        if not words: return
        self.btn_start.configure(state="disabled"); self.textbox.configure(state="disabled")
        threading.Thread(target=self.process_parallel, args=(words,), daemon=True).start()
    
    def process_parallel(self, words):
        total = len(words)
        def fetch_word(w):
            if w in data_manager.vocab or w in data_manager.phrase: return None
            is_single = len(w.split()) == 1
            ex, pos, vn = get_word_info(w) if is_single else get_phrase_info(w)
            return (w, 'vocab' if is_single else 'phrase', ex, pos, vn, "")
        
        futures = [executor.submit(fetch_word, w) for w in words]
        results = []
        for i, future in enumerate(futures):
            app.after(0, lambda idx=i: self.lbl_status.configure(text=f"⏳ Đang gọi dữ liệu API song song ({idx+1}/{total})..."))
            res = future.result()
            if res: results.append(res)
            
        if results:
            app.after(0, lambda: self.lbl_status.configure(text=f"⏳ Đang cập nhật hệ thống..."))
            for r in results: data_manager.add_or_update(r[0], r[1], r[2], r[3], r[4], r[5], sync_db=False)
            
            def save_batch(batch):
                with DB_LOCK:
                    conn = sqlite3.connect(DB_PATH)
                    conn.execute("BEGIN TRANSACTION")
                    for r in batch:
                        conn.execute(f"INSERT INTO {r[1]} (word, sentence, pos, vn_meaning, custom_sentence, last_studied, study_count, is_mastered) VALUES (?,?,?,?,?,?,?,?)",
                                     (r[0], r[2], r[3], r[4], r[5], "", 0, 0))
                    conn.commit()
                    conn.close()
            executor.submit(save_batch, results)
                
        app.after(0, lambda: self.finish(len(results)))
        
    def finish(self, added):
        if added == 0: self.lbl_status.configure(text="Tất cả từ đã có sẵn!", text_color="gray")
        else: self.lbl_status.configure(text=f"✅ Hoàn tất! Đã thêm cực nhanh {added} mục.", text_color=COLOR_SUCCESS[0])
        self.btn_start.configure(text="Đóng", state="normal", command=self.destroy)
        refresh_lists()

# ================== CÔNG CỤ DỮ LIỆU (TẢI VÍ DỤ, V.V...) ==================
class DataToolsDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Công cụ Dữ liệu")
        self.geometry("450x300")
        self.transient(master)
        self.grab_set()

        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(card, text="🛠 CÔNG CỤ DỮ LIỆU", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(pady=(20, 10))

        self.lbl_status = ctk.CTkLabel(card, text="Sẵn sàng kiểm tra dữ liệu.", text_color=TEXT_SUB, font=FONT_BODY)
        self.lbl_status.pack(pady=10)

        self.btn_examples = ctk.CTkButton(card, text="📝 Tải ví dụ bị thiếu", height=40, font=("Segoe UI", 15, "bold"), command=self.fetch_missing_examples)
        self.btn_examples.pack(pady=15)

        ctk.CTkButton(card, text="Đóng", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, text_color=TEXT_SUB, command=self.destroy).pack(pady=10)

    def fetch_missing_examples(self):
        self.btn_examples.configure(state="disabled")
        self.lbl_status.configure(text="Đang quét dữ liệu...", text_color=COLOR_WARNING[0])

        def task():
            missing = []
            for w, d in data_manager.vocab.items():
                if not d.get('sentence') or "Chưa có ví dụ" in d.get('sentence') or "Hãy tự đặt" in d.get('sentence'):
                    missing.append((w, 'vocab'))
            for w, d in data_manager.phrase.items():
                if not d.get('sentence') or "Chưa có ví dụ" in d.get('sentence') or "Hãy tự đặt" in d.get('sentence'):
                    missing.append((w, 'phrase'))

            if not missing:
                app.after(0, lambda: self.lbl_status.configure(text="Tất cả từ đều đã có ví dụ!", text_color=COLOR_SUCCESS[0]))
                app.after(0, lambda: self.btn_examples.configure(state="normal"))
                return

            app.after(0, lambda: self.lbl_status.configure(text=f"Tìm thấy {len(missing)} từ thiếu ví dụ. Đang tải..."))
            success_count = 0

            for w, ty in missing:
                if not self.winfo_exists(): return
                try:
                    res = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=5)
                    if res.status_code == 200:
                        d = res.json()[0]
                        example = None
                        for m in d['meanings']:
                            for df in m['definitions']:
                                if 'example' in df:
                                    example = df['example']
                                    break
                            if example: break
                        if example:
                            data_manager.update_field(w, ty, 'sentence', example)
                            success_count += 1
                except: pass

            app.after(0, lambda: self.lbl_status.configure(text=f"Hoàn tất! Đã thêm {success_count}/{len(missing)} ví dụ.", text_color=COLOR_SUCCESS[0]))
            app.after(0, lambda: self.btn_examples.configure(state="normal"))

        threading.Thread(target=task, daemon=True).start()

# ================== TẢI TRƯỚC ẢNH HÀNG LOẠT (PRELOADER) ==================
class ImagePreloaderDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Tải Trước Hình Ảnh Hàng Loạt")
        self.geometry("500x350")
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.is_running = False
        self.words_to_download = []
        self.downloaded_count = 0
        self.failed_count = 0
        self.total_count = 0
        
        self.build_ui()
        self.prepare_data()
        
    def build_ui(self):
        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.lbl_title = ctk.CTkLabel(card, text="🖼 TẢI TRƯỚC HÌNH ẢNH", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT)
        self.lbl_title.pack(pady=(20, 10))
        
        self.lbl_status = ctk.CTkLabel(card, text="Đang quét bộ nhớ đệm...", font=("Segoe UI", 15), text_color=TEXT_SUB)
        self.lbl_status.pack(pady=5)
        
        self.progress_bar = ctk.CTkProgressBar(card, height=12, progress_color=COLOR_SUCCESS[0])
        self.progress_bar.pack(fill="x", padx=40, pady=20)
        self.progress_bar.set(0)
        
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(pady=(10, 20), fill="x", padx=40)
        ctk.CTkButton(bf, text="Hủy", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, command=self.on_close).pack(side="left")
        self.btn_start = ctk.CTkButton(bf, text="Bắt Đầu Tải", width=120, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.start_download, state="disabled")
        self.btn_start.pack(side="right")
        
    def prepare_data(self):
        def task():
            all_words = list(data_manager.vocab.keys()) + list(data_manager.phrase.keys())
            missing = []
            for w in all_words:
                cache_path = os.path.join(CACHE_DIR, f"{hashlib.md5(w.encode()).hexdigest()}.jpg")
                # Chỉ tải nếu file không tồn tại hoặc file bị rỗng (dung lượng = 0)
                if not os.path.exists(cache_path) or os.path.getsize(cache_path) == 0:
                    missing.append(w)
            
            self.words_to_download = missing
            self.total_count = len(missing)
            
            def update_ui():
                if not self.winfo_exists(): return
                if self.total_count == 0:
                    self.lbl_status.configure(text="Tất cả từ vựng đã có ảnh!", text_color=COLOR_SUCCESS[0])
                    self.btn_start.configure(text="Đóng", state="normal", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.destroy)
                    self.progress_bar.set(1.0)
                else:
                    self.lbl_status.configure(text=f"Tìm thấy {self.total_count} từ chưa có ảnh.")
                    self.btn_start.configure(state="normal")
            
            app.after(0, update_ui)
            
        threading.Thread(target=task, daemon=True).start()
        
    def start_download(self):
        self.is_running = True
        self.btn_start.configure(state="disabled", text="Đang tải...")
        
        # Sử dụng 8 luồng song song (nhanh nhưng vẫn an toàn để không bị máy chủ chặn)
        self.dl_executor = ThreadPoolExecutor(max_workers=8)
        
        def download_worker(word):
            if not self.is_running: return
            
            cache_path = os.path.join(CACHE_DIR, f"{hashlib.md5(word.encode()).hexdigest()}.jpg")
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            safe_word = word.replace(' ', '+')
            image_sources = [
                f"https://tse2.mm.bing.net/th?q={safe_word}+png+isolated&w=400&h=400&c=7&rs=1",
                f"https://image.pollinations.ai/prompt/a+simple+illustration+of+{safe_word}?width=400&height=400&nologo=true"
            ]
            
            success = False
            for url in image_sources:
                try:
                    res = requests.get(url, headers=headers, timeout=5)
                    if res.status_code == 200 and 'image' in res.headers.get('Content-Type', '').lower():
                        with open(cache_path, "wb") as f: f.write(res.content)
                        try: Image.open(cache_path).verify(); success = True; break
                        except Exception: os.remove(cache_path)
                except: continue
                    
            if success: self.downloaded_count += 1
            else: self.failed_count += 1
                
            def update_progress():
                if not self.winfo_exists(): return
                done = self.downloaded_count + self.failed_count
                self.progress_bar.set(done / self.total_count)
                self.lbl_status.configure(text=f"Đã tải: {self.downloaded_count} | Lỗi: {self.failed_count} | Còn lại: {self.total_count - done}")
                
                if done >= self.total_count:
                    self.is_running = False
                    self.lbl_status.configure(text=f"Hoàn tất! Đã tải mới {self.downloaded_count} ảnh.", text_color=COLOR_SUCCESS[0])
                    self.btn_start.configure(text="Đóng", state="normal", fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=self.destroy)
            app.after(0, update_progress)
            
        for w in self.words_to_download: self.dl_executor.submit(download_worker, w)

    def on_close(self):
        self.is_running = False
        if hasattr(self, 'dl_executor'):
            try: self.dl_executor.shutdown(wait=False, cancel_futures=True)
            except: pass
        self.destroy()

# ================== HỆ THỐNG NHẮC NHỞ (REMINDER) ==================
class ReminderSetupDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Cài đặt Nhắc Nhở")
        self.geometry("450x420")
        self.transient(master)
        self.grab_set()
        
        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(card, text="⏰ HẸN GIỜ HỌC TẬP", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 10))
        
        self.enabled_var = ctk.StringVar(value=data_manager.get_setting("reminder_enabled", "0"))
        self.switch = ctk.CTkSwitch(card, text="Bật nhắc nhở thông báo trên màn hình", variable=self.enabled_var, onvalue="1", offvalue="0", font=FONT_BODY)
        self.switch.pack(pady=15)
        
        time_frame = ctk.CTkFrame(card, fg_color="transparent")
        time_frame.pack(pady=10)
        
        ctk.CTkLabel(time_frame, text="Thời gian:", font=FONT_BODY).pack(side="left", padx=10)
        
        saved_time = data_manager.get_setting("reminder_time", "20:00").split(":")
        self.hour_var = ctk.StringVar(value=saved_time[0] if len(saved_time)==2 else "20")
        self.minute_var = ctk.StringVar(value=saved_time[1] if len(saved_time)==2 else "00")
        
        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(60)]
        
        ctk.CTkOptionMenu(time_frame, values=hours, variable=self.hour_var, width=70).pack(side="left", padx=5)
        ctk.CTkLabel(time_frame, text=":", font=("Segoe UI", 16, "bold")).pack(side="left")
        ctk.CTkOptionMenu(time_frame, values=minutes, variable=self.minute_var, width=70).pack(side="left", padx=5)
        
        ctk.CTkButton(card, text="📅 Thêm vào Google Calendar", fg_color="#4285F4", hover_color="#3367D6", font=("Segoe UI", 14, "bold"), command=self.add_gcal).pack(pady=20)
        
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(pady=(10, 20), fill="x", padx=30)
        ctk.CTkButton(bf, text="Hủy", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, command=self.destroy).pack(side="left")
        ctk.CTkButton(bf, text="Lưu Cài Đặt", width=100, fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.save).pack(side="right")
        
    def add_gcal(self):
        # Tạo đường link add sự kiện lặp lại hằng ngày cực xịn
        url = "https://calendar.google.com/calendar/render?action=TEMPLATE&text=H%E1%BB%8Dc+T%E1%BB%AB+V%E1%BB%B1ng+(Vocab+Master)&details=%C4%90%C3%A3+%C4%91%E1%BA%BFn+l%C3%BAc+m%E1%BB%9F+app+Vocab+Master+Premium+%C4%91%E1%BB%83+t%C6%B0%E1%BB%9Bi+c%C3%A2y+t%E1%BB%AB+v%E1%BB%B1ng+r%E1%BB%93i!&recur=RRULE:FREQ=DAILY"
        webbrowser.open(url)
        
    def save(self):
        data_manager.set_setting("reminder_enabled", self.enabled_var.get())
        data_manager.set_setting("reminder_time", f"{self.hour_var.get()}:{self.minute_var.get()}")
        messagebox.showinfo("Thành công", "Đã lưu cài đặt nhắc nhở!")
        self.destroy()

LAST_REMINDED_DATE = ""
def show_toast_notification():
    toast = ctk.CTkToplevel(app)
    toast.title("Nhắc nhở")
    toast.overrideredirect(True) # Ẩn viền cửa sổ
    toast.attributes("-topmost", True)
    
    window_w, window_h = 320, 110
    x = toast.winfo_screenwidth() - window_w - 20
    y = toast.winfo_screenheight() - window_h - 60 # Hiển thị ngay trên thanh Taskbar
    toast.geometry(f"{window_w}x{window_h}+{x}+{y}")
    
    frame = ctk.CTkFrame(toast, corner_radius=16, border_width=2, border_color=COLOR_ACCENT, fg_color=BG_CARD)
    frame.pack(fill="both", expand=True)
    
    ctk.CTkLabel(frame, text="⏰ ĐẾN GIỜ HỌC RỒI!", font=("Segoe UI", 16, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 5))
    ctk.CTkLabel(frame, text="Vào app Vocab Master tưới cây thôi 🌱", font=FONT_BODY).pack()
    
    try:
        import winsound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except: pass
        
    frame.bind("<Button-1>", lambda e: toast.destroy())
    for child in frame.winfo_children(): child.bind("<Button-1>", lambda e: toast.destroy())
    toast.after(10000, toast.destroy) # Tự biến mất sau 10s

# ================== STATISTICS (TÍNH TOÁN TRỰC TIẾP TRÊN RAM SIÊU TỐC) ==================
class StatisticsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Thống Kê Học Tập")
        self.geometry("750x720")
        self.transient(master)
        
        # Đảm bảo cửa sổ luôn ở trên và nhận focus
        self.grab_set()
        self.focus_force()
        self.last_w, self.last_h = 0, 0

        self.build_ui()

    def get_stats_from_ram(self):
        """Thuật toán đếm số liệu trực tiếp từ RAM, không đụng tới SQLite giúp tốc độ tức thời"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        total_vocab = len(data_manager.vocab)
        total_phrase = len(data_manager.phrase)
        
        # Lấy số từ đã học hôm nay từ tracker trên RAM
        studied_today = len(data_manager.tracker.get(today, set()))

        mastered, warned, unlearned = 0, 0, 0

        # Quét qua toàn bộ từ vựng và cụm từ (Chỉ tốn ~0.001s cho 10.000 từ)
        for collection in (data_manager.vocab.values(), data_manager.phrase.values()):
            for item in collection:
                c = item.get('study_count', 0)
                is_mastered = item.get('is_mastered', 0)
                
                if c == 0 and not is_mastered:
                    unlearned += 1
                
                if is_mastered or c >= 15:
                    mastered += 1

                # Tính cảnh báo (học >= 10 lần nhưng đã bỏ bê 3 ngày)
                if c >= 10 and item.get('last_studied') and not is_mastered:
                    try:
                        # Chỉ lấy 10 ký tự đầu (YYYY-MM-DD) để so sánh ngày cho chuẩn xác
                        last_date = datetime.strptime(item['last_studied'][:10], "%Y-%m-%d")
                        if (datetime.now() - last_date).days >= 3:
                            warned += 1
                    except:
                        pass

        return total_vocab, total_phrase, studied_today, mastered, warned, unlearned
        total_mins = int(data_manager.get_setting("total_study_minutes", "0"))
        hours = total_mins // 60
        mins = total_mins % 60
        st_time_str = f"{hours}h {mins}p" if hours > 0 else f"{mins} phút"

        return total_vocab, total_phrase, studied_today, mastered, warned, unlearned, st_time_str

    def build_ui(self):
        ctk.CTkLabel(self, text="📊 TỔNG QUAN HỌC TẬP", font=("Segoe UI", 26, "bold"), text_color=COLOR_ACCENT).pack(pady=(30, 20))
        
        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.pack(fill="x", padx=30, pady=10)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        
        # Lấy dữ liệu ngay lập tức
        tv, tp, st, m, w, u = self.get_stats_from_ram()
        tv, tp, st, m, w, u, st_time_str = self.get_stats_from_ram()

        def create_card(row, col, title, value, color):
            if not title:
                ctk.CTkFrame(grid_frame, fg_color="transparent").grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
                return
            card = ctk.CTkFrame(grid_frame, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
            card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 15), text_color=TEXT_SUB).pack(pady=(25, 5))
            ctk.CTkLabel(card, text=str(value), font=("Segoe UI", 48, "bold"), text_color=color).pack(pady=(0, 25))

        create_card(0, 0, "📚 Tổng Từ Đơn", tv, COLOR_ACCENT)
        create_card(0, 1, "💬 Tổng Cụm Từ", tp, COLOR_ACCENT)
        create_card(1, 0, "🔥 Đã học hôm nay", st, COLOR_SUCCESS[0])
        create_card(1, 1, "✅ Đã thuộc/Trên 15 lần", m, COLOR_SUCCESS[0])
        create_card(2, 0, "🚨 Cảnh báo (Lâu chưa ôn)", w, COLOR_DANGER[0])
        create_card(2, 1, "🆕 Chưa học (0 lần)", u, "gray")
        create_card(2, 1, "⏳ Thời Gian Tập Trung", st_time_str, COLOR_WARNING[0])
        create_card(3, 0, "🆕 Chưa học (0 lần)", u, "gray")
        create_card(3, 1, "", "", "") # Tạo layout rỗng lấp đầy grid

        # --- BIỂU ĐỒ ĐƯỜNG (LINE CHART) TỰ ĐỘNG ---
        chart_frame = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        chart_frame.pack(fill="both", expand=True, padx=30, pady=(10, 20))
        
        ctk.CTkLabel(chart_frame, text="📈 Tiến trình học 7 ngày qua", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=20, pady=(15, 0))
        
        bg_hex = BG_CARD[1] if ctk.get_appearance_mode() == "Dark" else BG_CARD[0]
        self.canvas_chart = ctk.CTkCanvas(chart_frame, highlightthickness=0, bg=bg_hex)
        self.canvas_chart.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        self.canvas_chart.bind("<Configure>", self.on_resize)
        self.after(100, self.draw_chart)

    def on_resize(self, event):
        if event.width != self.last_w or event.height != self.last_h:
            self.last_w, self.last_h = event.width, event.height
            self.draw_chart()

    def draw_chart(self):
        if not self.winfo_exists(): return
        canvas = self.canvas_chart
        w, h = canvas.winfo_width(), canvas.winfo_height()
        if w < 50 or h < 50: return
            
        canvas.delete("all")
        bg_color = BG_CARD[1] if ctk.get_appearance_mode() == "Dark" else BG_CARD[0]
        canvas.configure(bg=bg_color)
        
        # Thu thập dữ liệu
        last_7_days = [(datetime.now() - timedelta(days=i)) for i in range(6, -1, -1)]
        counts = [len(data_manager.tracker.get(d.strftime("%Y-%m-%d"), set())) for d in last_7_days]
        max_val = max(counts) if max(counts) > 0 else 10
        
        pad_x, pad_y = 40, 30
        usable_w = w - 2 * pad_x
        usable_h = h - 2 * pad_y
        
        grid_color = "#3A3A45" if ctk.get_appearance_mode() == "Dark" else "#D1D8E5"
        text_color = TEXT_SUB[1] if ctk.get_appearance_mode() == "Dark" else TEXT_SUB[0]
        
        # Vẽ đường gióng ngang đứt khúc
        for i in range(4):
            y_line = h - pad_y - (i / 3) * usable_h
            canvas.create_line(pad_x, y_line, w - pad_x, y_line, fill=grid_color, dash=(4, 4))
            
        # Tính tọa độ
        points = []
        for i, count in enumerate(counts):
            x = pad_x + (i / 6) * usable_w
            y = h - pad_y - (count / max_val) * usable_h
            points.append((x, y))
            
        # Vẽ đường nối
        flat_coords = [coord for pt in points for coord in pt]
        if len(flat_coords) >= 4:
            canvas.create_line(*flat_coords, fill=COLOR_ACCENT, width=3)
        
        # Vẽ Điểm và Nhãn Text
        for i, (x, y) in enumerate(points):
            canvas.create_oval(x-6, y-6, x+6, y+6, fill=COLOR_SUCCESS[0], outline=bg_color, width=3)
            canvas.create_text(x, y-18, text=str(counts[i]), fill=text_color, font=("Segoe UI", 10, "bold"))
            canvas.create_text(x, h-10, text=last_7_days[i].strftime("%d/%m"), fill=text_color, font=("Segoe UI", 10))

# Biến toàn cục để tránh mở nhiều cửa sổ thống kê cùng lúc
stat_window_instance = None

def show_statistics():
    global stat_window_instance
    if stat_window_instance is None or not stat_window_instance.winfo_exists():
        stat_window_instance = StatisticsWindow(app)
    else:
        stat_window_instance.focus_force()
# ================== CHỨC NĂNG HỌC TỰ ĐỘNG (FLASHCARD) ==================

class AutoLearnSetupDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Cài đặt Học Tự Động")
        self.geometry("450x500") # Tăng chiều cao để chứa lựa chọn
        self.transient(master)
        self.grab_set()
        self.result_time = None
        self.result_data = None
        self.full_list = []
        
        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(card, text="▶ HỌC TỪ TỰ ĐỘNG", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 5))
        
        self.source_mode = ctk.CTkSegmentedButton(card, values=["Ngẫu nhiên", "Chưa ôn hôm nay"], font=FONT_BODY, command=lambda v: self.prepare_data())
        self.source_mode.set("Chưa ôn hôm nay")
        self.source_mode.pack(pady=10, fill="x", padx=40)
        
        self.chk_include_mastered_var = ctk.IntVar(value=0)
        self.chk_include_mastered = ctk.CTkCheckBox(card, text="Bao gồm cả từ đã thuộc", variable=self.chk_include_mastered_var, command=self.prepare_data)
        self.chk_include_mastered.pack(pady=5)
        
        self.lbl_alert = ctk.CTkLabel(card, text="", text_color=COLOR_SUCCESS[0], font=("Segoe UI", 12, "italic"))
        self.lbl_alert.pack(pady=(0, 5))
        
        # --- 1. CHỌN SỐ LƯỢNG TỪ ---
        ctk.CTkLabel(card, text="Số lượng từ muốn học:", font=("Segoe UI", 14), text_color=TEXT_SUB).pack()
        self.lbl_word_count = ctk.CTkLabel(card, text="10 Từ", font=("Segoe UI", 24, "bold"), text_color=COLOR_ACCENT)
        self.lbl_word_count.pack()
        
        self.slider_words = ctk.CTkSlider(card, from_=1, to=10, command=lambda v: self.lbl_word_count.configure(text=f"{int(v)} Từ"))
        self.slider_words.pack(fill="x", padx=40, pady=(5, 10))
        
        # --- 2. CHỌN THỜI GIAN ---
        ctk.CTkLabel(card, text="Thời gian chuyển từ:", font=("Segoe UI", 14), text_color=TEXT_SUB).pack()
        self.lbl_time = ctk.CTkLabel(card, text="5 Giây", font=("Segoe UI", 24, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_time.pack()
        
        self.slider_time = ctk.CTkSlider(card, from_=3, to=15, number_of_steps=12, command=lambda v: self.lbl_time.configure(text=f"{int(v)} Giây"))
        self.slider_time.pack(fill="x", padx=40, pady=(5, 15))
        self.slider_time.set(5)
        
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(pady=(10, 20), fill="x", padx=30)
        ctk.CTkButton(bf, text="Hủy", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, command=self.destroy).pack(side="left")
        self.btn_start = ctk.CTkButton(bf, text="Bắt đầu", width=100, fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.on_start)
        self.btn_start.pack(side="right")
        
        self.prepare_data()
        self.wait_window()
        
    def prepare_data(self):
        data = get_game_data(self.source_mode.get(), self.chk_include_mastered_var.get())
        
        if not data:
            self.lbl_alert.configure(text="🎉 Bạn không có từ nào trong mục này.", text_color=COLOR_DANGER[0])
            self.slider_words.configure(state="disabled")
            self.slider_time.configure(state="disabled")
            self.btn_start.configure(state="disabled")
            self.lbl_word_count.configure(text="0 Từ")
        else:
            self.full_list = data
            max_words = len(data)
            self.lbl_alert.configure(text=f"Có {max_words} từ đang chờ bạn học.", text_color=COLOR_SUCCESS[0])
            
            # Cấu hình thanh trượt số lượng từ dựa trên số từ thực tế chưa học
            self.slider_words.configure(state="normal", from_=1, to=max_words, number_of_steps=max_words-1 if max_words > 1 else 1)
            self.slider_time.configure(state="normal")
            self.btn_start.configure(state="normal")
            
            # Mặc định gợi ý học 10 từ (hoặc ít hơn nếu không đủ)
            default_val = min(10, max_words)
            self.slider_words.set(default_val)
            self.lbl_word_count.configure(text=f"{int(default_val)} Từ")

    def on_start(self):
        self.result_time = int(self.slider_time.get())
        num_words_to_learn = int(self.slider_words.get())
        
        # Cắt lấy đúng số lượng từ bạn đã chọn trên thanh trượt
        self.result_data = self.full_list[:num_words_to_learn]
        
        self.destroy()
class AutoLearnWindow(ctk.CTkToplevel):
    def __init__(self, master, time_per_word, data):
        super().__init__(master)
        self.title("Đang Học Tự Động")
        self.geometry("750x550")
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.time_per_word = time_per_word
        self.data = data
        self.current_idx = 0
        
        self.is_paused = False
        self.time_left = float(time_per_word)
        self.timer_id = None
        
        self.build_ui()
        self.load_word()

    def build_ui(self):
        # Thanh tiến độ tổng
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=30, pady=(20, 10))
        self.lbl_progress = ctk.CTkLabel(self.top_frame, text="Từ 1/10", font=("Segoe UI", 16, "bold"), text_color=TEXT_SUB)
        self.lbl_progress.pack(side="left")
        
        # Vùng hiển thị từ
        self.card = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        self.card.pack(fill="both", expand=True, padx=30, pady=10)
        
        self.lbl_word = ctk.CTkLabel(self.card, text="word", font=("Segoe UI", 55, "bold"), text_color=COLOR_ACCENT)
        self.lbl_word.pack(pady=(40, 5))
        
        self.lbl_pos = ctk.CTkLabel(self.card, text="loại từ", font=("Segoe UI", 14), text_color="white", fg_color=COLOR_ACCENT, corner_radius=10)
        self.lbl_pos.pack(pady=5, ipadx=10, ipady=3)
        
        self.lbl_vn = ctk.CTkLabel(self.card, text="nghĩa tiếng việt", font=("Segoe UI", 24, "bold"), text_color=COLOR_SUCCESS[0], wraplength=600)
        self.lbl_vn.pack(pady=(15, 10))
        
        self.lbl_ex = ctk.CTkLabel(self.card, text="Ví dụ...", font=("Segoe UI", 16, "italic"), text_color=TEXT_SUB, wraplength=600)
        self.lbl_ex.pack(pady=10, padx=20)
        
        # Thanh đếm ngược thời gian
        self.time_bar = ctk.CTkProgressBar(self.card, height=10, progress_color=COLOR_SUCCESS[0])
        self.time_bar.pack(fill="x", padx=50, pady=(30, 20))
        
        # Cụm nút điều khiển
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(10, 20))
        
        ctk.CTkButton(btn_frame, text="⏪ Trước", width=100, height=40, font=("Segoe UI", 14), hover_color="#4A48C0", command=self.prev_word).pack(side="left", padx=10)
        self.btn_pause = ctk.CTkButton(btn_frame, text="⏸ Tạm Dừng", width=120, height=40, font=("Segoe UI", 14, "bold"), fg_color="#FF9500", hover_color="#E08300", command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=10)
        self.btn_mastered = ctk.CTkButton(btn_frame, text="✅ Đã thuộc (Space)", width=140, height=40, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.mark_mastered)
        self.btn_mastered.pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Tiếp ⏩", width=100, height=40, font=("Segoe UI", 14), hover_color="#4A48C0", command=self.next_word).pack(side="left", padx=10)

        self.bind("<space>", lambda e: self.mark_mastered())

    def mark_mastered(self):
        if not self.winfo_exists() or self.current_idx >= len(self.data): return
        item = self.data[self.current_idx]
        data_manager.update_field(item['word'], item['item_type'], 'is_mastered', 1)
        (scroll_vocab if item['item_type'] == 'vocab' else scroll_phrase).refresh_item(item['word'])
        self.lbl_word.configure(text=item['word'].capitalize() + " ✅")
        self.btn_mastered.configure(state="disabled", text="Đã đánh dấu")

    def load_word(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.data):
            messagebox.showinfo("Hoàn thành", "Chúc mừng! Bạn đã ôn xong tất cả các từ trong danh sách.")
            self.on_close()
            return
            
        item = self.data[self.current_idx]
        detail = data_manager.get_detail(item['word'], item['item_type'])
        is_mastered = detail.get('is_mastered', 0) if detail else 0
        
        self.lbl_progress.configure(text=f"Từ {self.current_idx + 1} / {len(self.data)}")
        
        if is_mastered:
            self.lbl_word.configure(text=item['word'].capitalize() + " ✅")
            self.btn_mastered.configure(state="disabled", text="Đã đánh dấu")
        else:
            self.lbl_word.configure(text=item['word'].capitalize())
            self.btn_mastered.configure(state="normal", text="✅ Đã thuộc (Space)")
            
        self.lbl_pos.configure(text=item['pos'])
        self.lbl_vn.configure(text=item['vn_meaning'].capitalize())
        self.lbl_ex.configure(text=f'"{item["sentence"]}"')
        
        # Đánh dấu là đã học và phát âm
        data_manager.update_progress(item['word'], item['item_type'])
        play_sound_system(item['word'])
        
        # Cập nhật danh sách bên ngoài ngầm
        (scroll_vocab if item['item_type'] == 'vocab' else scroll_phrase).refresh_item(item['word'])
        
        self.reset_timer()

    def reset_timer(self):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.time_left = float(self.time_per_word)
        self.time_bar.set(1.0)
        self.is_paused = False
        self.btn_pause.configure(text="⏸ Tạm Dừng", fg_color="#FF9500", hover_color="#E08300")
        self.tick()

    def tick(self):
        if not self.winfo_exists(): return
        if self.is_paused:
            return
            
        self.time_left -= 0.05  # Cập nhật mỗi 50ms cho mượt
        progress = max(0.0, self.time_left / self.time_per_word)
        self.time_bar.set(progress)
        
        # Chuyển màu thanh thời gian khi sắp hết giờ
        if progress < 0.3:
            self.time_bar.configure(progress_color=COLOR_DANGER[0])
        else:
            self.time_bar.configure(progress_color=COLOR_SUCCESS[0])
            
        if self.time_left <= 0:
            self.next_word()
        else:
            self.timer_id = self.after(50, self.tick)

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.configure(text="▶ Tiếp Tục", fg_color=COLOR_SUCCESS[0], hover_color="#28a745")
            if self.timer_id:
                self.after_cancel(self.timer_id)
        else:
            self.btn_pause.configure(text="⏸ Tạm Dừng", fg_color="#FF9500", hover_color="#E08300")
            self.tick()

    def next_word(self):
        self.current_idx += 1
        self.load_word()

    def prev_word(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.load_word()

    def on_close(self):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        refresh_lists()
        self.destroy()

def open_auto_learn():
    dialog = AutoLearnSetupDialog(app)
    if dialog.result_time and dialog.result_data:
        AutoLearnWindow(app, dialog.result_time, dialog.result_data)
class ClozeGameWindow(BaseGameWindow):
    def __init__(self, master, num, data):
        super().__init__(master, "Game Điền Từ (Ngữ Cảnh)")
        # Lọc ra những từ có câu ví dụ thực tế
        valid_data = [d for d in data if d.get('sentence') and "Chưa có ví dụ" not in d['sentence'] and "Hãy tự đặt" not in d['sentence'] and d['word'].lower() in d['sentence'].lower()]
        if not valid_data:
            messagebox.showinfo("Lỗi", "Không có đủ từ vựng có câu ví dụ để chơi game này!")
            self.destroy(); return
            
        self.questions = random.sample(valid_data, min(num, len(valid_data)))
        self.build()
        self.load()

    def build(self):
        self.lbl_q = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 22, "italic"), wraplength=600)
        self.lbl_q.pack(pady=(40, 20))
        
        self.entry = ctk.CTkEntry(self.game_area, font=("Segoe UI", 24, "bold"), justify="center", height=50)
        self.entry.pack(pady=10)
        self.entry.bind('<Return>', lambda e: self.check())
        
        self.lbl_hint = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 16), text_color=COLOR_SUCCESS[0])
        self.lbl_hint.pack(pady=10)
        
        bf = ctk.CTkFrame(self.game_area, fg_color="transparent")
        bf.pack(pady=20)
        ctk.CTkButton(bf, text="💡 Gợi ý nghĩa", command=lambda: self.lbl_hint.configure(text=f"Nghĩa: {self.questions[self.current_idx]['vn_meaning'].upper()}")).pack(side="left", padx=10)
        ctk.CTkButton(bf, text="Kiểm tra", fg_color=COLOR_ACCENT, hover_color="#4A48C0", command=self.check).pack(side="left", padx=10)

    def load(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.questions):
            messagebox.showinfo("Hoàn thành", f"Bạn làm đúng {self.score}/{len(self.questions)} câu.")
            self.destroy(); return
            
        self.lbl_progress_text.configure(text=f"Câu {self.current_idx+1}/{len(self.questions)}")
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        
        item = self.questions[self.current_idx]
        # Đục lỗ từ vựng trong câu
        import re
        blanked_sentence = re.sub(item['word'], "____", item['sentence'], flags=re.IGNORECASE)
        
        self.lbl_q.configure(text=f'"{blanked_sentence}"')
        self.lbl_hint.configure(text="")
        self.entry.delete(0, 'end')
        self.entry.focus()

    def check(self):
        cw = self.questions[self.current_idx]['word'].lower()
        if self.entry.get().strip().lower() == cw:
            self.score += 1
            data_manager.update_progress(cw, self.questions[self.current_idx]['item_type'])
            play_sound_system(cw)
        else:
            messagebox.showerror("Sai rồi", f"Từ cần điền là:\n{cw.upper()}")
        self.current_idx += 1
        self.load()

class HangmanGameWindow(BaseGameWindow):
    def __init__(self, master, num, data):
        super().__init__(master, "Game Đoán Chữ (Hangman)")
        self.game_data = data
        self.questions = []
        self.prepare(num)
        self.build()
        self.load()

    def prepare(self, num):
        for item in random.sample(self.game_data, min(num, len(self.game_data))): 
            self.questions.append((item['word'], item['vn_meaning'], item['item_type']))

    def build(self):
        self.lbl_vn = ctk.CTkLabel(self.game_area, text="", font=("Segoe UI", 20, "bold"), text_color=COLOR_SUCCESS[0], wraplength=600)
        self.lbl_vn.pack(pady=(20, 10))
        
        self.lbl_lives = ctk.CTkLabel(self.game_area, text="❤️❤️❤️❤️❤️", font=("Segoe UI", 24))
        self.lbl_lives.pack(pady=(0, 20))
        
        self.lbl_word = ctk.CTkLabel(self.game_area, text="", font=("Courier New", 48, "bold"), text_color=COLOR_ACCENT)
        self.lbl_word.pack(pady=(10, 30))
        
        self.kb_frame = ctk.CTkFrame(self.game_area, fg_color="transparent")
        self.kb_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.buttons = {}
        keys = ["ABCDEFGHI", "JKLMNOPQR", "STUVWXYZ"]
        for row_chars in keys:
            row_frame = ctk.CTkFrame(self.kb_frame, fg_color="transparent")
            row_frame.pack(pady=5)
            for char in row_chars:
                btn = ctk.CTkButton(row_frame, text=char, width=50, height=50, font=("Segoe UI", 16, "bold"), 
                                    command=lambda c=char: self.guess(c))
                btn.pack(side="left", padx=5)
                self.buttons[char] = btn
                
        self.bind("<Key>", self.key_pressed)

    def load(self):
        if not self.winfo_exists(): return
        if self.current_idx >= len(self.questions):
            messagebox.showinfo("Kết thúc", f"Bạn giải mã đúng {self.score}/{len(self.questions)} từ.")
            refresh_lists()
            self.destroy()
            return
            
        self.word, self.vn, self.ty = self.questions[self.current_idx]
        self.guessed_chars = set()
        self.lives = 5
        self.is_transitioning = False
        
        self.lbl_progress_text.configure(text=f"Câu {self.current_idx+1}/{len(self.questions)}")
        self.progress_bar.set((self.current_idx) / len(self.questions))
        self.lbl_score.configure(text=f"Điểm: {self.score}")
        
        self.lbl_vn.configure(text=self.vn.capitalize())
        self.update_word_display()
        self.update_lives_display()
        
        for btn in self.buttons.values():
            btn.configure(state="normal", fg_color=COLOR_ACCENT)

    def update_word_display(self):
        display_text = ""
        for char in self.word:
            if char.isalpha() and char.lower() not in self.guessed_chars:
                display_text += "_ "
            else:
                display_text += char.upper() + " "
        self.lbl_word.configure(text=display_text.strip())

    def update_lives_display(self):
        self.lbl_lives.configure(text="❤️" * self.lives + "🖤" * (5 - self.lives))
        
    def key_pressed(self, event):
        if event.char and event.char.isalpha():
            char = event.char.upper()
            if char in self.buttons and self.buttons[char].cget("state") == "normal":
                self.guess(char)

    def guess(self, char):
        if self.is_transitioning: return
        
        char_lower = char.lower()
        self.buttons[char].configure(state="disabled")
        
        if char_lower in self.word.lower():
            self.buttons[char].configure(fg_color=COLOR_SUCCESS[0])
            self.guessed_chars.add(char_lower)
            self.update_word_display()
            
            # Check win condition
            if all(c.lower() in self.guessed_chars or not c.isalpha() for c in self.word):
                self.is_transitioning = True
                self.score += 1
                data_manager.update_progress(self.word, self.ty)
                play_sound_system(self.word)
                self.current_idx += 1
                self.after(1000, self.load)
        else:
            self.buttons[char].configure(fg_color=COLOR_DANGER[0])
            self.lives -= 1
            self.update_lives_display()
            if self.lives <= 0:
                self.is_transitioning = True
                self.lbl_word.configure(text=" ".join(list(self.word.upper())))
                play_sound_system("Oops")
                self.lbl_lives.configure(text="💀 BẠN ĐÃ THUA!")
                self.current_idx += 1
                self.after(2000, self.load)

class RadioSetupDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Cài đặt Radio")
        self.geometry("450x350")
        self.transient(master)
        self.grab_set()
        self.result_data = None
        
        card = ctk.CTkFrame(self, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(card, text="📻 CÀI ĐẶT RADIO", font=("Segoe UI", 20, "bold"), text_color=COLOR_WARNING[0]).pack(pady=(15, 10))
        
        self.source_mode = ctk.CTkSegmentedButton(card, values=["Ngẫu nhiên", "Chưa ôn hôm nay"], font=FONT_BODY, command=self.update_count)
        self.source_mode.set("Ngẫu nhiên")
        self.source_mode.pack(pady=10, fill="x", padx=40)
        
        self.chk_include_mastered_var = ctk.IntVar(value=0)
        self.chk_include_mastered = ctk.CTkCheckBox(card, text="Bao gồm cả từ đã thuộc", variable=self.chk_include_mastered_var, command=lambda: self.update_count(self.source_mode.get()))
        self.chk_include_mastered.pack(pady=10)
        
        self.lbl_alert = ctk.CTkLabel(card, text="", text_color=COLOR_SUCCESS[0], font=("Segoe UI", 12, "italic"))
        self.lbl_alert.pack(pady=10)
        
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(pady=(10, 20), fill="x", padx=30)
        ctk.CTkButton(bf, text="Hủy", width=100, fg_color="transparent", hover_color=HOVER_COLOR_TRANSPARENT, border_width=1, command=self.destroy).pack(side="left")
        self.btn_start = ctk.CTkButton(bf, text="Phát Radio", width=100, fg_color=COLOR_WARNING[0], hover_color=COLOR_WARNING[1], command=self.on_start)
        self.btn_start.pack(side="right")
        
        self.update_count(self.source_mode.get())
        self.wait_window()
        
    def update_count(self, mode):
        data = get_game_data(mode, self.chk_include_mastered_var.get())
        if not data:
            self.lbl_alert.configure(text="Không có từ nào để phát!", text_color=COLOR_DANGER[0])
            self.btn_start.configure(state="disabled")
        else:
            self.lbl_alert.configure(text=f"Sẵn sàng phát {len(data)} từ.", text_color=COLOR_SUCCESS[0])
            self.btn_start.configure(state="normal")
            
    def on_start(self):
        self.result_data = get_game_data(self.source_mode.get(), self.chk_include_mastered_var.get())
        self.destroy()

def open_radio_setup():
    dialog = RadioSetupDialog(app)
    if dialog.result_data:
        RadioWindow(app, dialog.result_data)

class RadioWindow(ctk.CTkToplevel):
    def __init__(self, master, data):
        super().__init__(master)
        self.title("📻 Đài Phát Thanh Từ Vựng")
        self.geometry("450x550")
        self.transient(master)
        
        self.data = data
        self.idx = 0
        self.is_playing = True
        self.timer_id = None
        
        if not self.data:
            messagebox.showinfo("Thông báo", "Không có dữ liệu để phát!")
            self.after(100, self.destroy)
            return
            
        self.master.withdraw() # Tự động ẩn cửa sổ chính cho đỡ rối
        
        self.build()
        self.update_audio_progress()
        self.play_next()

    def build(self):
        self.configure(fg_color="#1E1E24")
        ctk.CTkLabel(self, text="📻 VOCAB RADIO", font=("Courier New", 26, "bold"), text_color="#00FFFF").pack(pady=(20, 5))
        
        self.lbl_progress = ctk.CTkLabel(self, text="", font=("Segoe UI", 14), text_color="gray")
        self.lbl_progress.pack(pady=(0, 10))
        
        self.lbl_word = ctk.CTkLabel(self, text="Đang tải...", font=("Segoe UI", 40, "bold"), text_color="white")
        self.lbl_word.pack(pady=10)
        
        self.lbl_vn = ctk.CTkLabel(self, text="", font=("Segoe UI", 20), text_color="#34C759", wraplength=350)
        self.lbl_vn.pack(pady=5)
        
        self.lbl_ex = ctk.CTkLabel(self, text="", font=("Segoe UI", 16, "italic"), text_color="gray", wraplength=350)
        self.lbl_ex.pack(pady=(5, 15))
        
        self.audio_progress_bar = ctk.CTkProgressBar(self, height=6, progress_color=COLOR_SUCCESS[0])
        self.audio_progress_bar.pack(fill="x", padx=50, pady=5)
        self.audio_progress_bar.set(0)
        
        self.lbl_audio_time = ctk.CTkLabel(self, text="0.0s / 0.0s", font=("Segoe UI", 12), text_color="gray")
        self.lbl_audio_time.pack(pady=(0, 10))
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 5))
        
        self.btn_toggle = ctk.CTkButton(btn_frame, text="⏸ TẠM DỪNG", fg_color="#FF9500", hover_color="#E08300", font=("Segoe UI", 13, "bold"), command=self.toggle, width=105)
        self.btn_toggle.pack(side="left", padx=5)
        
        self.btn_mastered = ctk.CTkButton(btn_frame, text="✅ Đã thuộc", fg_color=COLOR_SUCCESS[0], hover_color="#28a745", font=("Segoe UI", 13, "bold"), command=self.mark_mastered, width=105)
        self.btn_mastered.pack(side="left", padx=5)
        
        self.btn_skip = ctk.CTkButton(btn_frame, text="BỎ QUA ⏩", fg_color="#3A3A45", hover_color="#4A48C0", font=("Segoe UI", 13, "bold"), command=self.skip_word, width=105)
        self.btn_skip.pack(side="left", padx=5)
        
        btn_frame_2 = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame_2.pack(pady=5)
        
        self.is_random_voice = False
        self.btn_random = ctk.CTkButton(btn_frame_2, text="🎲 Giọng: Mặc định", fg_color="gray", hover_color="#4A48C0", font=("Segoe UI", 12, "bold"), command=self.toggle_random, width=140)
        self.btn_random.pack(side="left", padx=5)
        
        self.is_looping = False
        self.btn_loop = ctk.CTkButton(btn_frame_2, text="🔁 Lặp: Tắt", fg_color="gray", hover_color="#4A48C0", font=("Segoe UI", 12, "bold"), command=self.toggle_loop, width=140)
        self.btn_loop.pack(side="left", padx=5)
        
        self.btn_tray = ctk.CTkButton(self, text="🔽 THU NHỎ XUỐNG KHAY", fg_color="#5E5CE6", font=("Segoe UI", 14, "bold"), command=self.minimize_to_tray)
        self.btn_tray.pack(pady=(5, 10))
        
        self.bind("<space>", lambda e: self.mark_mastered())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_audio_progress(self):
        if not self.winfo_exists(): return
        if getattr(self, 'is_playing', False):
            if VOICE_CHANNEL.get_busy():
                pos = time.time() - CURRENT_AUDIO_START_TIME
                length = CURRENT_AUDIO_LENGTH
                if length > 0:
                    progress = min(1.0, pos / length)
                    self.audio_progress_bar.set(progress)
                    self.lbl_audio_time.configure(text=f"{pos:.1f}s / {length:.1f}s")
            else:
                self.audio_progress_bar.set(0)
                self.lbl_audio_time.configure(text="Đang tải âm thanh...")
        else:
            self.lbl_audio_time.configure(text="Đã tạm dừng")
        self.after(100, self.update_audio_progress)

    def toggle_random(self):
        self.is_random_voice = not self.is_random_voice
        if self.is_random_voice:
            self.btn_random.configure(text="🎲 Giọng: Ngẫu nhiên", fg_color=COLOR_ACCENT)
        else:
            self.btn_random.configure(text="🎲 Giọng: Mặc định", fg_color="gray")

    def toggle_loop(self):
        self.is_looping = not self.is_looping
        if self.is_looping:
            self.btn_loop.configure(text="🔁 Lặp: Bật", fg_color=COLOR_ACCENT)
        else:
            self.btn_loop.configure(text="🔁 Lặp: Tắt", fg_color="gray")
            
    def skip_word(self):
        if not self.winfo_exists(): return
        if self.timer_id: self.after_cancel(self.timer_id)
        self.idx += 1
        self.is_playing = True
        self.btn_toggle.configure(text="⏸ TẠM DỪNG", fg_color="#FF9500")
        self.play_next()

    def mark_mastered(self):
        if not self.winfo_exists() or self.idx >= len(self.data): return
        item = self.data[self.idx]
        data_manager.update_field(item['word'], item['item_type'], 'is_mastered', 1)
        (scroll_vocab if item['item_type'] == 'vocab' else scroll_phrase).refresh_item(item['word'])
        self.lbl_word.configure(text=item['word'].capitalize() + " ✅")
        self.btn_mastered.configure(state="disabled", text="Đã đánh dấu")

    def play_next(self):
        if not self.winfo_exists() or not self.is_playing: return
        if not self.is_playing: return
        if self.idx >= len(self.data): self.idx = 0 # Phát lặp lại từ đầu
        
        item = self.data[self.idx]
        self.lbl_progress.configure(text=f"Từ {self.idx + 1} / {len(self.data)}")
        
        # Cập nhật số lần học và danh sách ngầm
        data_manager.update_progress(item['word'], item['item_type'])
        (scroll_vocab if item['item_type'] == 'vocab' else scroll_phrase).refresh_item(item['word'])
        
        detail = data_manager.get_detail(item['word'], item['item_type'])
        is_mastered = detail.get('is_mastered', 0) if detail else 0
        
        if is_mastered:
            self.lbl_word.configure(text=item['word'].capitalize() + " ✅")
            self.btn_mastered.configure(state="disabled", text="Đã đánh dấu")
        else:
            self.lbl_word.configure(text=item['word'].capitalize())
            self.btn_mastered.configure(state="normal", text="✅ Đã thuộc")
            
        self.lbl_vn.configure(text="")
        self.lbl_ex.configure(text="")
        
        # 1. Đọc tiếng Anh, đọc xong TỰ ĐỘNG gọi hàm hiển thị nghĩa tiếng Việt
        play_sound_system(item['word'], is_random=self.is_random_voice, on_finish=lambda: self.show_meaning(item))

    def show_meaning(self, item):
        if not self.winfo_exists() or not self.is_playing: return
        if not self.is_playing: return
        self.lbl_vn.configure(text=item['vn_meaning'].capitalize())
        
        # Đọc tiếng Việt, đọc xong TỰ ĐỘNG gọi hàm đọc câu ví dụ
        play_sound_system(item['vn_meaning'], lang='vi', on_finish=lambda: self.play_sentence(item))

    def play_sentence(self, item):
        if not self.winfo_exists() or not self.is_playing: return
        if not self.is_playing: return
        if item.get('sentence') and "Chưa có" not in item['sentence'] and "Hãy tự đặt" not in item['sentence']:
            self.lbl_ex.configure(text=f'"{item["sentence"]}"')
            play_sound_system(item['sentence'], is_random=self.is_random_voice, on_finish=self.next_word)
        else:
            self.timer_id = self.after(1000, self.next_word)
        
    def next_word(self):
        if not self.winfo_exists() or not self.is_playing: return
        if not getattr(self, 'is_looping', False):
            self.idx += 1
        self.play_next()

    def toggle(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_toggle.configure(text="⏸ TẠM DỪNG", fg_color="#FF9500")
            self.play_next()
        else:
            self.btn_toggle.configure(text="▶ TIẾP TỤC", fg_color="#34C759")
            if self.timer_id: self.after_cancel(self.timer_id)
            
    def minimize_to_tray(self):
        try:
            import pystray
            from PIL import ImageDraw
        except ImportError:
            messagebox.showinfo("Thiếu thư viện", "Vui lòng cài đặt thư viện 'pystray' trước.\n\nMở Terminal và gõ lệnh:\npip install pystray")
            return

        self.withdraw()
        
        def on_show(icon, item):
            icon.stop()
            self.after(0, self.show_window)
            
        def on_exit(icon, item):
            icon.stop()
            self.after(0, self.on_close)
            
        image = Image.new('RGB', (64, 64), color='white')
        dc = ImageDraw.Draw(image)
        dc.rectangle([16, 16, 48, 48], fill="#FF9500")
        
        menu = pystray.Menu(
            pystray.MenuItem("▶ Mở lại Vocab Radio", on_show, default=True),
            pystray.MenuItem("❌ Thoát Radio", on_exit)
        )
        self.tray_icon = pystray.Icon("VocabRadio", image, "Vocab Radio", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self):
        self.deiconify()
        self.lift()          # Nâng cửa sổ lên trên cùng
        self.focus_force()   # Ép hệ thống trỏ chuột vào cửa sổ

    def on_close(self):
        self.is_playing = False
        if self.timer_id: self.after_cancel(self.timer_id)
        if hasattr(self, 'tray_icon'):
            try: self.tray_icon.stop()
            except: pass
        self.master.deiconify() # Hiện lại cửa sổ chính khi tắt Radio
        self.destroy()

# ================== CÀI ĐẶT NHẠC LO-FI ==================
class LofiManagerDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Quản lý Nhạc Lo-fi")
        self.geometry("700x600")
        self.transient(master)
        self.grab_set()
        self.selected_file = None

        lbl_title = ctk.CTkLabel(self, text="🎵 QUẢN LÝ NHẠC LO-FI", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT)
        lbl_title.pack(pady=(20, 10))

        # Khung tải nhạc
        dl_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=16, border_width=1, border_color=BORDER_COLOR)
        dl_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(dl_frame, text="Tải nhạc mới từ YouTube, Pixabay, Soundcloud...", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        
        input_frame = ctk.CTkFrame(dl_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=5)
        
        self.entry_url = ctk.CTkEntry(input_frame, placeholder_text="Dán link vào đây...", height=40)
        self.entry_url.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.btn_download = ctk.CTkButton(input_frame, text="⬇️ Tải Xuống", width=120, height=40, font=("Segoe UI", 14, "bold"), command=self.start_download)
        self.btn_download.pack(side="right")
        
        self.progress_bar = ctk.CTkProgressBar(dl_frame, height=8, progress_color=COLOR_SUCCESS[0])
        self.progress_bar.pack(fill="x", padx=20, pady=10)
        self.progress_bar.set(0)
        
        self.lbl_status = ctk.CTkLabel(dl_frame, text="Sẵn sàng", text_color=TEXT_SUB)
        self.lbl_status.pack(pady=(0, 15))

        # Khung danh sách nhạc
        ctk.CTkLabel(self, text="Danh sách nhạc đã tải (Chọn để phát):", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.load_list()
        self.wait_window()

    def load_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()
            
        # Tự động dọn dẹp các file rác (do ffmpeg lỗi để lại)
        for f in os.listdir(LOFI_DIR):
            if f.endswith(('.webm', '.m4a', '.mp4', '.part', '.ytdl')):
                try: os.remove(os.path.join(LOFI_DIR, f))
                except: pass
                
        lofi_files = [f for f in os.listdir(LOFI_DIR) if f.endswith(('.mp3', '.ogg', '.wav'))]
        if not lofi_files:
            ctk.CTkLabel(self.list_frame, text="Bạn chưa tải bài nhạc nào. Hãy dán link phía trên để tải nhé!", text_color=TEXT_SUB).pack(pady=30)
            return
            
        for f in lofi_files:
            row = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            row.pack(fill="x", pady=5)
            
            display_name = f
            if len(display_name) > 45: display_name = display_name[:45] + "..."
            
            ctk.CTkLabel(row, text="🎵 " + display_name, font=("Segoe UI", 14)).pack(side="left", padx=10)
            btn_play = ctk.CTkButton(row, text="▶ Phát", width=80, fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=lambda file=f: self.select_and_close(file))
            btn_play.pack(side="right", padx=10)
            btn_del = ctk.CTkButton(row, text="🗑 Xóa", width=60, fg_color="transparent", border_width=1, text_color=COLOR_DANGER[0], border_color=COLOR_DANGER[0], hover_color=HOVER_COLOR_TRANSPARENT, command=lambda file=f: self.delete_file(file))
            btn_del.pack(side="right", padx=5)

    def select_and_close(self, file_name):
        self.selected_file = os.path.join(LOFI_DIR, file_name)
        self.destroy()

    def delete_file(self, file_name):
        if messagebox.askyesno("Xác nhận", f"Bạn có chắc muốn xóa bài nhạc:\n{file_name}?"):
            try:
                pygame.mixer.music.stop()
                try: pygame.mixer.music.unload()
                except: pass
                os.remove(os.path.join(LOFI_DIR, file_name))
                self.load_list()
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xóa file: {e}")

    def start_download(self):
        url = self.entry_url.get().strip()
        if not url: return
        
        self.btn_download.configure(state="disabled")
        self.lbl_status.configure(text="Đang phân tích link...", text_color=TEXT_SUB)
        self.progress_bar.set(0)
        
        def download_thread():
            from urllib.parse import urlparse
            if ".mp3" in url.lower() or urlparse(url).path.lower().endswith('.mp3'):
                try:
                    app.after(0, lambda: self.lbl_status.configure(text="Đang tải file MP3 trực tiếp...", text_color=COLOR_ACCENT[0]))
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"}
                    res = requests.get(url, headers=headers, stream=True, timeout=10)
                    if res.status_code == 200:
                        total_size = int(res.headers.get('content-length', 0))
                        filename = os.path.basename(urlparse(url).path)
                        if not filename.endswith(".mp3"): filename = f"downloaded_{int(time.time())}.mp3"
                        save_path = os.path.join(LOFI_DIR, filename)
                        
                        downloaded_size = 0
                        with open(save_path, "wb") as f:
                            for chunk in res.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded_size += len(chunk)
                                    if total_size > 0:
                                        percent = downloaded_size / total_size
                                        app.after(0, lambda p=percent: self.progress_bar.set(p))
                        
                        app.after(0, lambda: self.lbl_status.configure(text="✅ Tải nhạc thành công!", text_color=COLOR_SUCCESS[0]))
                        app.after(0, self.load_list)
                        app.after(0, lambda: self.btn_download.configure(state="normal"))
                        app.after(0, lambda: self.entry_url.delete(0, 'end'))
                        return 
                except Exception:
                    pass 
                    
            try:
                import yt_dlp
            except ImportError:
                if getattr(sys, 'frozen', False):
                    app.after(0, lambda: messagebox.showerror("Thiếu thư viện", "Vui lòng mở Terminal (CMD) và gõ lệnh sau để tải từ YouTube:\n\npip install yt-dlp"))
                    app.after(0, lambda: self.lbl_status.configure(text="❌ Thiếu thư viện yt-dlp.", text_color=COLOR_DANGER[0]))
                    app.after(0, lambda: self.btn_download.configure(state="normal"))
                    return
                app.after(0, lambda: self.lbl_status.configure(text="Đang tự động cài thư viện yt-dlp...", text_color=COLOR_WARNING[0]))
                try:
                    import subprocess
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
                    import yt_dlp
                except Exception:
                    app.after(0, lambda: messagebox.showerror("Thiếu thư viện", "Vui lòng mở Terminal (CMD) và gõ lệnh sau để tải từ YouTube:\n\npip install yt-dlp"))
                    app.after(0, lambda: self.lbl_status.configure(text="❌ Thiếu thư viện yt-dlp.", text_color=COLOR_DANGER[0]))
                    app.after(0, lambda: self.btn_download.configure(state="normal"))
                    return

            import shutil
            import platform
            ffmpeg_exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
            ffmpeg_path = shutil.which("ffmpeg")
            local_ffmpeg = os.path.join(LOFI_DIR, ffmpeg_exe_name)
            
            # Xóa file ffmpeg rỗng hoặc lỗi (dung lượng < 20MB)
            if os.path.exists(local_ffmpeg) and os.path.getsize(local_ffmpeg) < 20_000_000:
                try: os.remove(local_ffmpeg)
                except: pass

            # TỰ ĐỘNG TẢI FFMPEG NẾU MÁY TÍNH CHƯA CÓ
            if not ffmpeg_path and not os.path.exists(local_ffmpeg):
                app.after(0, lambda: self.lbl_status.configure(text="Đang tải FFmpeg để xử lý MP3 (Khoảng 35MB)...", text_color=COLOR_WARNING[0]))
                try:
                    if platform.system() == "Windows": ff_url = "https://github.com/imageio/imageio-binaries/raw/master/ffmpeg/ffmpeg-win32-v4.2.2.exe"
                    elif platform.system() == "Darwin": ff_url = "https://github.com/imageio/imageio-binaries/raw/master/ffmpeg/ffmpeg-osx-v4.2.2"
                    else: ff_url = "https://github.com/imageio/imageio-binaries/raw/master/ffmpeg/ffmpeg-linux64-v4.2.2"
                        
                    res_ff = requests.get(ff_url, stream=True, timeout=30)
                    if res_ff.status_code == 200:
                        total_ff = int(res_ff.headers.get('content-length', 0))
                        dl_ff = 0
                        temp_ffmpeg = local_ffmpeg + ".tmp"
                        with open(temp_ffmpeg, "wb") as f:
                            for chunk in res_ff.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    dl_ff += len(chunk)
                                    if total_ff > 0:
                                        app.after(0, lambda p=dl_ff/total_ff: self.progress_bar.set(p))
                        # Tải xong 100% mới đổi tên thành .exe (Tránh lỗi file hỏng)
                        if os.path.exists(temp_ffmpeg) and os.path.getsize(temp_ffmpeg) > 20_000_000:
                            os.rename(temp_ffmpeg, local_ffmpeg)
                            if platform.system() != "Windows":
                                os.chmod(local_ffmpeg, 0o755)
                except Exception:
                    pass

            if not ffmpeg_path and os.path.exists(local_ffmpeg):
                ffmpeg_path = local_ffmpeg
            else:
                ffmpeg_path = None

            class MyLogger:
                def debug(self, msg): pass
                def warning(self, msg): pass
                def error(self, msg): pass

            def my_hook(d):
                if d['status'] == 'downloading':
                    try:
                        percent_str = d['_percent_str'].strip('\x1b[0;94m').strip('%').strip()
                        percent = float(percent_str) / 100.0
                        app.after(0, lambda p=percent: self.progress_bar.set(p))
                        speed = d.get('_speed_str', '')
                        eta = d.get('_eta_str', '')
                        app.after(0, lambda: self.lbl_status.configure(text=f"Đang tải: {percent*100:.1f}% | Tốc độ: {speed} | Còn lại: {eta}", text_color=COLOR_ACCENT[0]))
                    except:
                        pass
                elif d['status'] == 'finished':
                    app.after(0, lambda: self.lbl_status.configure(text="Đang chuẩn bị xử lý âm thanh...", text_color=COLOR_WARNING[0]))
                    app.after(0, lambda: self.progress_bar.set(1.0))

            def pp_hook(d):
                if d['status'] == 'started':
                    app.after(0, lambda: self.lbl_status.configure(text="Đang xử lý FFmpeg (Đa luồng siêu tốc)...", text_color=COLOR_WARNING[0]))
                    app.after(0, lambda: self.progress_bar.configure(mode="indeterminate"))
                    app.after(0, lambda: self.progress_bar.start())
                elif d['status'] == 'finished':
                    app.after(0, lambda: self.progress_bar.stop())
                    app.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                    app.after(0, lambda: self.progress_bar.set(1.0))

            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'postprocessor_args': [
                    '-threads', '0',
                ],
                'outtmpl': os.path.join(LOFI_DIR, '%(title)s.%(ext)s'),
                'logger': MyLogger(),
                'progress_hooks': [my_hook],
                'postprocessor_hooks': [pp_hook],
                'quiet': True,
                'noplaylist': True
            }
            
            if ffmpeg_path:
                ydl_opts['ffmpeg_location'] = ffmpeg_path

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                app.after(0, lambda: self.progress_bar.stop())
                app.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                app.after(0, lambda: self.lbl_status.configure(text="✅ Tải nhạc thành công!", text_color=COLOR_SUCCESS[0]))
                app.after(0, self.load_list)
            except Exception as e:
                app.after(0, lambda: self.progress_bar.stop())
                app.after(0, lambda: self.progress_bar.configure(mode="determinate"))
                err_msg = str(e)
                if "ffprobe" in err_msg.lower() or "ffmpeg" in err_msg.lower() or "postprocessing" in err_msg.lower():
                    app.after(0, lambda: messagebox.showerror("Lỗi xử lý âm thanh", "Tải file thành công nhưng không thể chuyển thành nhạc MP3 do lỗi/thiếu công cụ FFmpeg.\n\nHãy đảm bảo mạng của bạn ổn định để ứng dụng tự động tải FFmpeg ở lần thử sau!"))
                app.after(0, lambda: self.lbl_status.configure(text="❌ Lỗi: Không thể tải được link này.", text_color=COLOR_DANGER[0]))
            finally:
                app.after(0, lambda: self.btn_download.configure(state="normal"))
                app.after(0, lambda: self.entry_url.delete(0, 'end'))

        threading.Thread(target=download_thread, daemon=True).start()

# ================== ĐỒNG HỒ POMODORO ==================
class PomodoroFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=16, fg_color=BG_CARD, border_width=1, border_color=BORDER_COLOR)
        
        self.WORK_TIME = 25 * 60
        self.BREAK_TIME = 5 * 60
        
        self.mode = "WORK"
        self.time_left = self.WORK_TIME
        self.is_running = False
        self.timer_id = None
        
        self.build_ui()
        self.update_display()
        
    def build_ui(self):
        self.lbl_mode = ctk.CTkLabel(self, text="🎯 THỜI GIAN TẬP TRUNG", font=("Segoe UI", 18, "bold"), text_color=COLOR_DANGER[0])
        self.lbl_mode.pack(pady=(20, 10))
        
        self.lbl_time = ctk.CTkLabel(self, text="25:00", font=("Segoe UI", 60, "bold"), text_color=COLOR_ACCENT)
        self.lbl_time.pack(pady=10)
        
        self.progress_bar = ctk.CTkProgressBar(self, height=12, progress_color=COLOR_DANGER[0])
        self.progress_bar.pack(fill="x", padx=30, pady=(10, 20))
        self.progress_bar.set(1.0)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=5)
        
        self.btn_toggle = ctk.CTkButton(btn_frame, text="▶ Bắt đầu", width=110, height=40, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.toggle)
        self.btn_toggle.pack(side="left", padx=5)
        
        self.btn_reset = ctk.CTkButton(btn_frame, text="🔄 Đặt lại", width=90, height=40, font=("Segoe UI", 14), fg_color="gray", hover_color="#4A48C0", command=self.reset)
        self.btn_reset.pack(side="left", padx=5)
        
        self.btn_skip = ctk.CTkButton(self, text="⏭ Chuyển sang Nghỉ ngơi", width=200, height=35, fg_color="transparent", border_width=1, text_color=TEXT_SUB, command=self.skip)
        self.btn_skip.pack(pady=15)
        
        lofi_frame = ctk.CTkFrame(self, fg_color="transparent")
        lofi_frame.pack(pady=(0, 5))
        self.btn_lofi = ctk.CTkButton(lofi_frame, text="🎵 Bật nhạc Lo-fi", fg_color="#5E5CE6", hover_color="#4A48C0", text_color="white", command=self.toggle_lofi)
        self.btn_lofi.pack(side="left", padx=(0, 5))
        
        self.btn_lofi_next = ctk.CTkButton(lofi_frame, text="⏭", width=35, fg_color="gray", hover_color="#4A48C0", command=self.next_lofi)
        self.btn_lofi_next.pack(side="left", padx=(0, 5))
        
        self.btn_lofi_edit = ctk.CTkButton(lofi_frame, text="⚙️", width=35, fg_color="gray", hover_color="#4A48C0", command=self.change_lofi_url)
        self.btn_lofi_edit.pack(side="left")
        self.volume_slider = ctk.CTkSlider(lofi_frame, from_=0.0, to=1.0, width=100, command=self.change_volume)
        self.volume_slider.set(0.3)
        self.volume_slider.pack(side="left", padx=(10, 0))
        
        self.lbl_lofi_status = ctk.CTkLabel(self, text="Sẵn sàng phát nhạc", font=("Segoe UI", 13), text_color=TEXT_SUB)
        self.lbl_lofi_status.pack(pady=(0, 15))
        
        self.session_seconds = 0

    def change_volume(self, value):
        try: pygame.mixer.music.set_volume(value)
        except: pass

    def change_lofi_url(self):
        dialog = LofiManagerDialog(self)
        if dialog.selected_file:
            data_manager.set_setting("lofi_file", dialog.selected_file)
            if getattr(self, 'lofi_playing', False):
                self.toggle_lofi() # Tắt nhạc hiện tại
            self.toggle_lofi() # Bật lại nhạc mới

    def toggle_lofi(self):
        if not getattr(self, 'lofi_playing', False):
            self.lofi_playing = True
            
            self.lofi_playlist = [os.path.join(LOFI_DIR, f) for f in os.listdir(LOFI_DIR) if f.endswith(('.mp3', '.ogg', '.wav'))]
            self.current_lofi_idx = 0
            
            if not self.lofi_playlist:
                self.lofi_playing = False
                self.lbl_lofi_status.configure(text="❌ Chưa có bài nhạc nào. Bấm ⚙️ để tải.")
                return
                
            preferred = data_manager.get_setting("lofi_file", "")
            if preferred in self.lofi_playlist:
                self.current_lofi_idx = self.lofi_playlist.index(preferred)
                
            self.fail_count = 0
            self.btn_lofi.configure(text="🔇 Tắt nhạc Lo-fi", fg_color=COLOR_DANGER[0])
            self.play_current_lofi()
        else:
            self.lofi_playing = False
            pygame.mixer.music.stop()
            if getattr(self, 'lofi_timer', None):
                self.after_cancel(self.lofi_timer)
            self.btn_lofi.configure(text="🎵 Bật nhạc Lo-fi", fg_color="#5E5CE6", state="normal")
            self.lbl_lofi_status.configure(text="Đã tắt nhạc.")

    def next_lofi(self):
        if getattr(self, 'lofi_playing', False) and hasattr(self, 'lofi_playlist') and self.lofi_playlist:
            pygame.mixer.music.stop()
            if getattr(self, 'lofi_timer', None):
                self.after_cancel(self.lofi_timer)
            self.current_lofi_idx += 1
            if self.current_lofi_idx >= len(self.lofi_playlist):
                self.current_lofi_idx = 0
            self.play_current_lofi()

    def play_current_lofi(self):
        if not getattr(self, 'lofi_playing', False): return
        
        if getattr(self, 'fail_count', 0) >= len(self.lofi_playlist):
            self.lofi_playing = False
            self.btn_lofi.configure(text="🎵 Bật nhạc Lo-fi", fg_color="#5E5CE6", state="normal")
            self.lbl_lofi_status.configure(text="❌ Lỗi phát nhạc. Các file có thể bị hỏng.")
            return

        if self.current_lofi_idx >= len(self.lofi_playlist):
            self.current_lofi_idx = 0
            
        path = self.lofi_playlist[self.current_lofi_idx]
        self.btn_lofi.configure(state="disabled")
        self.lbl_lofi_status.configure(text="⏳ Đang tải bài hát...")
        
        if os.path.exists(path):
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self.volume_slider.get())
                pygame.mixer.music.play(loops=0)
                
                filename = os.path.basename(path)
                if len(filename) > 35: filename = filename[:32] + "..."
                self.lbl_lofi_status.configure(text=f"🎶 Đang phát: {filename}")
                self.btn_lofi.configure(state="normal")
                
                self.fail_count = 0
                self.check_lofi_end()
            except Exception:
                self.fail_count = getattr(self, 'fail_count', 0) + 1
                self.current_lofi_idx += 1
                self.after(100, self.play_current_lofi)
        else:
            self.fail_count = getattr(self, 'fail_count', 0) + 1
            self.current_lofi_idx += 1
            self.after(100, self.play_current_lofi)

    def check_lofi_end(self):
        if not getattr(self, 'lofi_playing', False): return
        if not pygame.mixer.music.get_busy():
            self.current_lofi_idx += 1
            self.after(100, self.play_current_lofi)
        else:
            self.lofi_timer = self.after(1000, self.check_lofi_end)

    def update_display(self):
        mins = self.time_left // 60
        secs = self.time_left % 60
        self.lbl_time.configure(text=f"{mins:02d}:{secs:02d}")
        
        total_time = self.WORK_TIME if self.mode == "WORK" else self.BREAK_TIME
        progress = max(0.0, self.time_left / total_time)
        self.progress_bar.set(progress)
        
    def toggle(self):
        self.is_running = not self.is_running
        if self.is_running:
            self.btn_toggle.configure(text="⏸ Tạm dừng", fg_color="#FF9500", hover_color="#E08300")
            self.tick()
        else:
            self.btn_toggle.configure(text="▶ Tiếp tục", fg_color=COLOR_SUCCESS[0], hover_color="#28a745")
            if self.timer_id:
                self.after_cancel(self.timer_id)
                
    def tick(self):
        if not self.is_running or not self.winfo_exists(): return
        
        self.time_left -= 1
        
        if self.mode == "WORK":
            self.session_seconds += 1
            if self.session_seconds >= 60: # Cứ 60 giây thì lưu vào hệ thống
                current_mins = int(data_manager.get_setting("total_study_minutes", "0"))
                data_manager.set_setting("total_study_minutes", str(current_mins + 1))
                self.session_seconds = 0
                
        self.update_display()
        
        if self.time_left <= 0:
            self.play_alarm()
            self.skip()
        else:
            self.timer_id = self.after(1000, self.tick)
            
    def reset(self):
        self.is_running = False
        if self.timer_id:
            self.after_cancel(self.timer_id)
        self.time_left = self.WORK_TIME if self.mode == "WORK" else self.BREAK_TIME
        self.btn_toggle.configure(text="▶ Bắt đầu", fg_color=COLOR_SUCCESS[0], hover_color="#28a745")
        self.update_display()
        
    def skip(self):
        self.is_running = False
        if self.timer_id:
            self.after_cancel(self.timer_id)
            
        if self.mode == "WORK":
            self.mode = "BREAK"
            self.time_left = self.BREAK_TIME
            self.lbl_mode.configure(text="☕ THỜI GIAN NGHỈ NGƠI", text_color=COLOR_SUCCESS[0])
            self.progress_bar.configure(progress_color=COLOR_SUCCESS[0])
            self.btn_skip.configure(text="⏭ Chuyển sang Tập trung")
        else:
            self.mode = "WORK"
            self.time_left = self.WORK_TIME
            self.lbl_mode.configure(text="🎯 THỜI GIAN TẬP TRUNG", text_color=COLOR_DANGER[0])
            self.progress_bar.configure(progress_color=COLOR_DANGER[0])
            self.btn_skip.configure(text="⏭ Chuyển sang Nghỉ ngơi")
            
        self.btn_toggle.configure(text="▶ Bắt đầu", fg_color=COLOR_SUCCESS[0], hover_color="#28a745")
        self.update_display()
        
    def play_alarm(self):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except:
            pass
            
    def stop_timer(self):
        self.is_running = False
        if self.timer_id:
            self.after_cancel(self.timer_id)

def check_reminder_loop():
    global LAST_REMINDED_DATE
    if data_manager.get_setting("reminder_enabled", "0") == "1":
        remind_time = data_manager.get_setting("reminder_time", "20:00")
        now = datetime.now()
        if now.strftime("%H:%M") == remind_time and LAST_REMINDED_DATE != now.strftime("%Y-%m-%d"):
            LAST_REMINDED_DATE = now.strftime("%Y-%m-%d")
            show_toast_notification()
            
    app.after(30000, check_reminder_loop) # Chạy ngầm kiểm tra mỗi 30 giây

lbl_status.configure(text="Hoàn tất khởi động!")
splash.update()

if __name__ == "__main__":
    def start_app():
        app.deiconify()  # Bật hiển thị cửa sổ chính trước
        splash.destroy() # Hủy màn hình loading sau cùng
        
    app.after(800, start_app) # Đợi 0.8 giây để vòng lặp giao diện ổn định rồi mới chuyển cảnh
    check_reminder_loop()
    app.mainloop()