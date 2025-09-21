# Discord音樂機器人部署指南

## 🚀 快速部署

### 1. 環境準備
```bash
# 安裝Python依賴
pip install -r requirements.txt

# 安裝FFmpeg (Windows)
# 下載: https://ffmpeg.org/download.html
# 解壓並將bin資料夾加入系統PATH
```

### 2. Discord Bot設定
1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)
2. 創建新應用程式 → Bot → 獲取Token
3. 設定權限:
   - `Send Messages`
   - `Connect` (語音)
   - `Speak` (語音)
   - `Use Voice Activity`

### 3. 配置機器人
```python
# 在 fixed_music_bot.py 中填入
DISCORD_TOKEN = "你的機器人Token"
ALLOWED_IDS = {你的用戶ID}  # 可選，限制特殊功能使用者
```

### 4. 啟動機器人
```bash
python fixed_music_bot.py
```

## 🌐 生產環境部署

### 選項1: VPS部署
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip ffmpeg
pip3 install -r requirements.txt

# 使用screen或tmux保持運行
screen -S musicbot
python3 fixed_music_bot.py
# Ctrl+A+D 離開screen
```

### 選項2: Docker部署
```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "fixed_music_bot.py"]
```

### 選項3: Heroku部署
1. 創建 `Procfile`:
   ```
   worker: python fixed_music_bot.py
   ```
2. 添加buildpack: `heroku/python`
3. 設定環境變數: `DISCORD_TOKEN`

## 🔧 進階配置

### 環境變數配置 (推薦)
```python
import os
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SSH_HOST = os.getenv('SSH_HOST', '')
SSH_USER = os.getenv('SSH_USER', '')
```

### PM2 管理 (Linux)
```bash
npm install -g pm2
pm2 start "python3 fixed_music_bot.py" --name musicbot
pm2 startup  # 開機自啟
pm2 save
```

## 📊 監控與維護

### 日誌監控
```python
# 建議在 main 中加入
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("musicbot.log"),
        logging.StreamHandler()
    ]
)
```

### 狀態檢查指令
- `/ping` - 檢查延遲
- `/voice_debug` - 語音連接診斷
- `/debug_state` - 播放狀態診斷
- `/status` - 當前播放狀態

## ⚠️ 注意事項

1. **Token安全**: 絕不要將Token推送到公開倉庫
2. **資源限制**: 長時間運行需要穩定的記憶體和網路
3. **API限制**: 注意YouTube API的請求限制
4. **權限設定**: 確保機器人有足夠的Discord權限