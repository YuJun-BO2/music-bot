#!/bin/bash
# 安全的YouTube Cookies部署腳本
# 使用環境變數來傳遞敏感的cookies數據

echo "🍪 安全部署YouTube Cookies..."

# 檢查是否設置了cookies環境變數
if [ -z "$YOUTUBE_COOKIES_CONTENT" ]; then
    echo "❌ 錯誤: YOUTUBE_COOKIES_CONTENT 環境變數未設置"
    echo "請在GitHub Secrets中設置此變數"
    exit 1
fi

# 創建cookies目錄
mkdir -p /app/cookies

# 將環境變數中的cookies內容寫入文件
echo "$YOUTUBE_COOKIES_CONTENT" > /app/cookies/youtube_cookies.txt

# 設置適當的權限
chmod 600 /app/cookies/youtube_cookies.txt

echo "✅ YouTube Cookies 已安全部署"
echo "📍 位置: /app/cookies/youtube_cookies.txt"