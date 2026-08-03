#!/usr/bin/env bash
#
# deploy.sh — 一键部署到 GitHub Pages 并验证
#
# 用法:
#   ./deploy.sh                   # 使用默认提交信息
#   ./deploy.sh "自定义提交信息"
#
# 流程: 提交 -> 推送 main -> 等待 Pages 部署 -> 哈希比对验证线上文件
set -euo pipefail
cd "$(dirname "$0")"

SITE_URL="https://RavenWang1103.github.io/wildlife-map"
BRANCH="main"
WAIT_MAX=300                        # 等待 Pages 重建的最长秒数
MSG="${1:-feat: 更新}"
# 需要校验与本地逐字节一致的线上文件（路径即本地相对路径）
FILES=("index.html" "data/animals.json" "data/100000_full.json" "css/tailwind.css")

say() { printf '%s\n' "$*"; }
die() { say "失败: $*"; exit 1; }
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
sha_url() { curl -fsS -m 25 "$1" 2>/dev/null | shasum -a 256 | cut -d' ' -f1; }

say "==> [1/4] 本地检查"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "当前目录不是 git 仓库"
if git check-ignore -q .env; then
  say "  OK  .env 已被 .gitignore 忽略，密钥不会上传"
else
  die ".env 未被忽略！请先将其加入 .gitignore"
fi
say "  待提交/未跟踪文件:"
git status --short || true

say "==> [2/4] 提交并推送"
git add index.html css/tailwind.css data/ scripts/ web_2.py server.py deploy.sh
if git diff --cached --quiet; then
  say "  没有需要提交的更改，跳过提交"
else
  git commit -m "$MSG"
  say "  已提交: $MSG"
fi
git push origin "$BRANCH"
say "  已推送到 origin/$BRANCH"

say "==> [3/4] 等待 GitHub Pages 部署新版本（最长 ${WAIT_MAX}s）"
LOCAL_SHA=$(sha index.html)
say "  本地 index.html SHA256: ${LOCAL_SHA:0:12}..."
elapsed=0
while [ "$elapsed" -lt "$WAIT_MAX" ]; do
  if [ "$(sha_url "$SITE_URL/index.html")" = "$LOCAL_SHA" ]; then
    say "  线上 index.html 与本地一致，部署已生效"
    break
  fi
  sleep 10
  elapsed=$((elapsed + 10))
  say "  已等待 ${elapsed}s ..."
done
[ "$(sha_url "$SITE_URL/index.html")" = "$LOCAL_SHA" ] \
  || die "等待超时，页面未更新。请检查 GitHub 仓库 Settings > Pages 是否配置为从 main 分支部署"

say "==> [4/4] 验证线上资源（HTTP + 哈希一致）"
for f in "${FILES[@]}"; do
  url="$SITE_URL/$f"
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 25 "$url" || echo 000)
  if [ "$code" != "200" ]; then
    die "$code  $url 资源访问失败"
  fi
  if [ "$(sha_url "$url")" = "$(sha "$f")" ]; then
    say "  OK  $code  ${url}（与本地一致）"
  else
    die "$url 内容与本地不一致，请检查提交是否完整"
  fi
done

say ""
say "部署完成: $SITE_URL"
