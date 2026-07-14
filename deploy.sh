#!/usr/bin/env bash
# 一键部署到 GitHub Pages
# 用法：bash deploy.sh <你的GitHub用户名> [仓库名]
set -e

USER="${1:-}"
REPO="${2:-lijing-life}"

if [ -z "$USER" ]; then
  echo "用法: bash deploy.sh <你的GitHub用户名> [仓库名，默认 lijing-life]"
  echo ""
  echo "前置条件："
  echo "  1. 已在 GitHub 上创建同名仓库（可选，命令会尝试用 gh 创建）"
  echo "  2. 已配置 git 用户和 SSH key 或 gh CLI"
  exit 1
fi

cd "$(dirname "$0")"

if [ ! -d .git ]; then
  git init -b main
fi

git add .
git commit -m "update: 立鲸人生成长系统" || echo "无变更"

# 优先用 gh CLI 创建 + push
if command -v gh >/dev/null 2>&1; then
  if ! gh repo view "$USER/$REPO" >/dev/null 2>&1; then
    echo "创建 GitHub 仓库 $USER/$REPO ..."
    gh repo create "$USER/$REPO" --public --source=. --remote=origin --push
  else
    git remote get-url origin >/dev/null 2>&1 || git remote add origin "git@github.com:$USER/$REPO.git"
    git push -u origin main
  fi
  echo "开启 GitHub Pages ..."
  gh api "repos/$USER/$REPO/pages" -X POST -f source[branch]=main -f source[path]=/ 2>/dev/null \
    || gh api "repos/$USER/$REPO/pages" -X PUT -f source[branch]=main -f source[path]=/ 2>/dev/null \
    || echo "（可能已开启，请去 Settings → Pages 手动确认）"
  echo ""
  echo "✅ 部署完成！访问："
  echo "   https://$USER.github.io/$REPO/"
  echo ""
  echo "首次开启 Pages 可能需要等待 1-3 分钟才生效。"
else
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "git@github.com:$USER/$REPO.git"
  git push -u origin main
  echo ""
  echo "已推送。请去 https://github.com/$USER/$REPO/settings/pages 手动开启 GitHub Pages。"
fi
