# 多階段構建：依賴安裝階段
FROM python:3.11-slim as dependencies

# 安裝系統依賴（只一次）
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 設定 pip 優化
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 最終階段：應用程式
FROM python:3.11-slim

# 只安裝運行時必需的系統依賴
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 從依賴階段複製已安裝的 Python 套件
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# 設定工作目錄
WORKDIR /app

# 創建非 root 用戶
RUN useradd -m -u 1000 botuser

# 創建必要目錄並設定權限
RUN mkdir -p /app/logs /app/data && chown -R botuser:botuser /app

# 複製應用程式代碼（放在最後以利用 Docker 層緩存）
COPY --chown=botuser:botuser . .

# 切換到非 root 用戶
USER botuser

# 設定環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 健康檢查（簡化版）
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=2 \
    CMD pgrep -f "python.*main.py" > /dev/null || exit 1

# 啟動命令
CMD ["python", "main.py"]