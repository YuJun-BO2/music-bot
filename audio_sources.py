"""
Discord音樂機器人音源處理模組
處理YouTube、Spotify等音樂來源的搜尋和解析
"""

import asyncio
import logging
import shlex
from typing import List, Optional, Dict, Any

import yt_dlp
from youtubesearchpython import VideosSearch
import spotipy
from spotipy_anon import SpotifyAnon
import paramiko

from config import config

logger = logging.getLogger(__name__)

# 初始化Spotify客戶端
spotify = spotipy.Spotify(auth_manager=SpotifyAnon())

async def run_in_thread(func, *args):
    """在線程池中運行同步函數"""
    return await asyncio.to_thread(func, *args)

class AudioSourceError(Exception):
    """音源處理錯誤"""
    pass

class YouTubeHandler:
    """YouTube音源處理器"""
    
    @staticmethod
    async def extract_info(url: str) -> Dict[str, Any]:
        """提取YouTube影片資訊"""
        def _work():
            with yt_dlp.YoutubeDL(config.YTDL_OPTS) as ydl:
                return ydl.extract_info(url, download=False)
        
        try:
            return await asyncio.wait_for(
                run_in_thread(_work), 
                timeout=config.EXTRACT_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise AudioSourceError(f"影片解析超時 ({config.EXTRACT_TIMEOUT}s): {url}")
        except yt_dlp.utils.DownloadError as e:
            raise AudioSourceError(f"無法解析影片: {e}")
    
    @staticmethod
    async def get_playlist_urls(url: str, music: bool = False) -> List[str]:
        """取得播放列表中的所有影片URL"""
        opts = {**config.YTDL_OPTS, "extract_flat": "in_playlist"}
        
        def _work():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        try:
            data = await run_in_thread(_work)
            links = []
            
            for entry in data.get("entries", []):
                vid_id = entry.get("id")
                if vid_id:
                    base_url = "https://music.youtube.com/watch?v=" if music else "https://www.youtube.com/watch?v="
                    links.append(f"{base_url}{vid_id}")
            
            return links
            
        except Exception as e:
            logger.error(f"播放列表解析失敗: {e}")
            return []
    
    @staticmethod
    async def search_first(query: str) -> Optional[str]:
        """搜尋並返回第一個結果的URL"""
        def _work():
            try:
                search = VideosSearch(query, limit=1).result()
                results = search.get("result", [])
                return results[0]["link"] if results else None
            except Exception as e:
                logger.error(f"YouTube搜尋失敗: {e}")
                return None
        
        return await run_in_thread(_work)

class SpotifyHandler:
    """Spotify音源處理器"""
    
    @staticmethod
    async def get_track_info(url: str) -> Dict[str, str]:
        """取得Spotify單曲資訊"""
        try:
            track = await run_in_thread(spotify.track, url)
            return {
                "name": track["name"],
                "artist": track["artists"][0]["name"],
                "query": f'{track["name"]} {track["artists"][0]["name"]}'
            }
        except Exception as e:
            raise AudioSourceError(f"Spotify單曲解析失敗: {e}")
    
    @staticmethod
    async def get_playlist_tracks(url: str) -> List[str]:
        """取得Spotify播放列表中的所有搜尋查詢"""
        try:
            playlist = await run_in_thread(spotify.playlist, url)
            items = playlist.get("tracks", {}).get("items", [])
            
            queries = []
            for item in items:
                track = item.get("track")
                if track and track.get("name") and track.get("artists"):
                    query = f'{track["name"]} {track["artists"][0]["name"]}'
                    queries.append(query)
            
            return queries
            
        except Exception as e:
            raise AudioSourceError(f"Spotify播放列表解析失敗: {e}")

class SSHHandler:
    """SSH遠端處理器 (用於特殊功能)"""
    
    @staticmethod
    async def process_jable_url(url: str) -> tuple[List[str], List[str]]:
        """透過SSH處理特殊URL"""
        if not config.is_ssh_enabled():
            raise AudioSourceError("SSH功能未啟用或配置不完整")
        
        def _work():
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            try:
                ssh_config = config.get_ssh_config()
                connect_kwargs = {
                    'hostname': ssh_config['host'],
                    'port': ssh_config['port'],
                    'username': ssh_config['username']
                }
                
                # 使用私鑰檔案認證
                if 'key_filename' in ssh_config:
                    connect_kwargs['key_filename'] = ssh_config['key_filename']
                
                client.connect(**connect_kwargs)
                
                safe_url = shlex.quote(url)
                command = (
                    "cd /app && source venv/bin/activate && "
                    f"python main.py --url {safe_url} --encode 2 --output /downloads --no-prompt"
                )
                
                stdin, stdout, stderr = client.exec_command(command)
                output = stdout.read().decode().splitlines()[:20]
                errors = stderr.read().decode().splitlines()[:20]
                
                return output, errors
                
            finally:
                client.close()
        
        try:
            return await run_in_thread(_work)
        except Exception as e:
            raise AudioSourceError(f"SSH處理失敗: {e}")

class AudioSourceManager:
    """音源管理器，統一處理各種音源"""
    
    def __init__(self):
        self.youtube = YouTubeHandler()
        self.spotify = SpotifyHandler()
        self.ssh = SSHHandler()
    
    async def process_url(self, url_or_query: str) -> Dict[str, Any]:
        """處理URL或搜尋查詢，返回處理結果"""
        url_or_query = url_or_query.strip()
        
        # 判斷輸入類型並處理
        if "spotify.com/track" in url_or_query:
            return await self._process_spotify_track(url_or_query)
        elif "spotify.com/playlist" in url_or_query:
            return await self._process_spotify_playlist(url_or_query)
        elif "youtube.com" in url_or_query and "playlist" in url_or_query:
            return await self._process_youtube_playlist(url_or_query, music=False)
        elif "music.youtube.com" in url_or_query and "playlist" in url_or_query:
            return await self._process_youtube_playlist(url_or_query, music=True)
        elif url_or_query.startswith("http"):
            return await self._process_direct_url(url_or_query)
        else:
            return await self._process_search_query(url_or_query)
    
    async def _process_spotify_track(self, url: str) -> Dict[str, Any]:
        """處理Spotify單曲"""
        track_info = await self.spotify.get_track_info(url)
        youtube_url = await self.youtube.search_first(track_info["query"])
        
        if not youtube_url:
            raise AudioSourceError("找不到對應的YouTube影片")
        
        return {
            "type": "single",
            "source": "spotify",
            "title": f'{track_info["name"]} - {track_info["artist"]}',
            "urls": [youtube_url]
        }
    
    async def _process_spotify_playlist(self, url: str) -> Dict[str, Any]:
        """處理Spotify播放列表"""
        queries = await self.spotify.get_playlist_tracks(url)
        
        urls = []
        for query in queries:
            youtube_url = await self.youtube.search_first(query)
            if youtube_url:
                urls.append(youtube_url)
        
        if not urls:
            raise AudioSourceError("播放列表中沒有找到可播放的內容")
        
        return {
            "type": "playlist",
            "source": "spotify",
            "title": f"Spotify播放列表 ({len(urls)}首)",
            "urls": urls
        }
    
    async def _process_youtube_playlist(self, url: str, music: bool = False) -> Dict[str, Any]:
        """處理YouTube播放列表"""
        urls = await self.youtube.get_playlist_urls(url, music=music)
        
        if not urls:
            raise AudioSourceError("播放列表中沒有找到可播放的內容")
        
        source_name = "YouTube Music" if music else "YouTube"
        return {
            "type": "playlist",
            "source": "youtube",
            "title": f"{source_name}播放列表 ({len(urls)}首)",
            "urls": urls
        }
    
    async def _process_direct_url(self, url: str) -> Dict[str, Any]:
        """處理直接URL"""
        try:
            info = await self.youtube.extract_info(url)
            return {
                "type": "single",
                "source": "youtube",
                "title": info.get("title", "Unknown"),
                "urls": [url],
                "audio_url": info.get("url"),
                "info": info
            }
        except AudioSourceError:
            raise
    
    async def _process_search_query(self, query: str) -> Dict[str, Any]:
        """處理搜尋查詢"""
        url = await self.youtube.search_first(query)
        
        if not url:
            raise AudioSourceError(f"找不到搜尋結果: {query}")
        
        return await self._process_direct_url(url)

# 創建全域音源管理器實例
audio_source_manager = AudioSourceManager()