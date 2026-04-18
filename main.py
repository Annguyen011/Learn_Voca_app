import customtkinter as ctk
from tkinter import messagebox
import sqlite3
import os
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
import sys
import shutil
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

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

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

pygame.mixer.init()
translator = GoogleTranslator(source='en', target='vi')

executor = ThreadPoolExecutor(max_workers=15)
DB_LOCK = threading.Lock()

BG_SIDEBAR = ("#F7F9FC", "#1E1E24")
BG_MAIN = ("#FFFFFF", "#141419")
BG_CARD = ("#E6EBF5", "#272730")
COLOR_ACCENT = "#5E5CE6"
COLOR_SUCCESS = ("#34C759", "#30D158")
COLOR_DANGER = ("#FF3B30", "#FF453A")
TEXT_SUB = ("#6E6E73", "#98989F")
FONT_TITLE = ("Segoe UI", 42, "bold")
FONT_VN = ("Segoe UI", 22, "bold")
FONT_BODY = ("Segoe UI", 14)
FONT_ITALIC = ("Segoe UI", 15, "italic")

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
            c.execute('''CREATE TABLE IF NOT EXISTS phrase
                         (word TEXT PRIMARY KEY, sentence TEXT, pos TEXT, vn_meaning TEXT,
                          last_studied TEXT, study_count INTEGER DEFAULT 0, custom_sentence TEXT, item_type TEXT DEFAULT 'phrase')''')
            c.execute('''CREATE TABLE IF NOT EXISTS daily_tracker
                         (date TEXT, word TEXT, PRIMARY KEY (date, word))''')
            conn.commit()
            conn.close()

    def _load_to_ram(self):
        with DB_LOCK:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            for row in c.execute("SELECT * FROM vocab"):
                self.vocab[row[0]] = {'sentence': row[1], 'pos': row[2], 'vn_meaning': row[3], 'last_studied': row[4], 'study_count': row[5], 'custom_sentence': row[6], 'item_type': row[7]}
            for row in c.execute("SELECT * FROM phrase"):
                self.phrase[row[0]] = {'sentence': row[1], 'pos': row[2], 'vn_meaning': row[3], 'last_studied': row[4], 'study_count': row[5], 'custom_sentence': row[6], 'item_type': row[7]}
            for row in c.execute("SELECT date, word FROM daily_tracker"):
                if row[0] not in self.tracker: self.tracker[row[0]] = set()
                self.tracker[row[0]].add(row[1])
            conn.close()

    def get_all(self, item_type):
        d = self.vocab if item_type == 'vocab' else self.phrase
        return [(w, v['vn_meaning'], v['study_count'], v['last_studied']) for w, v in d.items()]

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
            d[word] = {'sentence': sentence, 'pos': pos, 'vn_meaning': vn_meaning, 'last_studied': "", 'study_count': 0, 'custom_sentence': custom_sentence, 'item_type': item_type}
        
        if sync_db:
            def save_to_db():
                with DB_LOCK:
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    if c.execute(f"SELECT 1 FROM {item_type} WHERE word=?", (word,)).fetchone():
                        conn.execute(f"UPDATE {item_type} SET sentence=?, pos=?, vn_meaning=?, custom_sentence=? WHERE word=?", (sentence, pos, vn_meaning, custom_sentence, word))
                    else:
                        conn.execute(f"INSERT INTO {item_type} (word, sentence, pos, vn_meaning, custom_sentence, last_studied, study_count) VALUES (?,?,?,?,?,?,?)", (word, sentence, pos, vn_meaning, custom_sentence, "", 0))
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

def play_sound_system(text):
    if not text: return
    safe_name = hashlib.md5(text.encode()).hexdigest()
    audio_path = os.path.join(AUDIO_CACHE_DIR, f"{safe_name}.mp3")
    def task():
        try:
            if not os.path.exists(audio_path):
                tts = gTTS(text=text, lang='en')
                tts.save(audio_path)
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): pygame.time.Clock().tick(10)
            pygame.mixer.music.unload()
        except: pass
    executor.submit(task)

def download_and_cache_image(word):
    cache_path = os.path.join(CACHE_DIR, f"{hashlib.md5(word.encode()).hexdigest()}.jpg")
    if os.path.exists(cache_path): return cache_path
    img_data = image_cache.get(word)
    if img_data:
        with open(cache_path, "wb") as f: f.write(img_data)
        return cache_path
    try:
        url = f"https://tse2.mm.bing.net/th?q={word.replace(' ', '+')}+png+isolated&w=400&h=400&c=7&rs=1"
        res = requests.get(url, timeout=4)
        if res.status_code == 200:
            with open(cache_path, "wb") as f: f.write(res.content)
            image_cache.set(word, res.content)
            return cache_path
    except: pass
    return None

def load_image_async(word, label_widget):
    def task():
        cache_path = download_and_cache_image(word)
        if cache_path and os.path.exists(cache_path):
            try:
                pil_img = Image.open(cache_path)
                pil_img.thumbnail((200, 200), Image.Resampling.BILINEAR)
                ctk_img = ctk.CTkImage(pil_img, size=(180, 180))
                app.after(0, lambda: label_widget.configure(image=ctk_img, text=""))
                return
            except: pass
        app.after(0, lambda: label_widget.configure(text="[ Không tải được ảnh ]", image=""))
    executor.submit(task)

# ================== TỐI ƯU VIRTUAL SCROLL LIST ==================
# ================== TỐI ƯU VIRTUAL SCROLL LIST (60FPS RENDER ENGINE) ==================
class VirtualScrollList(ctk.CTkFrame):
    def __init__(self, master, item_type, **kwargs):
        bg_color = kwargs.pop('bg', BG_SIDEBAR[1])
        super().__init__(master, fg_color="transparent", **kwargs)
        self.item_type = item_type
        self.items = []
        self.item_height = 56
        
        self.canvas = ctk.CTkCanvas(self, highlightthickness=0, bg=bg_color, borderwidth=0)
        # Tối ưu: Scrollbar giờ điều khiển Canvas trực tiếp, không gọi qua hàm redraw nữa
        self.scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        self.canvas.bind('<Configure>', self.on_resize)
        self.bind_scroll(self.canvas)
        
        self.total_height = 0
        self.sort_criteria = "recent"
        
        self.pool_size = 50 # Tăng lên 50 để chống viền trắng trên màn hình 2K/4K
        self.row_pool = []
        self.init_pool()
        self.load_data()
        
        # KHỞI ĐỘNG VÒNG LẶP RENDER 60 FPS
        self.last_y = -1
        self.last_h = -1
        self.after(16, self.render_loop)

    # Vòng lặp ngầm: Chỉ vẽ lại khi màn hình thực sự xê dịch
    def render_loop(self):
        try:
            current_y = self.canvas.canvasy(0)
            current_h = self.canvas.winfo_height()
            if current_y != self.last_y or current_h != self.last_h:
                self.redraw()
                self.last_y = current_y
                self.last_h = current_h
        except:
            pass
        self.after(16, self.render_loop)

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
        # KHÔNG gọi self.redraw() ở đây nữa để chống nghẽn CPU

    def init_pool(self):
        for _ in range(self.pool_size):
            frame = ctk.CTkFrame(self.canvas, fg_color=BG_CARD, corner_radius=8, height=48)
            frame.grid_columnconfigure(1, weight=1); frame.grid_columnconfigure(2, weight=1)
            frame.grid_propagate(False)
            
            lbl_icon = ctk.CTkLabel(frame, text="", font=("Segoe UI", 18, "bold"), width=30)
            lbl_icon.grid(row=0, column=0, pady=8, padx=5)
            lbl_word = ctk.CTkLabel(frame, text="", font=("Segoe UI", 14, "bold"), anchor="w")
            lbl_word.grid(row=0, column=1, sticky="we", pady=8, padx=5)
            lbl_vn = ctk.CTkLabel(frame, text="", font=FONT_BODY, text_color=TEXT_SUB, anchor="w")
            lbl_vn.grid(row=0, column=2, sticky="we", pady=8, padx=5)
            lbl_count = ctk.CTkLabel(frame, text="", font=("Segoe UI", 14, "bold"), text_color=COLOR_SUCCESS[0], width=30)
            lbl_count.grid(row=0, column=3, pady=8, padx=5)
            btn_view = ctk.CTkButton(frame, text="Xem", width=50, height=28, font=("Segoe UI", 12, "bold"), fg_color=COLOR_ACCENT, hover_color="#4A48C0")
            btn_view.grid(row=0, column=4, padx=10, pady=8)
            
            for w in [frame, lbl_icon, lbl_word, lbl_vn, lbl_count, btn_view]:
                self.bind_scroll(w)
            
            wid = self.canvas.create_window(0, -1000, anchor='nw', window=frame)
            self.row_pool.append({
                'frame': frame, 'icon': lbl_icon, 'word': lbl_word, 
                'vn': lbl_vn, 'count': lbl_count, 'btn': btn_view, 
                'id': wid, 'data_idx': -1
            })

    def load_data(self):
        self.items = data_manager.get_all(self.item_type)
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
        self.last_y = -1 # Đánh dấu ép render lại
        
    def update_total_height(self):
        self.total_height = max(len(self.items) * self.item_height, self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.total_height))
    
    def on_resize(self, event):
        self.update_total_height()
        for row in self.row_pool:
            self.canvas.itemconfig(row['id'], width=event.width)
        self.last_y = -1 # Ép render lại nếu đổi kích thước
    
    def redraw(self):
        view_top = self.canvas.canvasy(0)
        first = max(0, int(view_top // self.item_height))
        last = min(len(self.items), first + self.pool_size)
        
        active_pool_indices = set()
        for data_idx in range(first, last):
            pool_idx = data_idx % self.pool_size
            active_pool_indices.add(pool_idx)
            row = self.row_pool[pool_idx]
            
            if row['data_idx'] != data_idx:
                word, vn_meaning, study_count, last_studied = self.items[data_idx]
                is_old = False
                if last_studied:
                    try:
                        if (datetime.now() - datetime.strptime(last_studied, "%Y-%m-%d %H:%M")).days >= 3:
                            is_old = True
                    except: pass
                
                row['icon'].configure(text="⚠" if is_old else "✦", text_color=COLOR_DANGER[0] if is_old else COLOR_ACCENT)
                row['word'].configure(text=word.capitalize())
                row['vn'].configure(text=vn_meaning.capitalize() if vn_meaning else "")
                row['count'].configure(text=str(study_count))
                row['btn'].configure(command=lambda w=word, ty=self.item_type: select_item(w, ty))
                row['data_idx'] = data_idx
            
            self.canvas.coords(row['id'], 0, data_idx * self.item_height)
            
        for i in range(self.pool_size):
            if i not in active_pool_indices and self.row_pool[i]['data_idx'] != -1:
                self.canvas.coords(self.row_pool[i]['id'], 0, -1000)
                self.row_pool[i]['data_idx'] = -1
                
    def refresh_item(self, word):
        for i, (w, vn, count, last) in enumerate(self.items):
            if w == word:
                detail = data_manager.get_detail(word, self.item_type)
                self.items[i] = (w, detail['vn_meaning'], detail['study_count'], detail['last_studied'])
                pool_idx = i % self.pool_size
                if self.row_pool[pool_idx]['data_idx'] == i:
                    self.row_pool[pool_idx]['data_idx'] = -1 
                self.last_y = -1 # Force redraw
                break
# ================== GIAO DIỆN CHÍNH ==================
app = ctk.CTk()
app.title("Vocab Master Premium")
app.geometry("1350x800")
app.grid_columnconfigure(1, weight=1)
app.grid_rowconfigure(1, weight=1)

top_bar = ctk.CTkFrame(app, height=45, corner_radius=0, fg_color=BG_CARD)
top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")

def open_batch_add(): BatchAddDialog(app)
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

ctk.CTkButton(top_bar, text="➕ Thêm hàng loạt", font=FONT_BODY, fg_color="transparent", command=open_batch_add).pack(side="left", padx=10, pady=5)
ctk.CTkButton(top_bar, text="📻 Radio", font=FONT_BODY, fg_color="transparent", text_color="#FF9500", command=lambda: RadioWindow(app, get_game_data("Ngẫu nhiên"))).pack(side="left", padx=10, pady=5)
ctk.CTkButton(top_bar, text="▶ Học Tự Động", font=FONT_BODY, fg_color="transparent", text_color=COLOR_ACCENT, command=lambda: open_auto_learn()).pack(side="left", padx=10, pady=5)
ctk.CTkButton(top_bar, text="🎮 Game Ôn Tập", font=FONT_BODY, fg_color="transparent", command=lambda: open_game_setup()).pack(side="left", padx=10, pady=5)
ctk.CTkButton(top_bar, text="📊 Thống kê", font=FONT_BODY, fg_color="transparent", command=show_statistics).pack(side="left", padx=10, pady=5)
ctk.CTkButton(top_bar, text="💾 Sao lưu", font=FONT_BODY, fg_color="transparent", command=backup_data).pack(side="left", padx=10, pady=5)
theme_menu = ctk.CTkOptionMenu(top_bar, values=["System", "Dark", "Light"], command=lambda m: ctk.set_appearance_mode(m), width=110)
theme_menu.pack(side="right", padx=10, pady=5)
theme_menu.set("Giao diện")

sidebar = ctk.CTkFrame(app, width=550, corner_radius=0, fg_color=BG_SIDEBAR)
sidebar.grid(row=1, column=0, sticky="nsew")
sidebar.grid_propagate(False)

ctk.CTkLabel(sidebar, text="V O C A B", font=("Segoe UI", 24, "bold"), text_color=COLOR_ACCENT).pack(pady=(30, 5))
ctk.CTkLabel(sidebar, text="Master Your English", font=FONT_BODY, text_color=TEXT_SUB).pack(pady=(0, 15))

add_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
add_frame.pack(fill="x", padx=20, pady=10)
entry_add = ctk.CTkEntry(add_frame, placeholder_text="Nhập nhanh 1 từ/cụm từ...", height=45, font=FONT_BODY)
entry_add.pack(side="left", fill="x", expand=True)
btn_add = ctk.CTkButton(add_frame, text="+", width=45, height=45, font=("Segoe UI", 24, "bold"), fg_color=COLOR_ACCENT, command=lambda: add_item())
btn_add.pack(side="right", padx=(10, 0))
app.bind('<Return>', lambda e: add_item())

sort_var = ctk.StringVar(value="Sắp xếp: Ngày học (Gần nhất)")
sort_options = ["Sắp xếp: Tên (A-Z)", "Sắp xếp: Ngày học (Gần nhất)", "Sắp xếp: Ngày học (Xa nhất)", "Sắp xếp: Số lần học (Nhiều nhất)", "Sắp xếp: Số lần học (Ít nhất)"]
def on_sort_change(choice):
    mapping = {"Sắp xếp: Tên (A-Z)": "name", "Sắp xếp: Ngày học (Gần nhất)": "recent", "Sắp xếp: Ngày học (Xa nhất)": "oldest", "Sắp xếp: Số lần học (Nhiều nhất)": "most", "Sắp xếp: Số lần học (Ít nhất)": "least"}
    (scroll_vocab if tab_view.get() == "Từ Đơn" else scroll_phrase).set_sort(mapping.get(choice, "recent"))
ctk.CTkOptionMenu(sidebar, variable=sort_var, values=sort_options, command=on_sort_change, font=FONT_BODY).pack(fill="x", padx=20, pady=(5,10))

tab_view = ctk.CTkTabview(sidebar, width=500)
tab_view.pack(fill="both", expand=True, padx=20, pady=5)
tab_view.add("Từ Đơn")
tab_view.add("Cụm Từ")

scroll_vocab = VirtualScrollList(tab_view.tab("Từ Đơn"), item_type='vocab', bg=BG_SIDEBAR[1])
scroll_vocab.pack(fill="both", expand=True)
scroll_phrase = VirtualScrollList(tab_view.tab("Cụm Từ"), item_type='phrase', bg=BG_SIDEBAR[1])
scroll_phrase.pack(fill="both", expand=True)

main_view = ctk.CTkFrame(app, corner_radius=0, fg_color=BG_MAIN)
main_view.grid(row=1, column=1, sticky="nsew")
# --- LÀM MỚI TOP BAR VỚI STREAK ---
lbl_streak = ctk.CTkLabel(top_bar, text="🔥 0 Ngày", font=("Segoe UI", 16, "bold"), text_color="#FF9500")
lbl_streak.pack(side="left", padx=20)

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
    lbl_title.configure(text=word.lower())
    lbl_vn.configure(text=detail['vn_meaning'].capitalize() if detail['vn_meaning'] else "")
    lbl_pos_text.configure(text=detail['pos'])
    lbl_ex.configure(text=f'"{detail["sentence"]}"')
    lbl_stats.configure(text=f"🔥 Số lần: {detail['study_count']}  •  🕒 Lần cuối: {detail['last_studied']}")
    lbl_alert.pack_forget()
    if detail['study_count'] >= 10 and detail['last_studied'] and (datetime.now() - datetime.strptime(detail['last_studied'], "%Y-%m-%d %H:%M")).days >= 3:
        lbl_alert.configure(text="🚨 Cảnh báo: Từ/Cụm này lâu rồi chưa ôn lại!")
        lbl_alert.pack(anchor="w", padx=25, pady=(10, 0))
    txt_note.delete("1.0", "end")
    txt_note.insert("1.0", detail.get("custom_sentence", ""))
    lbl_img.configure(image="", text="Đang tìm ảnh...")
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

c1 = ctk.CTkFrame(detail_container, corner_radius=15, fg_color="transparent")
c1.pack(fill="x", pady=(10, 20))
hl = ctk.CTkFrame(c1, fg_color="transparent")
hl.pack(side="left")
lbl_title = ctk.CTkLabel(hl, text="", font=FONT_TITLE, wraplength=400, justify="left")
lbl_title.pack(anchor="w")
vf = ctk.CTkFrame(hl, fg_color="transparent")
vf.pack(anchor="w")
lbl_vn = ctk.CTkLabel(vf, text="", font=FONT_VN, text_color=COLOR_SUCCESS[0], wraplength=350, justify="left")
lbl_vn.pack(side="left")
ctk.CTkButton(vf, text="✏️", width=30, height=30, fg_color="transparent", text_color=COLOR_ACCENT, command=edit_vn_meaning).pack(side="left", padx=(10, 0))
pf = ctk.CTkFrame(c1, corner_radius=20, fg_color=COLOR_ACCENT)
pf.pack(side="left", pady=(10,0), padx=20)
lbl_pos_text = ctk.CTkLabel(pf, text="", font=("Segoe UI", 14), text_color="white")
lbl_pos_text.pack(padx=15, pady=2)
ctk.CTkButton(c1, text="🔊 Nghe", width=100, height=40, corner_radius=20, fg_color=BG_CARD, command=lambda: play_sound_system(current_item) if current_item else None).pack(side="right", pady=20)

c2 = ctk.CTkFrame(detail_container, fg_color="transparent")
c2.pack(fill="x", pady=10)
img_f = ctk.CTkFrame(c2, corner_radius=15, fg_color=BG_CARD, width=180, height=180)
img_f.pack(side="left"); img_f.pack_propagate(False)
lbl_img = ctk.CTkLabel(img_f, text="⌛", font=FONT_BODY, text_color=TEXT_SUB)
lbl_img.pack(expand=True)
c2_info = ctk.CTkFrame(c2, corner_radius=15, fg_color=BG_CARD)
c2_info.pack(side="left", fill="both", expand=True, padx=(20, 0))
lbl_alert = ctk.CTkLabel(c2_info, text="", font=("Segoe UI", 13, "bold"), text_color=COLOR_DANGER[0])
lbl_stats = ctk.CTkLabel(c2_info, text="", font=FONT_BODY, text_color=TEXT_SUB)
lbl_stats.pack(anchor="w", padx=25, pady=(20, 5))
lbl_ex = ctk.CTkLabel(c2_info, text="", font=FONT_ITALIC, wraplength=450, justify="left")
lbl_ex.pack(anchor="w", padx=25, pady=(5, 15))
ctk.CTkButton(c2_info, text="▶ Nghe câu ví dụ", border_width=1, fg_color="transparent", command=lambda: play_sound_system(data_manager.get_detail(current_item, current_type)['sentence'] if current_item else "")).pack(anchor="w", padx=25)

c3 = ctk.CTkFrame(detail_container, corner_radius=15, fg_color=BG_CARD)
c3.pack(fill="x", pady=20)
ctk.CTkLabel(c3, text="📝 Ghi chú của bạn / Đặt câu tự do", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=25, pady=(20, 10))
txt_note = ctk.CTkTextbox(c3, height=100, corner_radius=8, fg_color=BG_MAIN, font=FONT_BODY)
txt_note.pack(fill="x", padx=25, pady=(0, 20))
bf = ctk.CTkFrame(c3, fg_color="transparent")
bf.pack(fill="x", padx=25, pady=(0, 25))
ctk.CTkButton(bf, text="💾 Lưu", fg_color=COLOR_SUCCESS, width=100, command=save_custom_note).pack(side="left")
ctk.CTkButton(bf, text="🗑 Xóa Mục", fg_color="transparent", text_color=COLOR_DANGER[0], border_width=1, border_color=COLOR_DANGER[0], width=80, command=item_delete_cmd).pack(side="right")

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

def get_game_data(source_type):
    today = datetime.now().strftime("%Y-%m-%d")
    items = []
    for t, data_dict in [('vocab', data_manager.vocab), ('phrase', data_manager.phrase)]:
        for word, d in data_dict.items():
            item_data = {"word": word, "vn_meaning": d['vn_meaning'], "sentence": d.get('sentence', ''), "item_type": t, "last_studied": d['last_studied'], "study_count": d['study_count']}
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
        card = ctk.CTkFrame(self, corner_radius=15, fg_color=BG_CARD)
        card.pack(fill="both", expand=True, padx=25, pady=25)

        ctk.CTkLabel(card, text="🎮 CÀI ĐẶT TRÒ CHƠI", font=("Segoe UI", 22, "bold"), text_color=COLOR_ACCENT).pack(pady=(25, 10))
        
        self.source_mode = ctk.CTkSegmentedButton(card, values=["Ngẫu nhiên", "Chưa ôn hôm nay"], font=FONT_BODY, command=self.update_slider_max)
        self.source_mode.set("Chưa ôn hôm nay")
        self.source_mode.pack(pady=10, fill="x", padx=40)
        
        self.lbl_empty_alert = ctk.CTkLabel(card, text="", text_color=COLOR_SUCCESS[0], font=("Segoe UI", 12, "italic"))
        self.lbl_empty_alert.pack()
        
        self.game_mode = ctk.CTkOptionMenu(card, values=["Trắc nghiệm", "Đảo chữ", "Nối từ", "Nghe & Gõ", "Điền Từ", "Sinh Tồn", "⚔️ RPG Đánh Boss", "🚀 Bắn Ruồi (Invaders)", "🥷 Ninja Vượt Ải"], font=("Segoe UI", 16))
        self.game_mode.set("Trắc nghiệm")
        self.game_mode.pack(pady=10, fill="x", padx=40)
        
        self.lbl_val = ctk.CTkLabel(card, text="5 Từ", font=("Segoe UI", 32, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_val.pack(pady=(15, 0))
        
        self.slider = ctk.CTkSlider(card, from_=1, to=10, number_of_steps=9, command=lambda v: self.lbl_val.configure(text=f"{int(v)} Từ"))
        self.slider.pack(fill="x", padx=50, pady=10)
        
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(pady=(20, 25), fill="x", padx=40)
        ctk.CTkButton(btn_frame, text="Hủy", width=120, height=40, fg_color="transparent", border_width=1, text_color=TEXT_SUB, command=self.destroy).pack(side="left")
        self.btn_start = ctk.CTkButton(btn_frame, text="Bắt đầu", width=120, height=40, font=("Segoe UI", 14, "bold"), fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.on_ok)
        self.btn_start.pack(side="right")
        
        self.update_slider_max(self.source_mode.get())
        self.wait_window()
    
    def update_slider_max(self, mode):
        data = get_game_data(mode)
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
        self.result_num, self.result_mode, self.result_data = int(self.slider.get()), self.game_mode.get(), get_game_data(self.source_mode.get())
        self.destroy()

def open_game_setup():
    d = GameSetupDialog(app)
    if d.result_num and d.result_data:
        if d.result_mode == "Trắc nghiệm": QuizGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Đảo chữ": ScrambleGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Nối từ": MatchGameWindow(app, min(d.result_num, 10), d.result_data)
        elif d.result_mode == "Nghe & Gõ": DictationGameWindow(app, d.result_num, d.result_data)
        elif d.result_mode == "Sinh Tồn": SurvivalGameWindow(app, d.result_data) # <--- Thêm dòng này
        elif d.result_mode == "⚔️ RPG Đánh Boss": RPGBossGameWindow(app, d.result_data)
        elif d.result_mode == "🚀 Bắn Ruồi (Invaders)": InvadersGameWindow(app, d.result_data)
        elif d.result_mode == "🥷 Ninja Vượt Ải": NinjaGameWindow(app, d.result_data)
        elif d.result_mode == "Điền Từ": ClozeGameWindow(app, d.result_num, d.result_data)

class BaseGameWindow(ctk.CTkToplevel):
    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.geometry("700x550") # To hơn cho thoáng
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
        self.game_area = ctk.CTkFrame(self, corner_radius=15, fg_color=BG_CARD)
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
            btn = ctk.CTkButton(self.btn_grid, text="", height=60, corner_radius=12, font=("Segoe UI", 16, "bold"), 
                                fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_ACCENT,
                                command=lambda idx=i: self.check(idx))
            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
            self.btn_opts.append(btn)

    def load(self):
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
            btn = ctk.CTkButton(self.btn_grid, text="", height=70, corner_radius=12, font=("Segoe UI", 18, "bold"), 
                                fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_ACCENT,
                                command=lambda idx=i: self.check(idx))
            btn.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
            self.btn_opts.append(btn)

    def next_round(self):
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
        
        self.entry = ctk.CTkEntry(self.game_area, font=("Segoe UI", 24, "bold"), justify="center", height=60, corner_radius=12)
        self.entry.pack(fill="x", padx=60, pady=10)
        self.entry.bind('<Return>', lambda e: self.check())
        
        bf = ctk.CTkFrame(self.game_area, fg_color="transparent")
        bf.pack(pady=20, fill="x", padx=60)
        ctk.CTkButton(bf, text="🔊 Nghe gợi ý", width=140, height=45, fg_color=BG_MAIN, text_color=("black", "white"), command=lambda: play_sound_system(self.questions[self.current_idx][0])).pack(side="left")
        ctk.CTkButton(bf, text="Kiểm tra", width=140, height=45, font=("Segoe UI", 14, "bold"), fg_color=COLOR_ACCENT, command=self.check).pack(side="right")

    def load(self):
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
        btn_play = ctk.CTkButton(self.game_area, text="▶ NGHE TỪ VỰNG", font=("Segoe UI", 24, "bold"), height=90, width=300, corner_radius=20, command=lambda: play_sound_system(self.questions[self.current_idx][0]))
        btn_play.pack(pady=(40, 20))
        
        self.lbl_hint = ctk.CTkLabel(self.game_area, text="---", font=("Segoe UI", 16, "italic"), text_color=TEXT_SUB, wraplength=500)
        self.lbl_hint.pack(pady=(0, 20))
        
        self.entry = ctk.CTkEntry(self.game_area, font=("Segoe UI", 24, "bold"), justify="center", height=60, corner_radius=12)
        self.entry.pack(fill="x", padx=60, pady=10)
        self.entry.bind('<Return>', lambda e: self.check())
        
        bf = ctk.CTkFrame(self.game_area, fg_color="transparent")
        bf.pack(pady=20, fill="x", padx=60)
        ctk.CTkButton(bf, text="💡 Gợi ý nghĩa", width=140, height=45, fg_color=BG_MAIN, text_color=("black", "white"), command=lambda: self.lbl_hint.configure(text=f"Nghĩa: {self.questions[self.current_idx][1].capitalize()}")).pack(side="left")
        ctk.CTkButton(bf, text="Kiểm tra", width=140, height=45, font=("Segoe UI", 14, "bold"), fg_color=COLOR_ACCENT, command=self.check).pack(side="right")

    def load(self):
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

        gf = ctk.CTkFrame(self, fg_color="transparent")
        gf.pack(fill="both", expand=True, padx=30, pady=20)
        gf.grid_columnconfigure(0, weight=1)
        gf.grid_columnconfigure(1, weight=1)
        
        el, vl = list(self.pairs), list(self.pairs)
        random.shuffle(el)
        random.shuffle(vl)
        
        fe = ctk.CTkFrame(gf, fg_color=BG_CARD, corner_radius=15)
        fe.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        fv = ctk.CTkFrame(gf, fg_color=BG_CARD, corner_radius=15)
        fv.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        for w, _, _ in el:
            b = ctk.CTkButton(fe, text=w.capitalize(), height=55, corner_radius=10, font=("Segoe UI", 16, "bold"), fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_ACCENT, command=lambda w=w: self.sel(w, 'en'))
            b.pack(fill="x", padx=15, pady=8)
            self.btn_en[w] = b
            
        for _, v, _ in vl:
            b = ctk.CTkButton(fv, text=v.capitalize(), height=55, corner_radius=10, font=("Segoe UI", 15), fg_color=BG_MAIN, text_color=("black", "white"), hover_color=COLOR_SUCCESS[0], command=lambda v=v: self.sel(v, 'vi'))
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
        ctk.CTkButton(bf, text="Hủy bỏ", width=100, fg_color="transparent", border_width=1, command=self.destroy).pack(side="left", padx=10)
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
                        conn.execute(f"INSERT INTO {r[1]} (word, sentence, pos, vn_meaning, custom_sentence, last_studied, study_count) VALUES (?,?,?,?,?,?,?)",
                                     (r[0], r[2], r[3], r[4], r[5], "", 0))
                    conn.commit()
                    conn.close()
            executor.submit(save_batch, results)
                
        app.after(0, lambda: self.finish(len(results)))
        
    def finish(self, added):
        if added == 0: self.lbl_status.configure(text="Tất cả từ đã có sẵn!", text_color="gray")
        else: self.lbl_status.configure(text=f"✅ Hoàn tất! Đã thêm cực nhanh {added} mục.", text_color=COLOR_SUCCESS[0])
        self.btn_start.configure(text="Đóng", state="normal", command=self.destroy)
        refresh_lists()

# ================== STATISTICS (TÍNH TOÁN TRỰC TIẾP TRÊN RAM SIÊU TỐC) ==================
class StatisticsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Thống Kê Học Tập")
        self.geometry("700x600")
        self.transient(master)
        
        # Đảm bảo cửa sổ luôn ở trên và nhận focus
        self.grab_set()
        self.focus_force()

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
                if c == 0:
                    unlearned += 1
                elif c >= 15:
                    mastered += 1

                # Tính cảnh báo (học >= 10 lần nhưng đã bỏ bê 3 ngày)
                if c >= 10 and item.get('last_studied'):
                    try:
                        # Chỉ lấy 10 ký tự đầu (YYYY-MM-DD) để so sánh ngày cho chuẩn xác
                        last_date = datetime.strptime(item['last_studied'][:10], "%Y-%m-%d")
                        if (datetime.now() - last_date).days >= 3:
                            warned += 1
                    except:
                        pass

        return total_vocab, total_phrase, studied_today, mastered, warned, unlearned

    def build_ui(self):
        ctk.CTkLabel(self, text="📊 TỔNG QUAN HỌC TẬP", font=("Segoe UI", 26, "bold"), text_color=COLOR_ACCENT).pack(pady=(30, 20))
        
        grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=30, pady=10)
        grid_frame.grid_columnconfigure(0, weight=1)
        grid_frame.grid_columnconfigure(1, weight=1)
        
        # Lấy dữ liệu ngay lập tức
        tv, tp, st, m, w, u = self.get_stats_from_ram()

        def create_card(row, col, title, value, color):
            card = ctk.CTkFrame(grid_frame, corner_radius=15, fg_color=BG_CARD)
            card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 15), text_color=TEXT_SUB).pack(pady=(25, 5))
            ctk.CTkLabel(card, text=str(value), font=("Segoe UI", 48, "bold"), text_color=color).pack(pady=(0, 25))

        create_card(0, 0, "📚 Tổng Từ Đơn", tv, COLOR_ACCENT)
        create_card(0, 1, "💬 Tổng Cụm Từ", tp, COLOR_ACCENT)
        create_card(1, 0, "🔥 Đã học hôm nay", st, COLOR_SUCCESS[0])
        create_card(1, 1, "✅ Đã thuộc (>15 lần)", m, COLOR_SUCCESS[0])
        create_card(2, 0, "🚨 Cảnh báo (Lâu chưa ôn)", w, COLOR_DANGER[0])
        create_card(2, 1, "🆕 Chưa học (0 lần)", u, "gray")

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
        self.geometry("450x480") # Tăng chiều cao để chứa thêm thanh trượt
        self.transient(master)
        self.grab_set()
        self.result_time = None
        self.result_data = None
        self.full_unstudied_list = [] # Lưu tạm toàn bộ danh sách chưa học
        
        card = ctk.CTkFrame(self, corner_radius=15, fg_color=BG_CARD)
        card.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(card, text="▶ HỌC TỪ TỰ ĐỘNG", font=("Segoe UI", 20, "bold"), text_color=COLOR_ACCENT).pack(pady=(15, 5))
        
        self.lbl_alert = ctk.CTkLabel(card, text="", text_color=COLOR_SUCCESS[0], font=("Segoe UI", 12, "italic"))
        self.lbl_alert.pack(pady=(0, 15))
        
        # --- 1. CHỌN SỐ LƯỢNG TỪ ---
        ctk.CTkLabel(card, text="Số lượng từ muốn học:", font=("Segoe UI", 14), text_color=TEXT_SUB).pack()
        self.lbl_word_count = ctk.CTkLabel(card, text="10 Từ", font=("Segoe UI", 24, "bold"), text_color=COLOR_ACCENT)
        self.lbl_word_count.pack()
        
        self.slider_words = ctk.CTkSlider(card, from_=1, to=10, command=lambda v: self.lbl_word_count.configure(text=f"{int(v)} Từ"))
        self.slider_words.pack(fill="x", padx=40, pady=(5, 20))
        
        # --- 2. CHỌN THỜI GIAN ---
        ctk.CTkLabel(card, text="Thời gian chuyển từ:", font=("Segoe UI", 14), text_color=TEXT_SUB).pack()
        self.lbl_time = ctk.CTkLabel(card, text="5 Giây", font=("Segoe UI", 24, "bold"), text_color=COLOR_SUCCESS[0])
        self.lbl_time.pack()
        
        self.slider_time = ctk.CTkSlider(card, from_=3, to=15, number_of_steps=12, command=lambda v: self.lbl_time.configure(text=f"{int(v)} Giây"))
        self.slider_time.pack(fill="x", padx=40, pady=(5, 15))
        self.slider_time.set(5)
        
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(pady=(10, 20), fill="x", padx=30)
        ctk.CTkButton(bf, text="Hủy", width=100, fg_color="transparent", border_width=1, command=self.destroy).pack(side="left")
        self.btn_start = ctk.CTkButton(bf, text="Bắt đầu", width=100, fg_color=COLOR_SUCCESS[0], hover_color="#28a745", command=self.on_start)
        self.btn_start.pack(side="right")
        
        self.prepare_data()
        self.wait_window()
        
    def prepare_data(self):
        today = datetime.now().strftime("%Y-%m-%d")
        unstudied = []
        for t, data_dict in [('vocab', data_manager.vocab), ('phrase', data_manager.phrase)]:
            for word, d in data_dict.items():
                if word not in data_manager.tracker.get(today, set()):
                    unstudied.append({"word": word, "vn_meaning": d['vn_meaning'], "sentence": d['sentence'], "item_type": t, "pos": d['pos']})
        
        if not unstudied:
            self.lbl_alert.configure(text="🎉 Tuyệt vời! Bạn đã học hết từ hôm nay.")
            self.slider_words.configure(state="disabled")
            self.slider_time.configure(state="disabled")
            self.btn_start.configure(state="disabled")
        else:
            # Ưu tiên xếp những từ có số lần học ít nhất lên đầu
            unstudied.sort(key=lambda x: data_manager.get_detail(x['word'], x['item_type'])['study_count'])
            self.full_unstudied_list = unstudied
            
            max_words = len(unstudied)
            self.lbl_alert.configure(text=f"Có {max_words} từ đang chờ bạn học.")
            
            # Cấu hình thanh trượt số lượng từ dựa trên số từ thực tế chưa học
            self.slider_words.configure(from_=1, to=max_words, number_of_steps=max_words-1 if max_words > 1 else 1)
            
            # Mặc định gợi ý học 10 từ (hoặc ít hơn nếu không đủ)
            default_val = min(10, max_words)
            self.slider_words.set(default_val)
            self.lbl_word_count.configure(text=f"{int(default_val)} Từ")

    def on_start(self):
        self.result_time = int(self.slider_time.get())
        num_words_to_learn = int(self.slider_words.get())
        
        # Cắt lấy đúng số lượng từ bạn đã chọn trên thanh trượt
        self.result_data = self.full_unstudied_list[:num_words_to_learn]
        
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
        self.card = ctk.CTkFrame(self, corner_radius=20, fg_color=BG_CARD)
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
        
        ctk.CTkButton(btn_frame, text="⏪ Trước", width=100, height=40, font=("Segoe UI", 14), command=self.prev_word).pack(side="left", padx=10)
        self.btn_pause = ctk.CTkButton(btn_frame, text="⏸ Tạm Dừng", width=120, height=40, font=("Segoe UI", 14, "bold"), fg_color="#FF9500", hover_color="#E08300", command=self.toggle_pause)
        self.btn_pause.pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Tiếp ⏩", width=100, height=40, font=("Segoe UI", 14), command=self.next_word).pack(side="left", padx=10)

    def load_word(self):
        if self.current_idx >= len(self.data):
            messagebox.showinfo("Hoàn thành", "Chúc mừng! Bạn đã ôn xong tất cả các từ trong danh sách.")
            self.on_close()
            return
            
        item = self.data[self.current_idx]
        self.lbl_progress.configure(text=f"Từ {self.current_idx + 1} / {len(self.data)}")
        self.lbl_word.configure(text=item['word'].capitalize())
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
        valid_data = [d for d in data if d.get('sentence') and "Chưa có ví dụ" not in d['sentence'] and d['word'].lower() in d['sentence'].lower()]
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
        ctk.CTkButton(bf, text="Kiểm tra", fg_color=COLOR_ACCENT, command=self.check).pack(side="left", padx=10)

    def load(self):
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
class RadioWindow(ctk.CTkToplevel):
    def __init__(self, master, data):
        super().__init__(master)
        self.title("📻 Đài Phát Thanh Từ Vựng")
        self.geometry("400x500")
        self.transient(master)
        
        self.data = data
        self.idx = 0
        self.is_playing = True
        self.timer_id = None
        
        self.build()
        self.play_next()

    def build(self):
        self.configure(fg_color="#1E1E24")
        ctk.CTkLabel(self, text="📻 VOCAB RADIO", font=("Courier New", 26, "bold"), text_color="#00FFFF").pack(pady=20)
        
        self.lbl_word = ctk.CTkLabel(self, text="Đang tải...", font=("Segoe UI", 40, "bold"), text_color="white")
        self.lbl_word.pack(pady=10)
        
        self.lbl_vn = ctk.CTkLabel(self, text="", font=("Segoe UI", 20), text_color="#34C759", wraplength=350)
        self.lbl_vn.pack(pady=5)
        
        self.lbl_ex = ctk.CTkLabel(self, text="", font=("Segoe UI", 16, "italic"), text_color="gray", wraplength=350)
        self.lbl_ex.pack(pady=20)
        
        self.btn_toggle = ctk.CTkButton(self, text="⏸ TẠM DỪNG", fg_color="#FF9500", font=("Segoe UI", 16, "bold"), command=self.toggle)
        self.btn_toggle.pack(pady=20)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def play_next(self):
        if not self.is_playing: return
        if self.idx >= len(self.data): self.idx = 0 # Phát lặp lại từ đầu
        
        item = self.data[self.idx]
        self.lbl_word.configure(text=item['word'].capitalize())
        self.lbl_vn.configure(text="")
        self.lbl_ex.configure(text="")
        
        # 1. Đọc tiếng Anh
        play_sound_system(item['word'])
        
        # 2. Đợi 2 giây, hiện tiếng Việt
        self.timer_id = self.after(2000, lambda: self.show_meaning(item))

    def show_meaning(self, item):
        if not self.is_playing: return
        self.lbl_vn.configure(text=item['vn_meaning'].capitalize())
        
        # 3. Đợi 2 giây, đọc câu ví dụ
        self.timer_id = self.after(2000, lambda: self.play_sentence(item))

    def play_sentence(self, item):
        if not self.is_playing: return
        if item.get('sentence') and "Chưa có" not in item['sentence']:
            self.lbl_ex.configure(text=f'"{item["sentence"]}"')
            play_sound_system(item['sentence'])
            delay = 5000 # Đợi lâu hơn vì câu ví dụ dài
        else:
            delay = 2000
            
        # 4. Chuyển sang từ tiếp theo
        self.idx += 1
        self.timer_id = self.after(delay, self.play_next)

    def toggle(self):
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.btn_toggle.configure(text="⏸ TẠM DỪNG", fg_color="#FF9500")
            self.play_next()
        else:
            self.btn_toggle.configure(text="▶ TIẾP TỤC", fg_color="#34C759")
            if self.timer_id: self.after_cancel(self.timer_id)

    def on_close(self):
        self.is_playing = False
        if self.timer_id: self.after_cancel(self.timer_id)
        self.destroy()
if __name__ == "__main__":
    app.mainloop()