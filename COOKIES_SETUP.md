# 🍪 YouTube Cookies 安全設置指南

## ⚠️ 重要安全提醒
**絕對不要將YouTube cookies文件推送到GitHub或任何公開倉庫！**

## 🔑 設置方法

### 方法1: 使用GitHub Secrets (推薦)

1. **提取cookies內容**:
   ```bash
   cat youtube_cookies.txt
   ```

2. **添加到GitHub Secrets**:
   - 前往 GitHub倉庫 → Settings → Secrets and variables → Actions
   - 點擊 "New repository secret"
   - 名稱: `YOUTUBE_COOKIES_CONTENT`
   - 值: 貼上整個cookies文件的內容

3. **更新部署workflow**:
   GitHub Actions會自動將這個secret作為環境變數傳遞給容器

### 方法2: 手動上傳到服務器

1. **上傳cookies文件**:
   ```bash
   scp youtube_cookies.txt deploy@free:~/discord-music-bot/
   ```

2. **確保文件權限**:
   ```bash
   ssh deploy@free "chmod 600 ~/discord-music-bot/youtube_cookies.txt"
   ```

## 🧪 測試cookies是否工作

```bash
# 本地測試
yt-dlp --cookies youtube_cookies.txt --get-title "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# 服務器測試
docker exec music-bot-production yt-dlp --cookies /app/cookies/youtube_cookies.txt --get-title "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## 🔄 Cookies更新

如果cookies過期，需要重新提取並更新：

1. 重新從瀏覽器提取cookies
2. 更新GitHub Secret或重新上傳文件
3. 重新部署容器

## 🛡️ 安全最佳實踐

- ✅ 使用 `.gitignore` 排除cookies文件
- ✅ 使用環境變數或Secrets管理敏感數據
- ✅ 定期更新cookies (建議每月)
- ✅ 限制文件權限 (600)
- ❌ 絕不推送cookies到版本控制系統