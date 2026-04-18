
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "vocab.db")
CACHE_DIR = os.path.join(BASE_DIR, "image_cache")
AUDIO_CACHE_DIR = os.path.join(BASE_DIR, "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)