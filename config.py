"""
Discord音樂機器人配置管理模組
處理所有配置參數和環境變數
"""

import os
from typing import Dict, Any
from pathlib import Path

class Config:
    """配置管理類"""
    
    # Discord 設定
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')
    COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '/')
    
    # SSH 認證設定 (用於特殊功能)
    SSH_HOST = os.getenv('SSH_HOST', '')
    SSH_PORT = int(os.getenv('SSH_PORT', '22'))
    SSH_USER = os.getenv('SSH_USER', '')
    SSH_KEY_FILE = os.getenv('SSH_KEY_FILE', '')  # SSH 私鑰檔案路徑
    
    # 權限控制
    ALLOWED_IDS = set(map(int, os.getenv('ALLOWED_IDS', '').split(','))) if os.getenv('ALLOWED_IDS') else set()
    
    # 文件路徑
    STATE_FILE = Path(os.getenv('STATE_FILE', 'bot_state.json'))
    LOG_FILE = Path(os.getenv('LOG_FILE', 'musicbot.log'))
    
    # YouTube-DL 設定
    YTDL_OPTS = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "extractaudio": True,
        "audioformat": "mp3",
        "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
        "restrictfilenames": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "ignoreerrors": False,
        "logtostderr": False,
        "age_limit": None,
        "default_search": "auto",
        # 針對 YouTube 反機器人保護的設定
        "extractor_retries": 3,
        "fragment_retries": 3,
        "retry_sleep": 2,
        "sleep_interval": 1,
        "max_sleep_interval": 5,
        # 使用更多的備用提取器
        "youtube_include_dash_manifest": False,
        # 添加 User-Agent 來模擬正常瀏覽器
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        },
        # 使用備用搜索方法
        "default_search": "ytsearch",
    }
    
    # FFmpeg 設定
    FFMPEG_OPTS = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn -b:a 128k -threads 2",
    }
    
    # 播放設定
    MAX_QUEUE_SIZE = int(os.getenv('MAX_QUEUE_SIZE', '100'))
    MAX_HISTORY_SIZE = int(os.getenv('MAX_HISTORY_SIZE', '50'))
    MAX_BACK_HISTORY = int(os.getenv('MAX_BACK_HISTORY', '20'))
    
    # 超時設定
    EXTRACT_TIMEOUT = int(os.getenv('EXTRACT_TIMEOUT', '30'))
    CONNECT_TIMEOUT = int(os.getenv('CONNECT_TIMEOUT', '15'))
    KEEPALIVE_INTERVAL = int(os.getenv('KEEPALIVE_INTERVAL', '240'))  # 4分鐘
    
    # YouTube Cookies 設定（可選，用於繞過反機器人檢查）
    YOUTUBE_COOKIES_FILE = os.getenv('YOUTUBE_COOKIES_FILE', '')
    
    @classmethod
    def get_ytdl_opts_with_cookies(cls) -> Dict[str, Any]:
        """獲取包含 cookies 的 yt-dlp 選項"""
        opts = cls.YTDL_OPTS.copy()
        
        # 如果有 cookies 文件，添加到選項中
        if cls.YOUTUBE_COOKIES_FILE and os.path.exists(cls.YOUTUBE_COOKIES_FILE):
            opts['cookiefile'] = cls.YOUTUBE_COOKIES_FILE
            
        return opts
    
    @classmethod
    def validate(cls) -> bool:
        """驗證必要的配置是否完整"""
        if not cls.DISCORD_TOKEN:
            print("錯誤：DISCORD_TOKEN 未設定")
            return False
            
        # 檢查狀態文件目錄是否可寫
        try:
            cls.STATE_FILE.parent.mkdir(exist_ok=True)
        except Exception as e:
            print(f"錯誤：無法創建狀態文件目錄：{e}")
            return False
            
        return True
    
    @classmethod
    def get_ssh_config(cls) -> Dict[str, Any]:
        """獲取SSH配置字典"""
        config = {
            'host': cls.SSH_HOST,
            'port': cls.SSH_PORT,
            'username': cls.SSH_USER,
        }
        
        # 優先使用私鑰檔案認證
        if cls.SSH_KEY_FILE and os.path.exists(cls.SSH_KEY_FILE):
            config['key_filename'] = cls.SSH_KEY_FILE
        
        return config
    
    @classmethod
    def is_ssh_enabled(cls) -> bool:
        """檢查SSH功能是否可用"""
        return bool(cls.SSH_HOST and cls.SSH_USER and 
                   (cls.SSH_KEY_FILE and os.path.exists(cls.SSH_KEY_FILE)))
    
    @classmethod
    def is_user_allowed(cls, user_id: int) -> bool:
        """檢查用戶是否有特殊功能權限"""
        return not cls.ALLOWED_IDS or user_id in cls.ALLOWED_IDS

# 創建全域配置實例
config = Config()