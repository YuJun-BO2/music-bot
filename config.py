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
    
    # SSH 設定 (用於特殊功能)
    SSH_HOST = os.getenv('SSH_HOST', '')
    SSH_PORT = int(os.getenv('SSH_PORT', '22'))
    SSH_USER = os.getenv('SSH_USER', '')
    SSH_PASS = os.getenv('SSH_PASS', '')
    
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
    
    @classmethod
    def validate(cls) -> bool:
        """驗證必要的配置是否完整"""
        if not cls.DISCORD_TOKEN:
            print("❌ 錯誤：DISCORD_TOKEN 未設定")
            return False
            
        # 檢查狀態文件目錄是否可寫
        try:
            cls.STATE_FILE.parent.mkdir(exist_ok=True)
        except Exception as e:
            print(f"❌ 錯誤：無法創建狀態文件目錄：{e}")
            return False
            
        return True
    
    @classmethod
    def get_ssh_config(cls) -> Dict[str, Any]:
        """獲取SSH配置字典"""
        return {
            'host': cls.SSH_HOST,
            'port': cls.SSH_PORT,
            'username': cls.SSH_USER,
            'password': cls.SSH_PASS,
        }
    
    @classmethod
    def is_ssh_enabled(cls) -> bool:
        """檢查SSH功能是否可用"""
        return bool(cls.SSH_HOST and cls.SSH_USER and cls.SSH_PASS)
    
    @classmethod
    def is_user_allowed(cls, user_id: int) -> bool:
        """檢查用戶是否有特殊功能權限"""
        return not cls.ALLOWED_IDS or user_id in cls.ALLOWED_IDS

# 創建全域配置實例
config = Config()