"""
Discord音樂機器人單元測試
測試核心功能模組
"""

import unittest
import asyncio
import tempfile
import json
import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

# 設定測試環境
os.environ['DISCORD_TOKEN'] = 'test_token'
os.environ['STATE_FILE'] = 'test_state.json'

try:
    from config import config, Config
    from state_manager import StateManager
    from audio_sources import AudioSourceManager, AudioSourceError
except ImportError as e:
    print(f"警告: 無法導入模組 {e}")
    print("這可能是因為缺少依賴套件，跳過相關測試")
    # 創建空的測試類別以避免完全失敗
    config = None
    StateManager = None
    AudioSourceManager = None
    AudioSourceError = Exception

class TestConfig(unittest.TestCase):
    """測試配置模組"""
    
    def setUp(self):
        """設定測試"""
        if config is None:
            self.skipTest("Config 模組無法導入")
    
    def test_config_validation_with_token(self):
        """測試有效Token的配置驗證"""
        # 暫時設定Token
        original_token = config.DISCORD_TOKEN
        config.DISCORD_TOKEN = "test_token_123"
        
        try:
            self.assertTrue(config.validate())
        finally:
            config.DISCORD_TOKEN = original_token
    
    def test_config_validation_without_token(self):
        """測試無Token的配置驗證"""
        original_token = Config.DISCORD_TOKEN
        Config.DISCORD_TOKEN = ""
        
        try:
            self.assertFalse(config.validate())
        finally:
            Config.DISCORD_TOKEN = original_token
    
    def test_ssh_config(self):
        """測試SSH配置"""
        ssh_config = config.get_ssh_config()
        self.assertIsInstance(ssh_config, dict)
        self.assertIn('host', ssh_config)
        self.assertIn('port', ssh_config)
        self.assertIn('username', ssh_config)
        
        # 檢查認證方式：應該有私鑰檔案路徑（如果SSH_KEY_FILE存在且文件存在）
        if config.SSH_KEY_FILE and os.path.exists(config.SSH_KEY_FILE):
            self.assertIn('key_filename', ssh_config)
            self.assertEqual(ssh_config['key_filename'], config.SSH_KEY_FILE)
    
    def test_user_permission(self):
        """測試用戶權限檢查"""
        # 空白ALLOWED_IDS應該允許所有用戶
        original_ids = config.ALLOWED_IDS
        config.ALLOWED_IDS = set()
        
        try:
            self.assertTrue(config.is_user_allowed(12345))
        finally:
            config.ALLOWED_IDS = original_ids

class TestStateManager(unittest.TestCase):
    """測試狀態管理模組"""
    
    def setUp(self):
        """測試設定"""
        if StateManager is None:
            self.skipTest("StateManager 模組無法導入")
        self.state_manager = StateManager()
        self.test_guild_id = 12345
    
    def test_queue_operations(self):
        """測試隊列操作"""
        guild_id = self.test_guild_id
        
        # 測試空隊列
        queue = self.state_manager.get_queue(guild_id)
        self.assertEqual(len(queue), 0)
        
        # 測試添加項目
        length = self.state_manager.add_to_queue(guild_id, "test_url_1")
        self.assertEqual(length, 1)
        
        length = self.state_manager.add_to_queue(guild_id, "test_url_2")
        self.assertEqual(length, 2)
        
        # 測試獲取隊列
        queue = self.state_manager.get_queue(guild_id)
        self.assertEqual(queue, ["test_url_1", "test_url_2"])
        
        # 測試移除項目
        removed = self.state_manager.remove_from_queue(guild_id, 1)
        self.assertEqual(removed, 1)
        
        queue = self.state_manager.get_queue(guild_id)
        self.assertEqual(queue, ["test_url_2"])
    
    def test_played_history(self):
        """測試播放歷史"""
        guild_id = self.test_guild_id
        
        # 添加播放歷史
        self.state_manager.add_to_played(guild_id, "played_url_1")
        self.state_manager.add_to_played(guild_id, "played_url_2")
        
        played = self.state_manager.get_played(guild_id)
        self.assertEqual(played, ["played_url_1", "played_url_2"])
    
    def test_blacklist(self):
        """測試黑名單功能"""
        guild_id = self.test_guild_id
        test_url = "http://invalid.url"
        
        # 測試添加到黑名單
        self.assertFalse(self.state_manager.is_blacklisted(guild_id, test_url))
        
        self.state_manager.add_to_blacklist(guild_id, test_url)
        self.assertTrue(self.state_manager.is_blacklisted(guild_id, test_url))
    
    def test_current_info(self):
        """測試當前播放資訊"""
        guild_id = self.test_guild_id
        
        current = self.state_manager.get_current(guild_id)
        self.assertIsInstance(current, dict)
        self.assertIn("url", current)
        self.assertIn("title", current)
        self.assertIn("channel_id", current)
    
    def test_queue_status(self):
        """測試隊列狀態概覽"""
        guild_id = self.test_guild_id
        
        # 添加一些測試資料
        self.state_manager.add_to_queue(guild_id, "test_url")
        self.state_manager.add_to_played(guild_id, "played_url")
        self.state_manager.add_to_blacklist(guild_id, "bad_url")
        
        status = self.state_manager.get_queue_status(guild_id)
        
        self.assertEqual(status["queue_length"], 1)
        self.assertEqual(status["played_count"], 1)
        self.assertEqual(status["blacklist_count"], 1)
    
    def test_save_and_load_state(self):
        """測試狀態保存和載入"""
        guild_id = self.test_guild_id
        
        # 創建測試狀態
        self.state_manager.add_to_queue(guild_id, "test_save_url")
        self.state_manager.add_to_played(guild_id, "test_played_url")
        
        # 使用臨時文件進行測試
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = Path(f.name)
        
        try:
            # 暫時更改狀態文件路徑
            original_file = config.STATE_FILE
            config.STATE_FILE = temp_file
            
            # 測試保存
            self.assertTrue(self.state_manager.save_state())
            self.assertTrue(temp_file.exists())
            
            # 測試載入
            new_state_manager = StateManager()
            self.assertTrue(new_state_manager.load_state())
            
            # 驗證資料是否正確載入
            self.assertEqual(
                new_state_manager.get_queue(guild_id),
                ["test_save_url"]
            )
            self.assertEqual(
                new_state_manager.get_played(guild_id),
                ["test_played_url"]
            )
            
        finally:
            # 恢復原始設定並清理
            config.STATE_FILE = original_file
            if temp_file.exists():
                temp_file.unlink()

class TestAudioSources(unittest.IsolatedAsyncioTestCase):
    """測試音源處理模組"""
    
    def setUp(self):
        """測試設定"""
        if AudioSourceManager is None:
            self.skipTest("AudioSourceManager 模組無法導入")
        self.audio_manager = AudioSourceManager()
    
    async def test_process_search_query(self):
        """測試搜尋查詢處理"""
        # Mock YouTube搜尋結果
        with patch.object(self.audio_manager.youtube, 'search_first') as mock_search:
            mock_search.return_value = "https://www.youtube.com/watch?v=test123"
            
            with patch.object(self.audio_manager.youtube, 'extract_info') as mock_extract:
                mock_extract.return_value = {
                    "title": "Test Song",
                    "url": "http://audio.url"
                }
                
                result = await self.audio_manager.process_url("test song")
                
                self.assertEqual(result["type"], "single")
                self.assertEqual(result["source"], "youtube")
                self.assertEqual(result["title"], "Test Song")
    
    async def test_process_direct_url(self):
        """測試直接URL處理"""
        test_url = "https://www.youtube.com/watch?v=test123"
        
        with patch.object(self.audio_manager.youtube, 'extract_info') as mock_extract:
            mock_extract.return_value = {
                "title": "Direct Video",
                "url": "http://direct.audio.url"
            }
            
            result = await self.audio_manager.process_url(test_url)
            
            self.assertEqual(result["type"], "single")
            self.assertEqual(result["title"], "Direct Video")
            self.assertEqual(result["urls"], [test_url])
    
    async def test_spotify_track_processing(self):
        """測試Spotify單曲處理"""
        spotify_url = "https://open.spotify.com/track/test123"
        
        with patch.object(self.audio_manager.spotify, 'get_track_info') as mock_track:
            mock_track.return_value = {
                "name": "Spotify Song",
                "artist": "Test Artist",
                "query": "Spotify Song Test Artist"
            }
            
            with patch.object(self.audio_manager.youtube, 'search_first') as mock_search:
                mock_search.return_value = "https://www.youtube.com/watch?v=converted123"
                
                result = await self.audio_manager.process_url(spotify_url)
                
                self.assertEqual(result["type"], "single")
                self.assertEqual(result["source"], "spotify")
                self.assertEqual(result["title"], "Spotify Song - Test Artist")
    
    async def test_playlist_processing(self):
        """測試播放列表處理"""
        playlist_url = "https://www.youtube.com/playlist?list=test123"
        
        with patch.object(self.audio_manager.youtube, 'get_playlist_urls') as mock_playlist:
            mock_playlist.return_value = [
                "https://www.youtube.com/watch?v=song1",
                "https://www.youtube.com/watch?v=song2"
            ]
            
            result = await self.audio_manager.process_url(playlist_url)
            
            self.assertEqual(result["type"], "playlist")
            self.assertEqual(result["source"], "youtube")
            self.assertEqual(len(result["urls"]), 2)
    
    async def test_error_handling(self):
        """測試錯誤處理"""
        with patch.object(self.audio_manager.youtube, 'search_first') as mock_search:
            mock_search.return_value = None
            
            with self.assertRaises(AudioSourceError):
                await self.audio_manager.process_url("invalid search query")

class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """整合測試"""
    
    def setUp(self):
        """測試設定"""
        if StateManager is None:
            self.skipTest("StateManager 模組無法導入")
        self.state_manager = StateManager()
        self.guild_id = 12345
    
    async def test_queue_to_blacklist_flow(self):
        """測試從隊列到黑名單的流程"""
        test_url = "http://invalid.video.url"
        
        # 添加到隊列
        self.state_manager.add_to_queue(self.guild_id, test_url)
        queue = self.state_manager.get_queue(self.guild_id)
        self.assertEqual(len(queue), 1)
        
        # 模擬播放失敗，添加到黑名單
        self.state_manager.add_to_blacklist(self.guild_id, test_url)
        
        # 檢查黑名單
        self.assertTrue(self.state_manager.is_blacklisted(self.guild_id, test_url))
        
        # 從隊列移除
        self.state_manager.remove_from_queue(self.guild_id, 1)
        queue = self.state_manager.get_queue(self.guild_id)
        self.assertEqual(len(queue), 0)

def run_tests():
    """運行所有測試"""
    print("運行Discord音樂機器人單元測試")
    print("=" * 50)
    
    # 創建測試套件
    test_suite = unittest.TestSuite()
    
    # 添加測試類
    test_classes = [
        TestConfig,
        TestStateManager,
        TestAudioSources,
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # 運行測試
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # 返回測試結果
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)