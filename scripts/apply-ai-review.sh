#!/bin/bash
# apply-ai-review.sh
# 一键拉取 AI Review、应用修复、推送到 PR 的自动化工作流
#
# Usage:
#   ./scripts/apply-ai-review.sh [PR_NUMBER] [BRANCH]
#
# Example:
#   ./scripts/apply-ai-review.sh 1 scope-boundary

set -e

PR_NUMBER="${1:-1}"
BRANCH="${2:-$(git branch --show-current)}"
REPO="${REPO:-XGuang4010/LuaN1aoAgent}"
REVIEW_FILE=".ai-review-last.md"
FIX_PLAN=".ai-fix-plan.md"

echo "========================================"
echo "🤖 AI Review → Fix → Push 自动化工作流"
echo "========================================"
echo ""

# --- Step 1: Fetch AI Review ---
echo "📥 Step 1: 拉取 PR #${PR_NUMBER} 的 AI Review..."
./scripts/fetch-ai-review.sh "${PR_NUMBER}" "${REPO}" || {
    echo "❌ 获取 AI Review 失败，退出"
    exit 1
}

# --- Step 2: Parse actionable items ---
echo ""
echo "📋 Step 2: 解析可修复项..."

# 从 AI review 中提取 ⚠️ 和 ❌ 标记的项
grep -E "^[\s]*[-•*][\s]*[⚠️❌]" "${REVIEW_FILE}" > "${FIX_PLAN}" 2>/dev/null || true

if [ ! -s "${FIX_PLAN}" ]; then
    echo "✅ AI Review 未发现问题，无需修复"
    exit 0
fi

echo "📝 发现以下待修复项："
cat "${FIX_PLAN}"
echo ""

# --- Step 3: Prepare context for CodeBuddy Code ---
echo "========================================"
echo "🛠️ Step 3: 准备修复上下文"
echo "========================================"
echo ""
echo "已生成以下文件："
echo "  - ${REVIEW_FILE}   : 完整 AI Review 报告"
echo "  - ${FIX_PLAN}      : 待修复项清单"
echo ""
echo "👉 你可以通过以下方式继续："
echo ""
echo "【方式 A】让 CodeBuddy Code 自动修复（推荐）"
echo "   在 CodeBuddy Code 中输入："
echo ""
echo '   请根据 .ai-review-last.md 中的 AI Code Review 结果，'
echo '   逐条修复 .ai-fix-plan.md 中列出的问题。'
echo '   修复完成后提交并推送到当前分支。'
echo ""
echo "【方式 B】手动review后修复"
echo "   1. 阅读 ${REVIEW_FILE}"
echo "   2. 手动修改代码"
echo "   3. git add && git commit && git push origin ${BRANCH}"
echo ""
echo "========================================"

# 可选：自动创建 commit message 模板
cat > ".ai-fix-commit-msg.txt" << EOF
fix: address AI code review feedback on PR #${PR_NUMBER}

AI Review Comment ID: $(grep -oP 'Comment ID: \K[0-9]+' "${REVIEW_FILE}" || echo "unknown")

Fixed items:
$(sed 's/^/- /' "${FIX_PLAN}")
EOF

echo "✅ 修复计划已保存到 ${FIX_PLAN}"
echo "✅ Commit message 模板已保存到 .ai-fix-commit-msg.txt"
