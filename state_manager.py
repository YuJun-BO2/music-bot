"""
Discord音樂機器人狀態管理模組
處理多伺服器狀態的保存、載入和查詢
"""

import json
import logging
from typing import Dict, List, Set, Any
from collections import defaultdict
from config import config

logger = logging.getLogger(__name__)

class StateManager:
    """狀態管理器，處理多伺服器的所有狀態"""
    
    def __init__(self):
        # 所有狀態按 guild_id 分組
        self.guild_queues: Dict[int, List[str]] = defaultdict(list)
        self.guild_played: Dict[int, List[str]] = defaultdict(list)
        self.guild_current: Dict[int, Dict[str, Any]] = defaultdict(dict)
        self.guild_blacklist: Dict[int, Set[str]] = defaultdict(set)
        self.guild_back_count: Dict[int, int] = defaultdict(int)
        self.guild_back_history: Dict[int, List[str]] = defaultdict(list)
    
    def get_queue(self, guild_id: int) -> List[str]:
        """取得指定伺服器的音樂隊列"""
        return self.guild_queues[guild_id]
    
    def get_played(self, guild_id: int) -> List[str]:
        """取得指定伺服器的已播放歷史"""
        return self.guild_played[guild_id]
    
    def get_current(self, guild_id: int) -> Dict[str, Any]:
        """取得指定伺服器的當前播放資訊"""
        if guild_id not in self.guild_current:
            self.guild_current[guild_id] = {
                "url": None,
                "title": None,
                "channel_id": None,
                "position": 0,
                "from_back": False,
                "processing_back": False,
            }
        return self.guild_current[guild_id]
    
    def get_blacklist(self, guild_id: int) -> Set[str]:
        """取得指定伺服器的失效影片黑名單"""
        return self.guild_blacklist[guild_id]
    
    def get_back_count(self, guild_id: int) -> int:
        """取得指定伺服器的回退步數計數"""
        return self.guild_back_count[guild_id]
    
    def get_back_history(self, guild_id: int) -> List[str]:
        """取得指定伺服器的 back 歷史堆疊"""
        return self.guild_back_history[guild_id]
    
    def add_to_queue(self, guild_id: int, item: str) -> int:
        """添加項目到隊列，返回新的隊列長度"""
        queue = self.get_queue(guild_id)
        if len(queue) >= config.MAX_QUEUE_SIZE:
            raise ValueError(f"隊列已滿 (最大 {config.MAX_QUEUE_SIZE} 首)")
        queue.append(item)
        return len(queue)
    
    def add_to_played(self, guild_id: int, url: str):
        """添加到播放歷史，自動維護最大長度"""
        played = self.get_played(guild_id)
        played.append(url)
        if len(played) > config.MAX_HISTORY_SIZE:
            played.pop(0)  # 移除最舊的記錄
    
    def add_to_blacklist(self, guild_id: int, url: str):
        """添加失效URL到黑名單"""
        self.get_blacklist(guild_id).add(url)
        logger.info(f"Guild {guild_id}: 已將URL加入黑名單: {url[-30:]}")
    
    def is_blacklisted(self, guild_id: int, url: str) -> bool:
        """檢查URL是否在黑名單中"""
        return url in self.get_blacklist(guild_id)
    
    def clear_queue(self, guild_id: int) -> int:
        """清空隊列，返回清除的數量"""
        queue = self.get_queue(guild_id)
        count = len(queue)
        queue.clear()
        return count
    
    def remove_from_queue(self, guild_id: int, count: int = 1) -> int:
        """從隊列前面移除指定數量的項目，返回實際移除的數量"""
        queue = self.get_queue(guild_id)
        removed = min(count, len(queue))
        for _ in range(removed):
            if queue:
                queue.pop(0)
        return removed
    
    def get_queue_status(self, guild_id: int) -> Dict[str, Any]:
        """獲取隊列狀態概覽"""
        return {
            "queue_length": len(self.get_queue(guild_id)),
            "played_count": len(self.get_played(guild_id)),
            "blacklist_count": len(self.get_blacklist(guild_id)),
            "current_playing": self.get_current(guild_id).get("title", "無"),
            "back_history_length": len(self.get_back_history(guild_id)),
        }
    
    def save_state(self) -> bool:
        """保存所有伺服器的播放狀態到文件"""
        try:
            state = {
                "guild_queues": {str(k): v for k, v in self.guild_queues.items()},
                "guild_played": {str(k): v[-config.MAX_HISTORY_SIZE:] for k, v in self.guild_played.items()},
                "guild_current": {str(k): v for k, v in self.guild_current.items()},
                "guild_blacklist": {str(k): list(v) for k, v in self.guild_blacklist.items()},
                "guild_back_count": {str(k): v for k, v in self.guild_back_count.items()},
                "guild_back_history": {str(k): v[-config.MAX_BACK_HISTORY:] for k, v in self.guild_back_history.items()},
            }
            
            config.STATE_FILE.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.debug("狀態保存完成")
            return True
            
        except Exception as e:
            logger.error(f"保存狀態失敗：{e}")
            return False
    
    def load_state(self) -> bool:
        """從文件載入所有伺服器的播放狀態"""
        if not config.STATE_FILE.exists():
            logger.info("狀態文件不存在，使用空狀態")
            return True
            
        try:
            state = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
            
            # 載入各種狀態
            self.guild_queues = defaultdict(list, {
                int(k): v for k, v in state.get("guild_queues", {}).items()
            })
            self.guild_played = defaultdict(list, {
                int(k): v for k, v in state.get("guild_played", {}).items()
            })
            self.guild_current = defaultdict(dict, {
                int(k): v for k, v in state.get("guild_current", {}).items()
            })
            self.guild_blacklist = defaultdict(set, {
                int(k): set(v) for k, v in state.get("guild_blacklist", {}).items()
            })
            self.guild_back_count = defaultdict(int, {
                int(k): v for k, v in state.get("guild_back_count", {}).items()
            })
            self.guild_back_history = defaultdict(list, {
                int(k): v for k, v in state.get("guild_back_history", {}).items()
            })
            
            logger.info("成功載入已保存的播放狀態")
            return True
            
        except Exception as e:
            logger.warning(f"載入狀態失敗：{e}")
            return False
    
    def cleanup_guild(self, guild_id: int):
        """清理指定伺服器的所有狀態"""
        if guild_id in self.guild_queues:
            del self.guild_queues[guild_id]
        if guild_id in self.guild_played:
            del self.guild_played[guild_id]
        if guild_id in self.guild_current:
            del self.guild_current[guild_id]
        if guild_id in self.guild_blacklist:
            del self.guild_blacklist[guild_id]
        if guild_id in self.guild_back_count:
            del self.guild_back_count[guild_id]
        if guild_id in self.guild_back_history:
            del self.guild_back_history[guild_id]
        
        logger.info(f"已清理伺服器 {guild_id} 的所有狀態")

# 創建全域狀態管理器實例
state_manager = StateManager()