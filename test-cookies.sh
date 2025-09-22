#!/bin/bash
# 測試YouTube Cookies是否正常工作

echo "🧪 測試YouTube Cookies..."

echo "1️⃣ 檢查容器狀態:"
docker-compose ps music-bot

echo ""
echo "2️⃣ 檢查cookies文件:"
docker exec music-bot-production ls -la /app/host_files/youtube_cookies.txt
docker exec music-bot-production file /app/host_files/youtube_cookies.txt

echo ""
echo "3️⃣ 檢查cookies內容:"
docker exec music-bot-production head -3 /app/host_files/youtube_cookies.txt

echo ""
echo "4️⃣ 測試環境變數:"
docker exec music-bot-production printenv | grep YOUTUBE

echo ""
echo "5️⃣ 測試yt-dlp with cookies:"
docker exec music-bot-production yt-dlp --cookies /app/host_files/youtube_cookies.txt --get-title --no-warnings "https://www.youtube.com/watch?v=dQw4w9WgXcQ" || echo "❌ Cookies測試失敗"

echo ""
echo "6️⃣ 測試problematic video:"
docker exec music-bot-production yt-dlp --cookies /app/host_files/youtube_cookies.txt --get-title --no-warnings "https://www.youtube.com/watch?v=IJNR2EpS0jw" || echo "❌ 問題影片測試失敗"

echo ""
echo "✅ 測試完成"