"""
Discord音樂機器人播放核心模組
處理音樂播放、隊列管理和播放控制
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from collections import defaultdict

import discord
from discord.ext import commands

from config import config
from state_manager import state_manager
from audio_sources import audio_source_manager, AudioSourceError

logger = logging.getLogger(__name__)

# 每個guild的播放鎖
play_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

class VoiceManager:
    """語音連接管理器"""
    
    @staticmethod
    async def ensure_idle(vc: discord.VoiceClient, timeout: float = 3.0):
        """確保語音客戶端處於空閒狀態"""
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        
        start = asyncio.get_event_loop().time()
        while vc and (vc.is_playing() or vc.is_paused()) and \
              (asyncio.get_event_loop().time() - start) < timeout:
            await asyncio.sleep(0.05)
    
    @staticmethod
    async def get_safe_voice_client(ctx: commands.Context) -> Optional[discord.VoiceClient]:
        """獲取安全的語音客戶端"""
        vc = ctx.voice_client
        if vc is None or not vc.is_connected():
            await ctx.send("❌ Bot 尚未連線語音頻道，請先使用 `/join`")
            return None
        
        await VoiceManager.ensure_idle(vc)
        return vc
    
    @staticmethod
    async def safe_connect(channel: discord.VoiceChannel, retry: int = 5) -> discord.VoiceClient:
        """安全連接到語音頻道，支援重試"""
        for i in range(retry):
            try:
                logger.info(f"嘗試連接語音頻道 ({i+1}/{retry}): {channel.name}")
                
                vc = await asyncio.wait_for(
                    channel.connect(), 
                    timeout=config.CONNECT_TIMEOUT
                )
                
                await asyncio.sleep(2.0)  # 等待連接穩定
                
                if vc.is_connected():
                    logger.info(f"語音連接成功: {channel.name}")
                    return vc
                else:
                    logger.warning("連接狀態檢查失敗，重試...")
                    if vc:
                        try:
                            await vc.disconnect()
                        except:
                            pass
                            
            except asyncio.TimeoutError:
                logger.warning(f"語音連接超時 ({i+1}/{retry})")
            except Exception as e:
                logger.warning(f"語音連接失敗 ({i+1}/{retry}): {e}")
                
            if i < retry - 1:
                wait_time = min(5, 2 * (i + 1))
                logger.info(f"等待 {wait_time} 秒後重試...")
                await asyncio.sleep(wait_time)
        
        raise RuntimeError(f"多次嘗試後仍無法連接到語音頻道: {channel.name}")
    
    @staticmethod
    async def keep_alive(vc: discord.VoiceClient, guild_id: int):
        """防斷線保持連接"""
        silent_source = discord.FFmpegPCMAudio(
            "anullsrc=r=48000:cl=stereo",
            before_options="-f lavfi -t 1",
            options="-loglevel quiet"
        )
        
        while not vc.is_closed():
            await asyncio.sleep(config.KEEPALIVE_INTERVAL)
            
            if not vc.is_connected():
                continue
            if vc.is_playing() or vc.is_paused():
                continue
            
            lock = play_locks[guild_id]
            if lock.locked():
                continue
            
            async with lock:
                if not vc.is_playing() and not vc.is_paused():
                    vc.play(silent_source, after=lambda *_: None)

class MusicPlayer:
    """音樂播放器核心"""
    
    def __init__(self):
        self.voice_manager = VoiceManager()
    
    async def stream_play(self, ctx: commands.Context, url: str) -> bool:
        """播放音樂流"""
        guild_id = ctx.guild.id
        
        # 檢查黑名單
        if state_manager.is_blacklisted(guild_id, url):
            logger.info(f"URL在黑名單中，跳過: {url}")
            await ctx.send("⚠️ 此影片已知無效，已跳過")
            await self.play_next(ctx)
            return False
        
        lock = play_locks[guild_id]
        if lock.locked():
            logger.info(f"播放鎖被佔用，跳過: {url}")
            return False
        
        async with lock:
            try:
                vc = await self.voice_manager.get_safe_voice_client(ctx)
                if vc is None:
                    return False
                
                # 解析音源
                try:
                    result = await audio_source_manager.process_url(url)
                    
                    if result["type"] != "single":
                        raise AudioSourceError("期望單一音源")
                    
                    audio_url = result.get("audio_url")
                    title = result.get("title", "Unknown")
                    
                    if not audio_url:
                        raise AudioSourceError("找不到音訊來源")
                    
                except AudioSourceError as e:
                    logger.warning(f"音源解析失敗: {e}")
                    await ctx.send(f"⚠️ 無法播放（已跳過）：{e}")
                    
                    # 加入黑名單
                    state_manager.add_to_blacklist(guild_id, url)
                    
                    # 從隊列移除
                    queue = state_manager.get_queue(guild_id)
                    if queue and queue[0] == url:
                        queue.pop(0)
                    
                    # 清理當前狀態
                    current = state_manager.get_current(guild_id)
                    current["url"] = current["title"] = None
                    
                    state_manager.save_state()
                    await self.play_next(ctx)
                    return False
                
                # 創建音訊源
                source = discord.FFmpegPCMAudio(audio_url, **config.FFMPEG_OPTS)
                if source is None:
                    await ctx.send("⚠️ FFmpeg 無法建立音源，已跳過")
                    await self.play_next(ctx)
                    return False
                
                # 更新當前播放狀態
                current = state_manager.get_current(guild_id)
                current.update({
                    "url": url,
                    "title": title,
                    "channel_id": ctx.channel.id,
                    "position": 0
                })
                state_manager.save_state()
                
                # 創建播放完成回調
                def after_callback(error=None):
                    asyncio.run_coroutine_threadsafe(
                        self._handle_playback_finished(ctx, url, error),
                        ctx.bot.loop
                    )
                
                # 開始播放
                vc.play(source, after=after_callback)
                await ctx.send(f"🎵 {title}")
                logger.info(f"開始播放: {title}")
                return True
                
            except Exception as e:
                logger.error(f"播放過程中發生錯誤: {e}")
                await ctx.send(f"⚠️ 播放時發生錯誤：{e}")
                return False
    
    async def _handle_playback_finished(self, ctx: commands.Context, url: str, error: Optional[Exception]):
        """處理播放完成"""
        guild_id = ctx.guild.id
        
        logger.info(f"播放完成: {url}")
        
        if error:
            logger.error(f"播放錯誤: {error}")
            await ctx.send(f"⚠️ 播放失敗：{error}")
        
        # 獲取當前狀態
        current = state_manager.get_current(guild_id)
        is_from_back = current.get("from_back", False)
        
        # 從隊列移除
        queue = state_manager.get_queue(guild_id)
        if queue and queue[0] == url:
            queue.pop(0)
        
        # 添加到播放歷史（僅非back播放）
        if not is_from_back:
            state_manager.add_to_played(guild_id, url)
            logger.info(f"已加入播放歷史: {url}")
        else:
            logger.info(f"來自/back指令，不加入歷史")
        
        # 清理當前狀態
        current["url"] = current["title"] = None
        current["from_back"] = False
        current["processing_back"] = False
        
        state_manager.save_state()
        
        # 繼續播放下一首
        if queue or is_from_back:
            await self.play_next(ctx)
    
    async def play_next(self, ctx: commands.Context) -> bool:
        """播放下一首歌"""
        guild_id = ctx.guild.id
        queue = state_manager.get_queue(guild_id)
        current = state_manager.get_current(guild_id)
        
        if not queue:
            current["url"] = current["title"] = None
            state_manager.save_state()
            await ctx.send("🎵 隊列已空")
            return False
        
        # 取出隊首
        next_url = queue.pop(0)
        state_manager.save_state()
        
        logger.info(f"播放下一首: {next_url}")
        
        try:
            # 處理不同類型的URL
            result = await audio_source_manager.process_url(next_url)
            
            if result["type"] == "single":
                return await self.stream_play(ctx, next_url)
            elif result["type"] == "playlist":
                # 播放列表處理
                urls = result["urls"]
                if urls:
                    # 將播放列表添加到隊列開頭
                    for url in reversed(urls):
                        queue.insert(0, url)
                    state_manager.save_state()
                    
                    await ctx.send(f"📝 已加入 {len(urls)} 首歌曲")
                    return await self.play_next(ctx)
                else:
                    await ctx.send("❌ 播放列表為空")
                    return await self.play_next(ctx)
            
        except AudioSourceError as e:
            await ctx.send(f"❌ 播放時發生錯誤：{e}")
            return await self.play_next(ctx)
        except Exception as e:
            logger.error(f"播放下一首時發生錯誤: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
            return await self.play_next(ctx)
        
        return False
    
    async def add_to_queue(self, ctx: commands.Context, url_or_query: str) -> bool:
        """添加項目到播放隊列"""
        guild_id = ctx.guild.id
        
        try:
            result = await audio_source_manager.process_url(url_or_query)
            
            if result["type"] == "single":
                queue_pos = state_manager.add_to_queue(guild_id, url_or_query)
                await ctx.send(f"✅ 已加入隊列第 {queue_pos} 位")
                return True
                
            elif result["type"] == "playlist":
                urls = result["urls"]
                count = 0
                for url in urls:
                    try:
                        state_manager.add_to_queue(guild_id, url)
                        count += 1
                    except ValueError:
                        break  # 隊列已滿
                
                await ctx.send(f"✅ 已加入 {count} 首歌曲到隊列")
                return True
                
        except AudioSourceError as e:
            await ctx.send(f"❌ 無法處理：{e}")
            return False
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return False
        except Exception as e:
            logger.error(f"添加到隊列時發生錯誤: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
            return False

# 創建全域音樂播放器實例
music_player = MusicPlayer()