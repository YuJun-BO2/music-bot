"""
Discord音樂機器人主程式
整合所有模組，提供乾淨的架構和入口點
"""

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

# 導入自定義模組
from config import config
from state_manager import state_manager
from music_player import music_player, VoiceManager
from basic_commands import BasicCommands
from music_commands import MusicCommands

# 設定日誌
def setup_logging():
    """設定日誌系統"""
    # 創建日誌目錄
    config.LOG_FILE.parent.mkdir(exist_ok=True)
    
    # 日誌格式
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # 文件處理器
    file_handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # 根日誌器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # 設定discord.py日誌等級
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)

class MusicBot(commands.Bot):
    """音樂機器人主類"""
    
    def __init__(self):
        # Discord Intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            description="多功能Discord音樂機器人",
            help_command=None  # 禁用預設help指令
        )
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def setup_hook(self):
        """機器人設定hook"""
        self.logger.info("正在載入指令模組...")
        
        # 載入指令模組
        await self.add_cog(BasicCommands(self))
        await self.add_cog(MusicCommands(self))
        
        self.logger.info("指令模組載入完成")
    
    async def on_ready(self):
        """機器人就緒事件"""
        self.logger.info(f"機器人已登入: {self.user} (ID: {self.user.id})")
        self.logger.info(f"已連接到 {len(self.guilds)} 個伺服器")
        
        # 載入狀態
        if state_manager.load_state():
            self.logger.info("已載入保存的狀態")
        else:
            self.logger.warning("載入狀態失敗，使用預設狀態")
        
        # 恢復播放（如果有的話）
        await self._resume_playback()
        
        # 更新機器人狀態
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{config.COMMAND_PREFIX}help | 音樂機器人"
            )
        )
    
    async def _resume_playback(self):
        """恢復播放狀態"""
        for guild in self.guilds:
            if guild.voice_client:
                await self._auto_resume_guild_playback(guild)
    
    async def _auto_resume_guild_playback(self, guild: discord.Guild):
        """自動恢復單個伺服器的播放"""
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
        
        # 等待連接穩定
        await asyncio.sleep(1.0)
        await VoiceManager.ensure_idle(vc)
        
        guild_id = guild.id
        queue = state_manager.get_queue(guild_id)
        current = state_manager.get_current(guild_id)
        
        if current.get("url") or queue:
            self.logger.info(f"伺服器 {guild.name} 檢測到未完成播放，嘗試自動恢復...")
            
            channel_id = current.get("channel_id")
            if channel_id:
                channel = self.get_channel(channel_id)
                if channel:
                    # 檢查當前播放的影片是否依然有效
                    current_url = current.get("url")
                    if current_url and current_url not in queue:
                        try:
                            from audio_sources import audio_source_manager
                            await audio_source_manager.process_url(current_url)
                            queue.insert(0, current_url)
                            self.logger.info(f"已將中斷的影片重新加入隊列：{current_url[-30:]}")
                        except Exception as e:
                            self.logger.warning(f"中斷的影片已失效，跳過恢復：{current_url[-30:]} - {e}")
                            current["url"] = current["title"] = None
                            state_manager.save_state()
                    
                    if queue:
                        # 創建臨時上下文
                        class TempContext:
                            def __init__(self, bot, channel, guild):
                                self.bot = bot
                                self.channel = channel
                                self.guild = guild
                                self.voice_client = guild.voice_client
                                self.send = channel.send
                        
                        temp_ctx = TempContext(self, channel, guild)
                        await temp_ctx.send("🔄 重啟後檢測到語音播放任務，自動恢復播放...")
                        await music_player.play_next(temp_ctx)
    
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """語音狀態更新事件"""
        if member.id != self.user.id:
            return
        
        if before.channel and not after.channel:
            self.logger.info(f"Bot 已離開語音頻道：{before.channel.name}")
            
            # 檢查是否為意外斷線
            guild = before.channel.guild
            current = state_manager.get_current(guild.id)
            queue = state_manager.get_queue(guild.id)
            
            if current.get("url") or queue:  # 有音樂在播放或排隊
                self.logger.info("檢測到意外斷線，嘗試自動重連...")
                try:
                    await asyncio.sleep(3)  # 等待3秒
                    if not guild.voice_client:  # 確認還沒重連
                        # 尋找有用戶的語音頻道
                        for channel in guild.voice_channels:
                            if len(channel.members) > 0:
                                vc = await VoiceManager.safe_connect(channel)
                                self.logger.info(f"自動重連成功：{channel.name}")
                                
                                # 啟動保持連接任務
                                if not hasattr(vc, '_keepalive_task') or vc._keepalive_task.done():
                                    vc._keepalive_task = self.loop.create_task(
                                        VoiceManager.keep_alive(vc, guild.id)
                                    )
                                break
                except Exception as e:
                    self.logger.error(f"自動重連失敗：{e}")
            
            # 保存狀態
            state_manager.save_state()
            
        elif not before.channel and after.channel:
            self.logger.info(f"Bot 已加入語音頻道：{after.channel.name}")
            await asyncio.sleep(1)
            await self._auto_resume_guild_playback(after.channel.guild)
    
    async def on_guild_join(self, guild: discord.Guild):
        """加入新伺服器事件"""
        self.logger.info(f"加入新伺服器：{guild.name} (ID: {guild.id})")
    
    async def on_guild_remove(self, guild: discord.Guild):
        """離開伺服器事件"""
        self.logger.info(f"離開伺服器：{guild.name} (ID: {guild.id})")
        # 清理該伺服器的狀態
        state_manager.cleanup_guild(guild.id)
        state_manager.save_state()
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """指令錯誤處理"""
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ 您沒有權限執行此指令")
        
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ 機器人缺少必要權限：{missing_perms}")
        
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"❌ 指令冷卻中，請等待 {error.retry_after:.1f} 秒")
        
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ 指令參數錯誤，請檢查輸入格式")
        
        else:
            self.logger.error(f"指令執行錯誤: {error}", exc_info=True)
            await ctx.send(f"❌ 指令執行時發生錯誤：{str(error)[:100]}")
    
    async def close(self):
        """機器人關閉"""
        self.logger.info("正在關閉機器人...")
        
        # 保存狀態
        if state_manager.save_state():
            self.logger.info("狀態已保存")
        else:
            self.logger.error("狀態保存失敗")
        
        # 斷開所有語音連接
        for guild in self.guilds:
            if guild.voice_client:
                await guild.voice_client.disconnect()
        
        await super().close()

def main():
    """主函數"""
    print("🎵 Discord音樂機器人 - 重構版")
    print("=" * 50)
    
    # 設定日誌
    setup_logging()
    logger = logging.getLogger("main")
    
    # 驗證配置
    if not config.validate():
        logger.error("配置驗證失敗，程式退出")
        sys.exit(1)
    
    logger.info("配置驗證通過")
    
    # 創建並運行機器人
    bot = MusicBot()
    
    try:
        # 運行機器人
        bot.run(config.DISCORD_TOKEN, log_handler=None)  # 使用我們自己的日誌處理
        
    except discord.LoginFailure:
        logger.error("登入失敗：請檢查DISCORD_TOKEN是否正確")
        sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在關閉...")
        
    except Exception as e:
        logger.error(f"程式執行時發生錯誤: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        logger.info("程式已退出")

if __name__ == "__main__":
    main()