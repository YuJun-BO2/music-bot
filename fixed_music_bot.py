# NEW_music_bot.py - 2025-09-14 Enhanced (Multi-Guild Fixed)
# 支援多伺服器、Python 3.10+、discord.py 2.4+
# 功能：多伺服器音樂播放、狀態保存、隊列管理

import os
import json
import shlex
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
import yt_dlp
from youtubesearchpython import VideosSearch
import spotipy
from spotipy_anon import SpotifyAnon
import paramiko
# imports 需要包含 asyncio/logging 等，
from collections import defaultdict  # NEW

# 為每個 guild 建立獨立的播放鎖，避免併發播放問題，
play_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)  # NEW

async def ensure_idle(vc: discord.VoiceClient, timeout: float = 3.0):  # NEW
    # 確保語音客戶端處於空閒狀態，避免 Already playing 錯誤
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    start = asyncio.get_event_loop().time()
    while vc and (vc.is_playing() or vc.is_paused()) and \
          (asyncio.get_event_loop().time() - start) < timeout:
        await asyncio.sleep(0.05)


async def get_safe_vc(ctx: commands.Context) -> discord.VoiceClient | None:
    """
    回傳一個『已連線且可用』的 VoiceClient。
    若尚未連線，提示使用者並回 None。
    """
    vc = ctx.voice_client
    if vc is None or not vc.is_connected():        # 只看 is_connected()
        await ctx.send("❌ Bot 尚未連線語音頻道，請先 `/join`")
        return None

    await ensure_idle(vc)                          # 確定 idle
    return vc



##############################################################################
# 配置設定
##############################################################################

DISCORD_TOKEN = ""
SSH_HOST = ""
SSH_PORT = ""
SSH_USER = ""
SSH_PASS = "r"
ALLOWED_IDS = {}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
spotify = spotipy.Spotify(auth_manager=SpotifyAnon())
logger = logging.getLogger("music-bot")

##############################################################################
# 功能：全域狀態持久化保存
##############################################################################

STATE_FILE = Path("bot_state.json")

# 全域狀態，按 guild_id 分組保存
guild_queues: dict[int, list[str]] = {}       # {guild_id: [songs]}
guild_played: dict[int, list[str]] = {}       # {guild_id: [played_songs]}
guild_current: dict[int, dict] = {}           # {guild_id: current_playing_info}
guild_back_history: dict[int, list[str]] = {}  # {guild_id: [back_stack]}



YTDL_OPTS = {"format": "bestaudio/best", "quiet": True}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -b:a 128k -threads 2",
}

##############################################################################
# 功能：Guild 狀態管理輔助函數
##############################################################################
def get_guild_back_history(guild_id: int) -> list[str]:
    """取得指定伺服器的 back 歷史堆疊"""
    if guild_id not in guild_back_history:
        guild_back_history[guild_id] = []
    return guild_back_history[guild_id]

def get_guild_queue(guild_id: int) -> list[str]:
    """取得指定伺服器的音樂隊列"""
    if guild_id not in guild_queues:
        guild_queues[guild_id] = []
    return guild_queues[guild_id]

def get_guild_played(guild_id: int) -> list[str]:
    """取得指定伺服器的已播放歷史"""
    if guild_id not in guild_played:
        guild_played[guild_id] = []
    return guild_played[guild_id]

def get_guild_current(guild_id: int) -> dict:
    """取得指定伺服器的當前播放資訊"""
    if guild_id not in guild_current:
        guild_current[guild_id] = {
            "url": None,
            "title": None,
            "channel_id": None,
            "position": 0,
        }
    return guild_current[guild_id]

# 在 guild_current 定義附近加入

# 在 guild_current 定義附近加入
guild_blacklist: dict[int, set[str]] = {}  # {guild_id: {failed_urls}}
guild_back_count: dict[int, int] = {}       # ★ 新增：{guild_id: back_steps}

def get_guild_blacklist(guild_id: int) -> set[str]:
    """取得指定伺服器的失效影片黑名單"""
    if guild_id not in guild_blacklist:
        guild_blacklist[guild_id] = set()
    return guild_blacklist[guild_id]

def get_guild_back_count(guild_id: int) -> int:  # ★ 新增
    """取得指定伺服器的回退步數計數"""
    if guild_id not in guild_back_count:
        guild_back_count[guild_id] = 0
    return guild_back_count[guild_id]


def save_state():
    """保存所有伺服器的播放狀態"""
    try:
        state = {
            "guild_queues": {str(k): v for k, v in guild_queues.items()},
            "guild_played": {str(k): v[-50:] for k, v in guild_played.items()},
            "guild_current": {str(k): v for k, v in guild_current.items()},
            "guild_blacklist": {str(k): list(v) for k, v in guild_blacklist.items()},
            "guild_back_count": {str(k): v for k, v in guild_back_count.items()},
            "guild_back_history": {str(k): v[-20:] for k, v in guild_back_history.items()},
        }
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("狀態保存完成")
    except Exception as e:
        logger.error(f"保存狀態失敗：{e}")


def load_state():
    """載入所有伺服器的播放狀態"""
    global guild_queues, guild_played, guild_current, guild_blacklist, guild_back_count, guild_back_history
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            
            guild_queues = {int(k): v for k, v in state.get("guild_queues", {}).items()}
            guild_played = {int(k): v for k, v in state.get("guild_played", {}).items()}
            guild_current = {int(k): v for k, v in state.get("guild_current", {}).items()}
            guild_blacklist = {int(k): set(v) for k, v in state.get("guild_blacklist", {}).items()}
            guild_back_count = {int(k): v for k, v in state.get("guild_back_count", {}).items()}
            guild_back_history = {int(k): v for k, v in state.get("guild_back_history", {}).items()}
     
            logger.info("成功載入已保存的播放狀態")
        except Exception as e:
            logger.warning(f"載入狀態失敗：{e}")



##############################################################################
# 輔助工具：非同步執行器
##############################################################################

async def run_in_thread(func, *args):
    return await asyncio.to_thread(func, *args)

async def ytdlp_extract(url: str):
    def _work():
        with yt_dlp.YoutubeDL(YTDL_OPTS) as ydl:
            return ydl.extract_info(url, download=False)
    
    try:
        # ★ 加入 30 秒超時
        return await asyncio.wait_for(run_in_thread(_work), timeout=30.0)
    except asyncio.TimeoutError:
        raise yt_dlp.utils.DownloadError(f"Extract timeout after 30s for {url}")


async def yt_flat_playlist(url: str, music=False) -> list[str]:
    opts = {**YTDL_OPTS, "extract_flat": "in_playlist"}
    def _work():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    data = await run_in_thread(_work)
    links = []
    for e in data.get("entries", []):
        vid = e.get("id")
        if vid:
            prefix = "https://music.youtube.com/watch?v=" if music else "https://www.youtube.com/watch?v="
            links.append(f"{prefix}{vid}")
    return links

async def yt_search_first(query: str) -> str | None:
    def _work():
        res = VideosSearch(query, limit=1).result()
        return res["result"][0]["link"] if res.get("result") else None
    return await run_in_thread(_work)

async def sp_track(url: str):
    return await run_in_thread(spotify.track, url)

async def sp_playlist(url: str):
    return await run_in_thread(spotify.playlist, url)

async def ssh_jable(url: str):
    def _work():
        cli = paramiko.SSHClient()
        cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cli.connect(SSH_HOST, port=SSH_PORT, username=SSH_USER, password=SSH_PASS)
        safe = shlex.quote(url)
        cmd = (
            "cd /app && source venv/bin/activate && "
            f"python main.py --url {safe} --encode 2 --output /downloads --no-prompt"
        )
        stdin, stdout, stderr = cli.exec_command(cmd)
        out = stdout.read().decode().splitlines()[:20]
        err = stderr.read().decode().splitlines()[:20]
        cli.close()
        return out, err
    return await run_in_thread(_work)

##############################################################################
# 新增：安全連線管理 + 防斷線 keep-alive
##############################################################################

async def safe_connect(channel, retry=5):
    """強化版語音連接，支援更多重試和錯誤處理"""
    for i in range(retry):
        try:
            print(f"DEBUG: 嘗試連接語音頻道 ({i+1}/{retry}): {channel.name}")
            
            # ★ 增加連接超時設定
            vc = await asyncio.wait_for(channel.connect(), timeout=15.0)
            
            # ★ 連接後等待穩定
            await asyncio.sleep(2.0)
            
            # ★ 檢查連接狀態
            if vc.is_connected():
                print(f"DEBUG: 語音連接成功: {channel.name}")
                return vc
            else:
                print(f"DEBUG: 連接狀態檢查失敗，重試...")
                if vc:
                    try:
                        await vc.disconnect()
                    except:
                        pass
                        
        except asyncio.TimeoutError:
            print(f"DEBUG: 語音連接超時 ({i+1}/{retry})")
        except Exception as e:
            print(f"DEBUG: 語音連接失敗 ({i+1}/{retry}): {e}")
            
        if i < retry - 1:  # 最後一次不需要等待
            wait_time = min(5, 2 * (i + 1))  # 漸進式等待時間
            print(f"DEBUG: 等待 {wait_time} 秒後重試...")
            await asyncio.sleep(wait_time)
    
    raise RuntimeError(f"多次嘗試後仍無法連接到語音頻道: {channel.name}")



# 防斷線 keep_alive 機制

async def keep_alive(vc: discord.VoiceClient, guild_id: int):
    """
    每 4 分鐘播 1 s 靜音，防 Discord 自動斷線。
    若正在重連或正被鎖定，直接跳過。
    """
    SILENT = discord.FFmpegPCMAudio(
        "anullsrc=r=48000:cl=stereo",
        before_options="-f lavfi -t 1",
        options="-loglevel quiet"
    )

    while not vc.is_closed():
        await asyncio.sleep(240)

        # 尚未完成連線 → 跳過
        if not vc.is_connected():
            continue
        # 正在播放或暫停 → 跳過
        if vc.is_playing() or vc.is_paused():
            continue

        lock = play_locks[guild_id]
        if lock.locked():                           # 播放流程持有鎖
            continue

        async with lock:
            if not vc.is_playing() and not vc.is_paused():
                vc.play(SILENT, after=lambda *_: None)



##############################################################################
# 功能：機器人重啟後自動恢復播放，適用於多伺服器，
##############################################################################

class TempContext:
    def __init__(self, bot, channel, guild):
        self.bot = bot
        self.channel = channel
        self.guild = guild
        self.voice_client = guild.voice_client
        self.send = channel.send

async def auto_resume_playback(guild: discord.Guild):
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    await asyncio.sleep(1.0)
    await ensure_idle(vc)
    
    guild_id = guild.id
    queue = get_guild_queue(guild_id)
    current = get_guild_current(guild_id)
    
    if current["url"] and (queue or current["url"]):
        logger.info(f"伺服器 {guild.name} 重啟後發現未完成播放，嘗試自動恢復...")
        
        channel_id = current.get("channel_id")
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                if current["url"] and current["url"] not in queue:
                    # 檢查影片是否依然有效
                    try:
                        await ytdlp_extract(current["url"])
                        queue.insert(0, current["url"])
                        logger.info(f"已將中斷的影片重新加入佇列：{current['url']}")
                    except yt_dlp.utils.DownloadError as e:
                        logger.warning(f"中斷的影片已失效，跳過恢復：{current['url']} - {e}")
                        current["url"] = current["title"] = None
                        save_state()
                
                if queue:
                    temp_ctx = TempContext(bot, channel, guild)
                    await temp_ctx.send("🔄 重啟後檢測到語音播放任務，自動恢復播放...")
                    await play_next(temp_ctx)


##############################################################################
# 事件處理器
##############################################################################

@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    load_state()
    
    for guild in bot.guilds:
        if guild.voice_client:
            await auto_resume_playback(guild)

@bot.event
async def on_voice_state_update(member, before, after):
    """處理語音狀態變更，包含自動重連和狀態恢復"""
    if member.id != bot.user.id:
        return
    
    if before.channel and not after.channel:
        logger.info(f"Bot 已離開語音頻道：{before.channel.name}")
        
        # ★ 如果是意外斷線，嘗試自動重連
        guild = before.channel.guild
        current = get_guild_current(guild.id)
        queue = get_guild_queue(guild.id)
        
        if current["url"] or queue:  # 有音樂在播放或排隊
            logger.info("檢測到意外斷線，嘗試自動重連...")
            try:
                await asyncio.sleep(3)  # 等待3秒
                if not guild.voice_client:  # 確認還沒重連
                    # 尋找有用戶的語音頻道
                    for channel in guild.voice_channels:
                        if len(channel.members) > 0:
                            vc = await safe_connect(channel)
                            logger.info(f"自動重連成功：{channel.name}")
                            break
            except Exception as e:
                logger.error(f"自動重連失敗：{e}")
        
        save_state()
        
    elif not before.channel and after.channel:
        logger.info(f"Bot 已加入語音頻道：{after.channel.name}")
        await asyncio.sleep(1)
        await auto_resume_playback(after.channel.guild)


##############################################################################
# 功能：播放下一首歌，支援多伺服器狀態管理
##############################################################################

# ────────── play_next ──────────
async def play_next(ctx: commands.Context):
    guild_id = ctx.guild.id
    queue    = get_guild_queue(guild_id)
    current  = get_guild_current(guild_id)

    if not queue:
        current["url"] = current["title"] = None
        save_state()
        await ctx.send("Queue is empty.")
        return

    item = queue.pop(0)          # 先取出隊首
    save_state()

    try:
        if "spotify.com" in item:
            await play_spotify_track(ctx, item)
        elif "youtube.com" in item and "playlist" in item:
            await play_youtube_playlist(ctx, item)
        elif "music.youtube.com" in item and "playlist" in item:
            await play_ytmusic_playlist(ctx, item)
        else:
            if not item.startswith("http"):
                link = await yt_search_first(item)
                if not link:
                    return await ctx.send(f"找不到：{item}")
                await stream_play(ctx, link)
            else:
                await stream_play(ctx, item)
    except Exception as e:
        await ctx.send(f"播放時發生錯誤：{e}")

    # ─ 可選緩衝，如需保留 0.5 s 延遲請取消下一行註解 ─
    # await asyncio.sleep(0.5)
# ─────────────────────────────


##############################################################################
# 指令：基本和支援多伺服器狀態管理的指令
##############################################################################

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! `{round(bot.latency*1000)} ms`")

@bot.command()
@commands.is_owner()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("✅ Slash commands 已同步")

@bot.command()
async def jable(ctx, url: str):
    if ALLOWED_IDS and ctx.author.id not in ALLOWED_IDS:
        return await ctx.send("❌ 您沒有權限使用此指令")
    if not (SSH_HOST and SSH_USER and SSH_PASS):
        return await ctx.send("❌ 配置 SSH 參數不完整")
    await ctx.send(f"⏳ 正在處理：{url}")
    out, err = await ssh_jable(url)
    if any("完成" in line for line in out):
        await ctx.send("✅ 已完成處理")
    else:
        txt = "\n".join(out or err) or "(無輸出)"
        await ctx.send(f"❌ 處理 過程中可能遇到問題，輸出前 20 行：\n```{txt[:1000]}```")


@bot.command()
async def join(ctx):
    if not (ctx.author.voice and ctx.author.voice.channel):
        return await ctx.send("您需要先加入語音頻道")
    
    ch = ctx.author.voice.channel
    vc = ctx.voice_client
    
    try:
        if vc and vc.channel == ch:
            if vc.is_connected():
                await ctx.send(f"已經在 {ch.name} 中")
                return
            else:
                # 重新連接
                await vc.disconnect()
                vc = None
        elif vc:
            await vc.disconnect()
            await asyncio.sleep(1.0)  # 等待斷開
        
        # 嘗試連接
        msg = await ctx.send(f"🔄 正在連接到 {ch.name}...")
        vc = await safe_connect(ch)
        
        # 啟動 keep-alive
        if not hasattr(vc, '_ka_task') or vc._ka_task.done():
            vc._ka_task = bot.loop.create_task(keep_alive(vc, ctx.guild.id))
        
        await msg.edit(content=f"✅ 成功加入 {ch.name}")
        
    except RuntimeError as e:
        await ctx.send(f"❌ 連接失敗: {str(e)}")
    except Exception as e:
        await ctx.send(f"❌ 發生未預期的錯誤: {str(e)}")



@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        save_state()
        await ctx.voice_client.disconnect()
        await ctx.send("已離開語音頻道")
    else:
        await ctx.send("Bot 沒有在任何語音頻道")

@bot.command()
async def play(ctx, *, arg: str | None = None):
    if ctx.voice_client is None or not ctx.voice_client.is_connected():
        return await ctx.send("請先 `/join`")
    
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    
    if arg is None:
        return await play_next(ctx)
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        queue.append(arg)
        save_state()
        await ctx.send(f"已加入佇列第{len(queue)}位")
        return
    await _direct_play(ctx, arg)

async def _direct_play(ctx, arg: str):
    try:
        if "spotify.com" in arg:
            await play_spotify_track(ctx, arg)
        elif "youtube.com" in arg and "playlist" in arg:
            await play_youtube_playlist(ctx, arg)
        elif "music.youtube.com" in arg and "playlist" in arg:
            await play_ytmusic_playlist(ctx, arg)
        else:
            if not arg.startswith("http"):
                link = await yt_search_first(arg)
                if not link:
                    return await ctx.send("找不到搜尋結果")
                await stream_play(ctx, link)
            else:
                await stream_play(ctx, arg)
    except Exception as e:
        await ctx.send(f"播放發生問題：{e}")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("沒有任何音樂正在播放")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("沒有任何暫停中的音樂")

##############################################################################
# 新增： skip / back / interlude

@bot.command()
async def skip(ctx):
    """跳過當前歌曲，支援續播功能"""
    vc = ctx.voice_client
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await ctx.send("❌ 沒有任何音樂正在播放")
    
    # ★ 不管是否來自 back，都允許 skip 到佇列下一首
    current = get_guild_current(ctx.guild.id)
    current["from_back"] = False  # 清除 back 狀態，允許正常續播
    save_state()
    
    vc.pause()
    await asyncio.sleep(1.0)
    vc.stop()
    await ctx.send("⏭️ 已跳過")



@bot.command()
async def debug_state(ctx):
    """顯示當前所有狀態，用於除錯"""
    gid = ctx.guild.id
    q = get_guild_queue(gid)
    hist = get_guild_played(gid)
    cur = get_guild_current(gid)
    
    embed = discord.Embed(title="🔧 除錯狀態", color=0xFF0000)
    embed.add_field(name="當前播放", value=f"URL: {cur.get('url', 'None')[:50]}...\nTitle: {cur.get('title', 'None')}", inline=False)
    embed.add_field(name="播放歷史", value=f"總數: {len(hist)}\n最後3首: {[url[-20:] for url in hist[-3:]]}", inline=False)
    embed.add_field(name="佇列狀態", value=f"總數: {len(q)}\n前3首: {[url[-20:] for url in q[:3]]}", inline=False)
    
    await ctx.send(embed=embed)


# 加入一個新的全域變數來追蹤 back 歷史
guild_back_history: dict[int, list[str]] = {}  # {guild_id: [back_stack]}

def get_guild_back_history(guild_id: int) -> list[str]:
    """取得指定伺服器的 back 歷史堆疊"""
    if guild_id not in guild_back_history:
        guild_back_history[guild_id] = []
    return guild_back_history[guild_id]


@bot.command()
async def back(ctx):
    """返回上一首歌，正確的續播版本"""
    gid = ctx.guild.id
    q = get_guild_queue(gid)
    hist = get_guild_played(gid)
    cur = get_guild_current(gid)
    back_stack = get_guild_back_history(gid)

    print(f"DEBUG /back: 開始執行")
    print(f"DEBUG /back: played={[url[-20:] for url in hist[-5:]]}")
    print(f"DEBUG /back: queue={len(q)} 首歌")

    # ★ 獲取當前播放的歌
    current_url = cur.get("url")
    
    if current_url:
        if not back_stack or back_stack[-1] != current_url:
            back_stack.append(current_url)

    # ★ 檢查歷史
    if len(back_stack) < 2:
        if hist:
            for song in hist[-5:]:
                if song not in back_stack:
                    back_stack.insert(-1 if back_stack else 0, song)

    if len(back_stack) < 2:
        return await ctx.send("❌ 沒有足夠的歷史記錄")

    # ★ 重要：強制停止所有播放
    if ctx.voice_client:
        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            ctx.voice_client.stop()
            await asyncio.sleep(2.0)

    # ★ 保存原始佇列用於重建
    original_queue = q.copy()  # 在清空前先複製
    
    # ★ 取得目標歌曲
    back_stack.pop()  # 移除當前歌
    prev_url = back_stack[-1]  # 上一首

    print(f"DEBUG /back: 目標歌曲: {prev_url[-20:]}")
    print(f"DEBUG /back: 原始佇列: {len(original_queue)} 首")

    # ★ 重建續播佇列：找到目標歌曲在歷史中的位置
    try:
        if prev_url in hist:
            prev_index = hist.index(prev_url)
            
            # 從目標歌曲之後的歌曲作為續播佇列
            if current_url and current_url in hist:
                current_index = hist.index(current_url)
                # 取從目標歌曲到當前歌曲之間的所有歌曲
                continuation = hist[prev_index + 1:current_index + 1]
            else:
                # 如果找不到當前歌曲，取目標歌曲後面的幾首
                continuation = hist[prev_index + 1:prev_index + 4]  # 取後面3首
            
            print(f"DEBUG /back: 續播歌曲: {[url[-20:] for url in continuation]}")
            
            # 重建完整佇列：續播歌曲 + 原始佇列
            q.clear()
            q.extend(continuation)  # 先加入續播歌曲
            q.extend(original_queue)  # 再加入原始佇列
            
            print(f"DEBUG /back: 重建佇列 {len(continuation)} 首續播 + {len(original_queue)} 首原始")
        else:
            # 找不到目標歌曲，只恢復原始佇列
            q.clear()
            q.extend(original_queue)
            print(f"DEBUG /back: 找不到目標歌曲，恢復原始佇列 {len(original_queue)} 首")
            
    except Exception as e:
        print(f"DEBUG /back: 重建佇列失敗: {e}")
        # 失敗時恢復原始佇列
        q.clear()
        q.extend(original_queue)

    # ★ 設定正確狀態
    cur.clear()
    cur.update({
        "url": None,
        "title": None,
        "channel_id": ctx.channel.id,
        "position": 0,
        "from_back": True,
        "processing_back": True
    })
    
    save_state()
    
    # ★ 延遲後播放
    await asyncio.sleep(1.0)
    await stream_play(ctx, prev_url)
    
    cur["processing_back"] = False
    save_state()
    
    await ctx.send(f"⏮️ 返回：{prev_url[-30:]}，續播佇列：{len(q)} 首")



@bot.command()
async def interlude(ctx, *, url: str):
    """插播歌曲/播放列表，插入到佇列最前面並立即播放，"""
    gid   = ctx.guild.id
    queue = get_guild_queue(gid)

    # 處理播放列表：如果是播放列表或含有播放列表ID
    if "playlist" in url or "list=" in url:
        if "music.youtube.com" in url:
            links = await yt_flat_playlist(url, music=True)
        else:
            links = await yt_flat_playlist(url, music=False)
    else:
        links = [url]

    if not links:
        return await ctx.send("❌ 無法取得插播內容")

    for link in reversed(links):   # 倒序插入佇列開頭保持原順序
        queue.insert(0, link)
    save_state()

    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await asyncio.sleep(0.5)
        ctx.voice_client.stop()
    else:
        await play_next(ctx)

    await ctx.send(f"▶️ 插播內容已加入，共 {len(links)} 首歌曲將優先播放")


@bot.command(name="list")
async def _list(ctx):
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    
    if not queue:
        await ctx.send("隊列是空的")
    else:
        queue_text = "\n".join(f"{i+1}. {q}" for i, q in enumerate(queue[:10]))
        if len(queue) > 10:
            queue_text += f"\n... 還有 {len(queue)-10} 首"
        await ctx.send(f"**隊列:**\n{queue_text}")

@bot.command()
async def search(ctx, *, query: str):
    try:
        def _work():
            vs = VideosSearch(query, limit=5).result()
            return [(v["title"], v["link"]) for v in vs.get("result", [])]
        items = await run_in_thread(_work)
        if not items:
            return await ctx.send("No result.")
        for title, link in items:
            await ctx.send(f"{title}\n{link}")
    except Exception as e:
        await ctx.send(f"搜尋發生問題：{e}")

@bot.command()
async def playlist(ctx, *, url: str):
    try:
        if "spotify.com" in url:
            await play_spotify_playlist(ctx, url)
        elif "youtube.com" in url and "playlist" in url:
            await play_youtube_playlist(ctx, url)
        elif "music.youtube.com" in url and "playlist" in url:
            await play_ytmusic_playlist(ctx, url)
        else:
            await ctx.send("請提供 Spotify / YouTube / YT Music 播放列表連結")
    except Exception as e:
        await ctx.send(f"處理播放列表發生問題：{e}")

@bot.command()
async def status(ctx):
    """顯示當前播放狀態"""
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    played = get_guild_played(guild_id)
    current = get_guild_current(guild_id)
    
    embed = discord.Embed(title="🎵 播放狀態", color=0x1DB954)
    
    if current["url"]:
        embed.add_field(name="當前播放", value=current["title"] or "Unknown", inline=False)
    else:
        embed.add_field(name="當前播放", value="無", inline=False)
    
    embed.add_field(name="隊列歌曲數", value=len(queue), inline=True)
    embed.add_field(name="已播放數", value=len(played), inline=True)
    
    if ctx.voice_client:
        status = "🔗 已連線" if ctx.voice_client.is_connected() else "❌ 未連線"
        embed.add_field(name="語音狀態", value=status, inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def save(ctx):
    save_state()
    await ctx.send("✅ 狀態保存完成")

@bot.command()
@commands.is_owner()
async def load(ctx):
    load_state()
    await ctx.send("✅ 狀態載入完成")
##############################################################################
# 新增：更多隊列管理指令
##############################################################################

@bot.command()
async def clean_list(ctx, count: int):
    """清空隊列前面指定歌曲數量，移除最前面歌曲"""
    if count <= 0:
        return await ctx.send("請輸入大於0的歌曲數")

    queue = get_guild_queue(ctx.guild.id)
    removed = min(count, len(queue))
    for _ in range(removed):
        queue.pop(0)
    save_state()

    await ctx.send(f"🗑️ 已清空前 {removed} 首歌，剩餘 {len(queue)} 首")

@bot.command()
async def clean_all(ctx):
    """清空所有播放隊列"""
    queue = get_guild_queue(ctx.guild.id)
    removed = len(queue)
    queue.clear()
    save_state()

    await ctx.send(f"🗑️ 已清空所有隊列 {removed} 首歌")


@bot.command()
async def voice_debug(ctx):
    """語音連接狀態除錯"""
    vc = ctx.voice_client
    
    embed = discord.Embed(title="🔊 語音連接狀態", color=0x00FF00 if vc and vc.is_connected() else 0xFF0000)
    
    if vc:
        embed.add_field(name="連接狀態", value="✅ 已連接" if vc.is_connected() else "❌ 未連接", inline=True)
        embed.add_field(name="當前頻道", value=vc.channel.name if vc.channel else "無", inline=True)
        embed.add_field(name="播放狀態", value="🎵 播放中" if vc.is_playing() else "⏸️ 暫停" if vc.is_paused() else "⏹️ 停止", inline=True)
        embed.add_field(name="延遲", value=f"{vc.latency*1000:.1f}ms" if vc.is_connected() else "N/A", inline=True)
    else:
        embed.add_field(name="狀態", value="❌ 未連接到任何語音頻道", inline=False)
    
    # 用戶語音狀態
    if ctx.author.voice:
        embed.add_field(name="您的頻道", value=ctx.author.voice.channel.name, inline=True)
    else:
        embed.add_field(name="您的頻道", value="❌ 您未在語音頻道中", inline=True)
    
    await ctx.send(embed=embed)


##############################################################################
# 功能：多播放服務整合支援多伺服器狀態管理的指令
##############################################################################


# ─────────────────────────── stream_play ───────────────────────────

async def stream_play(ctx: commands.Context, url: str, retry: int = 3):
    print(f"DEBUG: stream_play 開始處理 URL: {url}")
    
    gid = ctx.guild.id
    
    # ★ 在函數開頭就定義所有需要的變數
    queue = get_guild_queue(gid)
    current = get_guild_current(gid)
    played = get_guild_played(gid)
    blacklist = get_guild_blacklist(gid)
    
    # ★ 檢查黑名單（在鎖外面檢查）
    if url in blacklist:
        print(f"DEBUG: URL 在黑名單中，跳過: {url}")
        await ctx.send("⚠️ 此影片已知無效，已跳過")
        await play_next(ctx)
        return
    
    lock = play_locks[gid]
    
    # ★ 檢查是否已經有其他播放在進行
    if lock.locked():
        print(f"DEBUG: 播放鎖被佔用，等待或跳過: {url}")
        return
    
    await lock.acquire()
    try:
        print(f"DEBUG: 已獲得播放鎖: {gid}")
        
        # ★ 再次檢查是否有音樂正在播放
        vc = await get_safe_vc(ctx)
        if vc is None:
            return

        # 1. 解析影片
        try:
            print(f"DEBUG: 開始解析影片: {url}")
            
            # ★ 加入 30 秒超時保護
            info = await asyncio.wait_for(ytdlp_extract(url), timeout=30.0)
            audio = info.get("url")
            title = info.get("title", "Unknown")
            
            print(f"DEBUG: 影片解析成功: {title}")

        except asyncio.TimeoutError:
            print(f"DEBUG: 影片解析超時: {url}")
            await ctx.send("⚠️ 影片解析超時（已跳過）")
            
            # 清理邏輯
            blacklist.add(url)
            if queue and queue[0] == url:
                queue.pop(0)
            
            current["url"] = current["title"] = None
            if url in played:
                played.remove(url)
            
            save_state()
            # ★ 注意：play_next 要在鎖釋放後執行
            lock.release()
            await play_next(ctx)
            return

        except yt_dlp.utils.DownloadError as e:
            print(f"DEBUG: DownloadError 觸發，URL: {url}")
            await ctx.send(f"⚠️ 無法播放（已跳過）：{e}")

            # ★ 加入黑名單，永久記住這個失效影片
            blacklist.add(url)
            print(f"DEBUG: 已將 URL 加入黑名單: {url}")

            if queue and queue[0] == url:
                queue.pop(0)
                print(f"DEBUG: 已從佇列移除 URL: {url}")

            current["url"] = current["title"] = None
            
            # 從播放歷史移除
            if url in played:
                played.remove(url)
            
            save_state()
            # ★ 注意：play_next 要在鎖釋放後執行
            lock.release()
            await play_next(ctx)
            return

        # 2. 音訊有效性
        if not audio:
            await ctx.send("⚠️ 找不到音訊來源，已跳過")
            if queue and queue[0] == url:
                queue.pop(0)
            lock.release()
            await play_next(ctx)
            return

        source = discord.FFmpegPCMAudio(audio, **FFMPEG_OPTS)
        if source is None:
            await ctx.send("⚠️ FFmpeg 無法建立音源，已跳過")
            if queue and queue[0] == url:
                queue.pop(0)
            lock.release()
            await play_next(ctx)
            return

        # 3. 記錄 current
        current.update({"url": url, "title": title,
                        "channel_id": ctx.channel.id, "position": 0})
        save_state()
    
        # 4. after callback
        def _after(err=None):
            print(f"DEBUG: _after 被觸發，URL: {url}")
            
            # ★ 重新獲取最新狀態
            current_state = get_guild_current(gid)
            is_from_back = current_state.get("from_back", False)
            
            print(f"DEBUG: _after 狀態檢查 - from_back: {is_from_back}")
            
            # ① 佇列管理
            q = get_guild_queue(gid)
            if q and q[0] == url:
                q.pop(0)

            # ② 錯誤處理
            if err:
                asyncio.run_coroutine_threadsafe(
                    ctx.send(f"⚠️ 播放失敗：{err}"), bot.loop)

            # ③ 獲取播放歷史
            played_list = get_guild_played(gid)
            
            # ④ ★ 關鍵修正：只有非 back 播放才加入歷史
            if not is_from_back:
                played_list.append(url)
                if len(played_list) > 50:
                    played_list.pop(0)
                print(f"DEBUG: _after 正常播放，已加入歷史: {url}")
            else:
                print(f"DEBUG: _after 來自 /back 指令，不加入歷史")
            
            # ⑤ 清空狀態
            current_state["url"] = current_state["title"] = None
            current_state["from_back"] = False
            current_state["processing_back"] = False
            guild_back_count[gid] = 0
            save_state()

            # ⑥ 決定是否繼續播放
            updated_queue = get_guild_queue(gid)

            if is_from_back:
                print(f"DEBUG: _after 來自 /back 指令，檢查是否有續播佇列")
                if updated_queue:
                    print(f"DEBUG: _after 有續播佇列 {len(updated_queue)} 首，開始續播")
                    # ★ 從 /back 也可以繼續播放佇列
                    asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
                else:
                    print(f"DEBUG: _after 來自 /back 指令，無續播佇列，停止播放")
                return
            elif updated_queue:
                print(f"DEBUG: _after 來自正常佇列，播放下一首")
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            else:
                print(f"DEBUG: _after 佇列為空，停止播放")

        # 5. 播放
        try:
            vc.play(source, after=_after)
        except discord.errors.ClientException as e:
            await ctx.send(f"⚠️ 播放器錯誤：{e}")
            if queue and queue[0] == url:
                queue.pop(0)
            lock.release()
            await play_next(ctx)
            return

        await ctx.send(f"🎵 {title}")
        print(f"DEBUG: 播放開始，即將釋放鎖: {gid}")

    finally:
        # ★ 確保鎖一定會被釋放
        if lock.locked():
            lock.release()
            print(f"DEBUG: 鎖已釋放: {gid}")



async def play_youtube_playlist(ctx, url):
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    
    links = await yt_flat_playlist(url, music=False)
    if not links:
        return await ctx.send("播放列表中沒有播放內容")
    
    idle = not (ctx.voice_client.is_playing() or ctx.voice_client.is_paused())
    queue.extend(links)
    save_state()
    await ctx.send(f"已加入 {len(links)} 首 YouTube 歌曲")
    if idle:
        await play_next(ctx)

async def play_ytmusic_playlist(ctx, url):
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    
    links = await yt_flat_playlist(url, music=True)
    if not links:
        return await ctx.send("播放列表中沒有播放內容")
    
    idle = not (ctx.voice_client.is_playing() or ctx.voice_client.is_paused())
    queue.extend(links)
    save_state()
    await ctx.send(f"已加入 {len(links)} 首 YT Music 歌曲")
    if idle:
        await play_next(ctx)

async def play_spotify_track(ctx, url):
    try:
        track = await sp_track(url)
        name = track["name"]
        artist = track["artists"][0]["name"]
        link = await yt_search_first(f"{name} {artist}")
        if not link:
            return await ctx.send("找不到對應的 YouTube 連結")
        await ctx.send(f"🎵 {name} - {artist}")
        await stream_play(ctx, link)
    except Exception as e:
        await ctx.send(f"Spotify 處理發生問題：{e}")

async def play_spotify_playlist(ctx, url):
    guild_id = ctx.guild.id
    queue = get_guild_queue(guild_id)
    
    try:
        pl = await sp_playlist(url)
        items = pl.get("tracks", {}).get("items", [])
        queries = [
            f'{t["track"]["name"]} {t["track"]["artists"][0]["name"]}'
            for t in items if t.get("track")
        ]

        links = []
        for q in queries:
            l = await yt_search_first(q)
            if l:
                links.append(l)

        if not links:
            return await ctx.send("處理播放列表時沒有找到播放內容")

        idle = not (ctx.voice_client.is_playing() or ctx.voice_client.is_paused())
        queue.extend(links)
        save_state()
        await ctx.send(f"已加入 {len(links)} 首 Spotify 歌曲")
        if idle:
            await play_next(ctx)
    except Exception as e:
        await ctx.send(f"Spotify 播放列表發生問題：{e}")

##############################################################################
# 主要運行
##############################################################################
print("載入檔案：", __file__)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("請設定環境變數或配置 DISCORD_TOKEN")
    
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    
    STATE_FILE.parent.mkdir(exist_ok=True)
    bot.run(DISCORD_TOKEN)