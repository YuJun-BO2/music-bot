"""
Discord音樂機器人音樂指令模組
包含play、pause、skip、back等音樂控制功能
"""

import asyncio
import logging

import discord
from discord.ext import commands

from config import config
from state_manager import state_manager
from music_player import music_player
from audio_sources import audio_source_manager, AudioSourceError

logger = logging.getLogger(__name__)

class MusicCommands(commands.Cog):
    """音樂指令類"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.command()
    async def play(self, ctx: commands.Context, *, arg: str = None):
        """播放音樂或繼續播放"""
        # 檢查語音連接
        if ctx.voice_client is None or not ctx.voice_client.is_connected():
            return await ctx.send("❌ 請先使用 `/join` 連接語音頻道")
        
        guild_id = ctx.guild.id
        
        # 如果沒有參數，播放下一首
        if arg is None:
            return await music_player.play_next(ctx)
        
        # 如果正在播放，加入隊列
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            success = await music_player.add_to_queue(ctx, arg)
            if success:
                state_manager.save_state()
            return
        
        # 直接播放
        try:
            result = await audio_source_manager.process_url(arg)
            
            if result["type"] == "single":
                await music_player.stream_play(ctx, arg)
            elif result["type"] == "playlist":
                # 播放列表處理
                urls = result["urls"]
                if urls:
                    # 第一首直接播放，其餘加入隊列
                    first_url = urls[0]
                    remaining_urls = urls[1:]
                    
                    # 將剩餘歌曲加入隊列
                    queue = state_manager.get_queue(guild_id)
                    for url in remaining_urls:
                        try:
                            state_manager.add_to_queue(guild_id, url)
                        except ValueError:
                            break  # 隊列已滿
                    
                    await ctx.send(f"📝 {result['title']}")
                    await music_player.stream_play(ctx, first_url)
                else:
                    await ctx.send("❌ 播放列表為空")
            
        except AudioSourceError as e:
            await ctx.send(f"❌ 播放失敗：{e}")
        except Exception as e:
            logger.error(f"播放指令執行失敗: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
    
    @commands.command()
    async def pause(self, ctx: commands.Context):
        """暫停播放"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ 已暫停")
        else:
            await ctx.send("❌ 沒有任何音樂正在播放")
    
    @commands.command()
    async def resume(self, ctx: commands.Context):
        """恢復播放"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 已恢復播放")
        else:
            await ctx.send("❌ 沒有任何暫停中的音樂")
    
    @commands.command()
    async def skip(self, ctx: commands.Context):
        """跳過當前歌曲"""
        vc = ctx.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await ctx.send("❌ 沒有任何音樂正在播放")
        
        # 清除back狀態，允許正常續播
        current = state_manager.get_current(ctx.guild.id)
        current["from_back"] = False
        state_manager.save_state()
        
        vc.pause()
        await asyncio.sleep(1.0)
        vc.stop()
        await ctx.send("⏭️ 已跳過")
    
    @commands.command()
    async def back(self, ctx: commands.Context):
        """返回上一首歌"""
        guild_id = ctx.guild.id
        queue = state_manager.get_queue(guild_id)
        played = state_manager.get_played(guild_id)
        current = state_manager.get_current(guild_id)
        back_history = state_manager.get_back_history(guild_id)
        
        logger.info("執行/back指令")
        
        # 獲取當前播放的歌
        current_url = current.get("url")
        
        if current_url:
            if not back_history or back_history[-1] != current_url:
                back_history.append(current_url)
        
        # 檢查歷史
        if len(back_history) < 2:
            if played:
                for song in played[-5:]:
                    if song not in back_history:
                        back_history.insert(-1 if back_history else 0, song)
        
        if len(back_history) < 2:
            return await ctx.send("❌ 沒有足夠的歷史記錄")
        
        # 強制停止當前播放
        if ctx.voice_client:
            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                ctx.voice_client.stop()
                await asyncio.sleep(2.0)
        
        # 保存原始佇列
        original_queue = queue.copy()
        
        # 取得目標歌曲
        back_history.pop()  # 移除當前歌
        prev_url = back_history[-1]  # 上一首
        
        logger.info(f"目標歌曲: {prev_url[-20:]}")
        
        # 重建續播佇列
        try:
            if prev_url in played:
                prev_index = played.index(prev_url)
                
                # 從目標歌曲之後的歌曲作為續播佇列
                if current_url and current_url in played:
                    current_index = played.index(current_url)
                    continuation = played[prev_index + 1:current_index + 1]
                else:
                    continuation = played[prev_index + 1:prev_index + 4]
                
                # 重建完整佇列
                queue.clear()
                queue.extend(continuation)
                queue.extend(original_queue)
                
                logger.info(f"重建佇列: {len(continuation)} 首續播 + {len(original_queue)} 首原始")
            else:
                queue.clear()
                queue.extend(original_queue)
                logger.info("找不到目標歌曲，恢復原始佇列")
                
        except Exception as e:
            logger.error(f"重建佇列失敗: {e}")
            queue.clear()
            queue.extend(original_queue)
        
        # 設定正確狀態
        current.clear()
        current.update({
            "url": None,
            "title": None,
            "channel_id": ctx.channel.id,
            "position": 0,
            "from_back": True,
            "processing_back": True
        })
        
        state_manager.save_state()
        
        # 延遲後播放
        await asyncio.sleep(1.0)
        await music_player.stream_play(ctx, prev_url)
        
        current["processing_back"] = False
        state_manager.save_state()
        
        await ctx.send(f"⏮️ 返回：{prev_url[-30:]}，續播佇列：{len(queue)} 首")
    
    @commands.command()
    async def interlude(self, ctx: commands.Context, *, url: str):
        """插播歌曲/播放列表，插入到佇列最前面並立即播放"""
        guild_id = ctx.guild.id
        queue = state_manager.get_queue(guild_id)
        
        try:
            result = await audio_source_manager.process_url(url)
            
            if result["type"] == "single":
                links = [url]
            elif result["type"] == "playlist":
                links = result["urls"]
            else:
                return await ctx.send("❌ 無法處理此類型的內容")
            
            if not links:
                return await ctx.send("❌ 無法取得插播內容")
            
            # 倒序插入佇列開頭保持原順序
            for link in reversed(links):
                queue.insert(0, link)
            
            state_manager.save_state()
            
            # 如果正在播放，停止當前播放
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.pause()
                await asyncio.sleep(0.5)
                ctx.voice_client.stop()
            else:
                # 如果沒有播放，直接播放下一首
                await music_player.play_next(ctx)
            
            await ctx.send(f"▶️ 插播內容已加入，共 {len(links)} 首歌曲將優先播放")
            
        except AudioSourceError as e:
            await ctx.send(f"❌ 插播失敗：{e}")
        except Exception as e:
            logger.error(f"插播指令執行失敗: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
    
    @commands.command(name="list")
    async def queue_list(self, ctx: commands.Context):
        """顯示當前播放隊列"""
        queue = state_manager.get_queue(ctx.guild.id)
        
        if not queue:
            return await ctx.send("📝 隊列是空的")
        
        # 顯示前10首歌
        queue_text = "\n".join(f"{i+1}. {q[-50:]}" for i, q in enumerate(queue[:10]))
        
        if len(queue) > 10:
            queue_text += f"\n... 還有 {len(queue)-10} 首"
        
        embed = discord.Embed(title="📝 當前隊列", description=queue_text, color=0x1DB954)
        embed.set_footer(text=f"總計 {len(queue)} 首歌曲")
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def search(self, ctx: commands.Context, *, query: str):
        """搜尋YouTube影片"""
        try:
            result = await audio_source_manager.process_url(query)
            
            if result["type"] == "single":
                embed = discord.Embed(title="🔍 搜尋結果", color=0xFF0000)
                embed.add_field(name="標題", value=result["title"], inline=False)
                embed.add_field(name="連結", value=result["urls"][0], inline=False)
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ 搜尋結果格式不正確")
                
        except AudioSourceError as e:
            await ctx.send(f"❌ 搜尋失敗：{e}")
        except Exception as e:
            logger.error(f"搜尋指令執行失敗: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
    
    @commands.command()
    async def playlist(self, ctx: commands.Context, *, url: str):
        """處理播放列表（Spotify/YouTube/YT Music）"""
        try:
            result = await audio_source_manager.process_url(url)
            
            if result["type"] != "playlist":
                return await ctx.send("❌ 請提供有效的播放列表連結")
            
            urls = result["urls"]
            if not urls:
                return await ctx.send("❌ 播放列表為空")
            
            # 檢查是否正在播放
            is_idle = not (ctx.voice_client and 
                          (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()))
            
            # 加入隊列
            queue = state_manager.get_queue(ctx.guild.id)
            added_count = 0
            
            for url in urls:
                try:
                    state_manager.add_to_queue(ctx.guild.id, url)
                    added_count += 1
                except ValueError:
                    break  # 隊列已滿
            
            state_manager.save_state()
            
            await ctx.send(f"✅ {result['title']} - 已加入 {added_count} 首歌曲")
            
            # 如果沒有播放，開始播放
            if is_idle:
                await music_player.play_next(ctx)
                
        except AudioSourceError as e:
            await ctx.send(f"❌ 播放列表處理失敗：{e}")
        except Exception as e:
            logger.error(f"播放列表指令執行失敗: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
    
    @commands.command()
    async def clean_list(self, ctx: commands.Context, count: int):
        """清空隊列前面指定數量的歌曲"""
        if count <= 0:
            return await ctx.send("❌ 請輸入大於0的數字")
        
        removed = state_manager.remove_from_queue(ctx.guild.id, count)
        remaining = len(state_manager.get_queue(ctx.guild.id))
        
        state_manager.save_state()
        await ctx.send(f"🗑️ 已清除前 {removed} 首歌，剩餘 {remaining} 首")
    
    @commands.command()
    async def clean_all(self, ctx: commands.Context):
        """清空所有播放隊列"""
        removed = state_manager.clear_queue(ctx.guild.id)
        state_manager.save_state()
        await ctx.send(f"🗑️ 已清空所有隊列，共移除 {removed} 首歌")
    
    @commands.command()
    async def now_playing(self, ctx: commands.Context):
        """顯示當前播放的歌曲詳細資訊"""
        current = state_manager.get_current(ctx.guild.id)
        
        if not current.get("url"):
            return await ctx.send("❌ 目前沒有播放任何音樂")
        
        embed = discord.Embed(title="🎵 正在播放", color=0x1DB954)
        embed.add_field(name="標題", value=current.get("title", "Unknown"), inline=False)
        embed.add_field(name="來源", value=current.get("url", "Unknown")[-50:], inline=False)
        
        # 播放狀態
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                status = "▶️ 播放中"
            elif ctx.voice_client.is_paused():
                status = "⏸️ 暫停"
            else:
                status = "⏹️ 停止"
            embed.add_field(name="狀態", value=status, inline=True)
        
        # 隊列資訊
        queue_length = len(state_manager.get_queue(ctx.guild.id))
        embed.add_field(name="隊列中", value=f"{queue_length} 首歌", inline=True)
        
        await ctx.send(embed=embed)