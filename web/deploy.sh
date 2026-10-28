#!/usr/bin/env bash
set -e

# ====================================================================
# md-to-word Web Playground 远程部署脚本
# 目标服务器: 124.220.135.226 (root)
# 部署路径: /opt/md-to-word
# 服务端口: 127.0.0.1:8799 (通过 Nginx 80 端口反向代理)
# ====================================================================

REMOTE_HOST="124.220.135.226"
REMOTE_USER="root"
REMOTE_DIR="/opt/md-to-word"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 1. 正在同步代码到服务器 ${REMOTE_HOST}:${REMOTE_DIR} ..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}"

rsync -avz --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.DS_Store' \
  --exclude 'video_build' \
  --exclude 'tmp_*' \
  "${LOCAL_ROOT}/src" \
  "${LOCAL_ROOT}/presets" \
  "${LOCAL_ROOT}/web" \
  "${LOCAL_ROOT}/pyproject.toml" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> 2. 正在远程配置 Python 虚拟环境与安装依赖..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'EOF'
set -e
cd /opt/md-to-word

if [ ! -d ".venv" ]; then
  echo "创建 Python3.11 独立虚拟环境..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip -q

echo "安装排版核心引擎与 Web 服务依赖..."
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  python-docx>=1.1.0 \
  lxml>=4.9.0 \
  PyYAML>=6.0 \
  latex2mathml>=3.0 \
  citeproc-py>=0.6 \
  pypdfium2>=4.30 \
  fastapi>=0.100.0 \
  uvicorn>=0.22.0 \
  python-multipart>=0.0.6 \
  requests>=2.28.0 \
  -q

echo "安装 md_to_word 本地可编辑包..."
pip install -e . --no-deps -q

echo "依赖检查完成！"
EOF

echo "==> 3. 正在配置 systemd 守护进程..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'EOF'
cat << 'SERVICE' > /etc/systemd/system/md-to-word-web.service
[Unit]
Description=md-to-word Web Playground Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/md-to-word
ExecStart=/opt/md-to-word/.venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8799
Restart=always
RestartSec=3
Environment=PYTHONPATH=/opt/md-to-word/src

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable md-to-word-web.service
systemctl restart md-to-word-web.service
systemctl status md-to-word-web.service --no-pager | head -n 12
EOF

echo "==> 4. 正在配置 Nginx 反向代理..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'EOF'
CONF="/www/server/panel/vhost/nginx/claude-gateway-http.conf"

cat << 'NGINX' > "${CONF}"
server {
    listen 80;
    server_name 124.220.135.226;

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }

    location / {
        proxy_pass http://127.0.0.1:8799;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        client_max_body_size 50M;
    }
}
NGINX

/www/server/nginx/sbin/nginx -t
/www/server/nginx/sbin/nginx -s reload
EOF

echo "==> 5. 验证服务公网健康状态..."
sleep 2
curl -s http://127.0.0.1:8799/api/health || true

echo "=========================================================="
echo "🎉 部署完成！"
echo "公网访问地址: http://${REMOTE_HOST}"
echo "=========================================================="
