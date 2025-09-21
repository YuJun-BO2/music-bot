"""
Discord音樂機器人基本指令模組
包含ping、sync、join、leave等基本功能
"""

import asyncio
import logging

import discord
from discord.ext import commands

from config import config
from state_manager import state_manager
from music_player import music_player, VoiceManager
from audio_sources import SSHHandler, AudioSourceError

logger = logging.getLogger(__name__)

class BasicCommands(commands.Cog):
    """基本指令類"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_manager = VoiceManager()
        self.ssh_handler = SSHHandler()
    
    @commands.command()
    async def ping(self, ctx: commands.Context):
        """測試機器人延遲"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! `{latency} ms`")
    
    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """同步斜線指令（僅機器人擁有者）"""
        try:
            await self.bot.tree.sync()
            await ctx.send("✅ Slash commands 已同步")
        except Exception as e:
            await ctx.send(f"❌ 同步失敗：{e}")
    
    @commands.command()
    async def join(self, ctx: commands.Context):
        """加入用戶所在的語音頻道"""
        # 檢查用戶是否在語音頻道
        if not (ctx.author.voice and ctx.author.voice.channel):
            return await ctx.send("❌ 您需要先加入語音頻道")
        
        target_channel = ctx.author.voice.channel
        current_vc = ctx.voice_client
        
        try:
            # 如果已經在目標頻道
            if current_vc and current_vc.channel == target_channel:
                if current_vc.is_connected():
                    return await ctx.send(f"✅ 已經在 {target_channel.name} 中")
                else:
                    # 重新連接
                    await current_vc.disconnect()
                    current_vc = None
            
            # 如果在其他頻道，先斷開
            elif current_vc:
                await current_vc.disconnect()
                await asyncio.sleep(1.0)
            
            # 嘗試連接
            msg = await ctx.send(f"🔄 正在連接到 {target_channel.name}...")
            vc = await self.voice_manager.safe_connect(target_channel)
            
            # 啟動保持連接任務
            if not hasattr(vc, '_keepalive_task') or vc._keepalive_task.done():
                vc._keepalive_task = self.bot.loop.create_task(
                    self.voice_manager.keep_alive(vc, ctx.guild.id)
                )
            
            await msg.edit(content=f"✅ 成功加入 {target_channel.name}")
            
        except RuntimeError as e:
            await ctx.send(f"❌ 連接失敗: {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ 發生未預期的錯誤: {str(e)}")
            logger.error(f"加入語音頻道時發生錯誤: {e}")
    
    @commands.command()
    async def leave(self, ctx: commands.Context):
        """離開當前語音頻道"""
        if ctx.voice_client:
            # 保存狀態
            state_manager.save_state()
            
            # 停止保持連接任務
            if hasattr(ctx.voice_client, '_keepalive_task'):
                ctx.voice_client._keepalive_task.cancel()
            
            await ctx.voice_client.disconnect()
            await ctx.send("👋 已離開語音頻道")
        else:
            await ctx.send("❌ Bot 沒有在任何語音頻道")
    
    @commands.command()
    async def jable(self, ctx: commands.Context, url: str):
        """特殊處理功能（需要權限）"""
        # 檢查權限
        if not config.is_user_allowed(ctx.author.id):
            return await ctx.send("❌ 您沒有權限使用此指令")
        
        # 檢查SSH配置
        if not config.is_ssh_enabled():
            return await ctx.send("❌ SSH功能未啟用或配置不完整")
        
        await ctx.send(f"⏳ 正在處理：{url}")
        
        try:
            output, errors = await self.ssh_handler.process_jable_url(url)
            
            # 檢查是否成功
            if any("完成" in line for line in output):
                await ctx.send("✅ 已完成處理")
            else:
                # 顯示輸出或錯誤
                result_text = "\n".join(output or errors) or "(無輸出)"
                await ctx.send(
                    f"❌ 處理過程中可能遇到問題，輸出前20行：\n```{result_text[:1000]}```"
                )
                
        except AudioSourceError as e:
            await ctx.send(f"❌ 處理失敗：{e}")
        except Exception as e:
            logger.error(f"jable指令執行失敗: {e}")
            await ctx.send(f"❌ 發生未預期錯誤：{e}")
    
    @commands.command()
    async def status(self, ctx: commands.Context):
        """顯示當前播放狀態"""
        guild_id = ctx.guild.id
        status_info = state_manager.get_queue_status(guild_id)
        current = state_manager.get_current(guild_id)
        
        embed = discord.Embed(title="🎵 播放狀態", color=0x1DB954)
        
        # 當前播放
        if current.get("url"):
            embed.add_field(
                name="當前播放", 
                value=current.get("title", "Unknown"), 
                inline=False
            )
        else:
            embed.add_field(name="當前播放", value="無", inline=False)
        
        # 隊列資訊
        embed.add_field(
            name="隊列歌曲數", 
            value=status_info["queue_length"], 
            inline=True
        )
        embed.add_field(
            name="已播放數", 
            value=status_info["played_count"], 
            inline=True
        )
        embed.add_field(
            name="黑名單數", 
            value=status_info["blacklist_count"], 
            inline=True
        )
        
        # 語音狀態
        if ctx.voice_client:
            voice_status = "🔗 已連線" if ctx.voice_client.is_connected() else "❌ 未連線"
            embed.add_field(name="語音狀態", value=voice_status, inline=True)
            
            if ctx.voice_client.is_connected():
                embed.add_field(
                    name="語音頻道", 
                    value=ctx.voice_client.channel.name, 
                    inline=True
                )
        else:
            embed.add_field(name="語音狀態", value="❌ 未連線", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def voice_debug(self, ctx: commands.Context):
        """語音連接狀態除錯"""
        vc = ctx.voice_client
        
        color = 0x00FF00 if vc and vc.is_connected() else 0xFF0000
        embed = discord.Embed(title="🔊 語音連接狀態", color=color)
        
        if vc:
            # 連接狀態
            connect_status = "✅ 已連接" if vc.is_connected() else "❌ 未連接"
            embed.add_field(name="連接狀態", value=connect_status, inline=True)
            
            # 當前頻道
            channel_name = vc.channel.name if vc.channel else "無"
            embed.add_field(name="當前頻道", value=channel_name, inline=True)
            
            # 播放狀態
            if vc.is_playing():
                play_status = "🎵 播放中"
            elif vc.is_paused():
                play_status = "⏸️ 暫停"
            else:
                play_status = "⏹️ 停止"
            embed.add_field(name="播放狀態", value=play_status, inline=True)
            
            # 延遲
            if vc.is_connected():
                latency = f"{vc.latency*1000:.1f}ms"
            else:
                latency = "N/A"
            embed.add_field(name="延遲", value=latency, inline=True)
        else:
            embed.add_field(
                name="狀態", 
                value="❌ 未連接到任何語音頻道", 
                inline=False
            )
        
        # 用戶語音狀態
        if ctx.author.voice:
            embed.add_field(
                name="您的頻道", 
                value=ctx.author.voice.channel.name, 
                inline=True
            )
        else:
            embed.add_field(
                name="您的頻道", 
                value="❌ 您未在語音頻道中", 
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def debug_state(self, ctx: commands.Context):
        """顯示當前所有狀態，用於除錯"""
        guild_id = ctx.guild.id
        queue = state_manager.get_queue(guild_id)
        played = state_manager.get_played(guild_id)
        current = state_manager.get_current(guild_id)
        blacklist = state_manager.get_blacklist(guild_id)
        
        embed = discord.Embed(title="🔧 除錯狀態", color=0xFF0000)
        
        # 當前播放
        current_url = current.get('url', 'None')
        current_title = current.get('title', 'None')
        current_info = f"URL: {current_url[:50] if current_url != 'None' else 'None'}...\nTitle: {current_title}"
        embed.add_field(name="當前播放", value=current_info, inline=False)
        
        # 播放歷史
        recent_played = [url[-20:] for url in played[-3:]]
        played_info = f"總數: {len(played)}\n最後3首: {recent_played}"
        embed.add_field(name="播放歷史", value=played_info, inline=False)
        
        # 佇列狀態
        upcoming_queue = [url[-20:] for url in queue[:3]]
        queue_info = f"總數: {len(queue)}\n前3首: {upcoming_queue}"
        embed.add_field(name="佇列狀態", value=queue_info, inline=False)
        
        # 黑名單
        embed.add_field(name="黑名單數量", value=len(blacklist), inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.is_owner()
    async def save(self, ctx: commands.Context):
        """手動保存狀態（僅機器人擁有者）"""
        if state_manager.save_state():
            await ctx.send("✅ 狀態保存完成")
        else:
            await ctx.send("❌ 狀態保存失敗")
    
    @commands.command()
    @commands.is_owner()
    async def load(self, ctx: commands.Context):
        """手動載入狀態（僅機器人擁有者）"""
        if state_manager.load_state():
            await ctx.send("✅ 狀態載入完成")
        else:
            await ctx.send("❌ 狀態載入失敗")