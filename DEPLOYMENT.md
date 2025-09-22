# Discord 音樂機器人部署指南

## 🚀 **GitHub Actions 自動部署**

本指南專注於使用 GitHub Actions workflow 進行自動部署，這是推薦的部署方式。

### **📋 部署流程概述**

1. **🧪 測試階段**: 自動運行單元測試
2. **🔨 構建階段**: 構建 Docker 映像並推送到 GitHub Container Registry
3. **🚀 部署階段**: SSH 連接到您的伺服器並自動部署
4. **📊 通知階段**: 報告部署結果

### **⚙️ 環境變數設定**

#### **Repository Secrets & Variables 設定**

前往 `Repository → Settings → Secrets and variables → Actions`：

**� 必填 Secrets（敏感資訊）**
```bash
DISCORD_TOKEN          # Discord 機器人 Token
SSH_PRIVATE_KEY        # SSH 私鑰內容（用於部署認證）
```

**⚙️ 建議 Variables（非敏感配置）**
```bash
# 🚀 部署設定
DEPLOY_HOST          # 部署伺服器 IP 或域名
DEPLOY_USER          # 部署用的 SSH 用戶名
DEPLOY_PORT          # 部署用的 SSH 端口（如果不是預設的 22）

# 🎵 機器人設定
COMMAND_PREFIX       # 指令前綴（預設 /）
MAX_QUEUE_SIZE       # 最大隊列（預設 100）
MAX_HISTORY_SIZE     # 最大歷史（預設 50）
EXTRACT_TIMEOUT      # 解析超時（預設 30 秒）
KEEPALIVE_INTERVAL   # 保持連接（預設 240 秒）

# 🔒 SSH 遠端功能設定（用於 /jable 指令，可選）
SSH_HOST             # SSH 遠端功能伺服器地址
SSH_PORT             # SSH 連接埠（預設: 22）
SSH_USER             # SSH 遠端功能用戶名
```

**🔒 SSH 遠端功能 Secrets（可選，用於 /jable 指令）**
```bash
SSH_REMOTE_KEY       # SSH 遠端功能的私鑰內容（如果 SSH 遠端功能需要私鑰認證）
```

**👥 權限控制 Secrets（可選）**
```bash
ALLOWED_IDS=123456789,987654321  # 允許使用特殊功能的用戶ID（逗號分隔）
```

### **🔑 Discord Bot Token 取得**

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)
2. 創建新應用程式或選擇現有應用程式
3. 左側選單 → `Bot`
4. 點擊 `Reset Token` 並複製新的 Token
5. 設定機器人權限：
   - ✅ `Send Messages`
   - ✅ `Use Slash Commands`
   - ✅ `Connect`
   - ✅ `Speak`
   - ✅ `Use Voice Activity`

### **🔧 部署伺服器準備**

#### **1. 安裝 Docker 和 Docker Compose**
```bash
# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# 安裝 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 重新登入以應用群組變更
newgrp docker
```

#### **2. 設定 SSH 金鑰**

**在本地生成 SSH 金鑰對：**
```bash
# 生成新的 SSH 金鑰對
ssh-keygen -t rsa -b 4096 -C "github-actions-deploy"

# 預設會儲存在 ~/.ssh/id_rsa (私鑰) 和 ~/.ssh/id_rsa.pub (公鑰)
```

**將公鑰添加到部署伺服器：**
```bash
# 如果使用預設端口 22
ssh-copy-id -i ~/.ssh/id_rsa.pub user@your-server.com

# 如果使用自定義端口（例如 2222）
ssh-copy-id -i ~/.ssh/id_rsa.pub -p 2222 user@your-server.com

# 方法二：手動添加（預設端口）
cat ~/.ssh/id_rsa.pub | ssh user@your-server.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"

# 方法二：手動添加（自定義端口）
cat ~/.ssh/id_rsa.pub | ssh -p 2222 user@your-server.com "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

**將私鑰添加到 GitHub Secrets：**
```bash
# 複製完整的私鑰內容（包含 -----BEGIN 和 -----END 行）
cat ~/.ssh/id_rsa

# 將輸出的完整內容貼到 GitHub Secrets 的 DEPLOY_SSH_KEY 中
```

#### **3. 創建部署目錄**
```bash
# 在部署伺服器上創建目錄
mkdir -p ~/discord-music-bot
cd ~/discord-music-bot
```

### **👥 獲取 Discord 用戶 ID（權限控制）**

1. 在 Discord 中啟用開發者模式：
   - `使用者設定` → `進階` → `開發者模式` 開啟
2. 右鍵點擊您的用戶頭像 → `複製使用者 ID`
3. 將 ID 添加到 GitHub Secrets 的 `ALLOWED_IDS` 中

### **🚀 觸發部署**

#### **自動觸發**
- 推送代碼到 `main` 分支時自動觸發：
  ```bash
  git add .
  git commit -m "Deploy bot"
  git push origin main
  ```

#### **手動觸發**
1. 前往 GitHub Repository
2. 點擊 `Actions` 頁籤
3. 選擇 `🚀 Deploy Discord Music Bot` workflow
4. 點擊 `Run workflow`

### **📊 監控部署**

#### **GitHub Actions 監控**
- 在 `Actions` 頁面查看部署進度
- 每個階段都有詳細的日誌輸出
- 部署失敗會顯示錯誤訊息

#### **伺服器監控**
```bash
# 查看容器狀態
docker-compose ps

# 查看機器人日誌
docker-compose logs -f music-bot

# 查看資源使用
docker stats
```

### **🛠️ 常見問題排除**

#### **1. SSH 連接失敗**
```bash
# 檢查 SSH 連接（預設端口 22）
ssh -i ~/.ssh/id_rsa user@your-server.com

# 檢查 SSH 連接（自定義端口）
ssh -i ~/.ssh/id_rsa -p 2222 user@your-server.com

# 檢查 authorized_keys 權限
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys

# 確認伺服器 SSH 服務狀態
sudo systemctl status ssh
sudo systemctl status sshd

# 檢查防火牆設定（如果使用自定義端口）
sudo ufw status
sudo ufw allow 2222/tcp  # 允許自定義 SSH 端口
```

#### **2. Docker 權限問題**
```bash
# 確保用戶在 docker 群組中
sudo usermod -aG docker $USER
newgrp docker

# 測試 Docker 權限
docker ps
```

#### **3. 機器人無法連接**
- 檢查 `DISCORD_TOKEN` 是否正確
- 確認機器人已加入 Discord 伺服器
- 檢查機器人權限設定

#### **4. 部署失敗**
```bash
# 在伺服器上手動測試
cd ~/discord-music-bot
docker-compose down
docker-compose pull
docker-compose up -d
```

### **🔄 更新部署**

每次推送到 `main` 分支都會自動觸發更新部署：

1. **測試新功能** → 自動運行測試
2. **構建新映像** → 構建並推送到 GitHub Container Registry
3. **更新部署** → SSH 到伺服器並更新容器
4. **驗證部署** → 檢查容器狀態

### **📝 部署檢查清單**

**設定前檢查：**
- [ ] Discord Bot Token 已取得
- [ ] 部署伺服器已準備（Docker 已安裝）
- [ ] SSH 金鑰已設定
- [ ] GitHub Secrets 已配置（包含 DEPLOY_PORT 如果使用自定義端口）
- [ ] 防火牆允許 SSH 端口連接

**部署後驗證：**
- [ ] GitHub Actions 執行成功
- [ ] 容器正常運行 (`docker-compose ps`)
- [ ] 機器人在 Discord 中顯示在線
- [ ] 測試基本指令 (`/ping`)

### **🔒 安全性最佳實踐**

1. **SSH 安全**
   - 使用 SSH 金鑰而非密碼
   - 定期更換 SSH 金鑰
   - 限制 SSH 存取 IP（如果可能）
   - 使用非標準 SSH 端口以減少攻擊

2. **Token 安全**
   - 定期重新生成 Discord Bot Token
   - 絕不在代碼中硬編碼 Token
   - 使用 GitHub Secrets 儲存敏感資訊

3. **伺服器安全**
   - 保持系統更新
   - 設定防火牆規則
   - 定期備份重要數據

### **📋 快速部署摘要**

1. **設定 Discord Bot** → 取得 Token
2. **準備伺服器** → 安裝 Docker，設定 SSH
3. **配置 GitHub Secrets** → 添加必要的環境變數
4. **推送代碼** → 自動觸發部署
5. **驗證運行** → 檢查機器人狀態

就這麼簡單！推送代碼後，GitHub Actions 會自動處理測試、構建和部署的整個流程。

---

需要其他幫助，請參考：
- 📖 `README.md` - 專案概述和功能說明
- 🔧 `env-setup-guide.md` - 詳細的環境變數說明