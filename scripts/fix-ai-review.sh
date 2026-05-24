#!/bin/bash
# fix-ai-review.sh
# 全自动工作流：获取 AI Review → 解析问题 → 分配给子代理修复 → 提交推送
#
# Usage:
#   ./scripts/fix-ai-review.sh [PR_NUMBER] [BRANCH]
#
# 依赖:
#   - gh CLI (已认证)
#   - CodeBuddy Code Agent 功能
#   - 当前分支有未提交的改动时会中止

set -e

PR_NUMBER="${1:-1}"
BRANCH="${2:-$(git branch --show-current)}"
REPO="${REPO:-XGuang4010/LuaN1aoAgent}"
REVIEW_FILE=".ai-review-last.md"
FIX_PLAN=".ai-fix-plan.md"
FIXES_DIR=".ai-fixes"

echo "========================================"
echo "🤖 全自动 AI Review 修复工作流"
echo "========================================"
echo ""

# --- 前置检查 ---
if ! command -v gh &> /dev/null; then
    echo "❌ gh CLI 未安装"
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "⚠️ 当前分支有未提交的改动"
    echo "请先提交或 stash 现有改动，再运行自动修复"
    git status --short
    exit 1
fi

# --- Step 1: 拉取 AI Review ---
echo "📥 Step 1: 拉取 PR #${PR_NUMBER} 的 AI Review..."
./scripts/fetch-ai-review.sh "${PR_NUMBER}" "${REPO}" || exit 1

# --- Step 2: 解析问题清单 ---
echo ""
echo "📋 Step 2: 解析待修复项..."

mkdir -p "${FIXES_DIR}"

# 提取带文件路径的问题（尝试匹配 `文件:行号` 或 `path/to/file.py` 模式）
grep -n "" "${REVIEW_FILE}" | grep -E "[⚠️❌]" > "${FIXES_DIR}/raw_issues.txt" || true

if [ ! -s "${FIXES_DIR}/raw_issues.txt" ]; then
    echo "✅ AI Review 未标记严重问题，无需修复"
    rm -rf "${FIXES_DIR}"
    exit 0
fi

echo "📝 发现 $(wc -l < "${FIXES_DIR}/raw_issues.txt") 个待修复项"

# --- Step 3: 生成修复指令给 CodeBuddy Code ---
echo ""
echo "🛠️ Step 3: 生成修复计划..."

cat > "${FIX_PLAN}" << 'EOF'
# AI Review 修复计划

基于 `.ai-review-last.md` 中的审查结果，请按以下步骤执行：

## 修复原则
1. 优先修复 ❌（严重）级别的问题
2. 其次修复 ⚠️（建议）级别的问题
3. 保持代码风格与现有项目一致
4. 修复后运行 `python -m py_compile` 检查语法

## 执行步骤
1. 阅读 `.ai-review-last.md` 获取完整上下文
2. 针对每个标记了文件路径的问题，定位并修复
3. 如无明确路径，根据问题描述推断受影响文件
4. 修复完成后验证（如适用）
5. 使用以下 message 提交：
   `fix: address AI code review feedback on PR #PR_NUMBER`

## 注意事项
- 不要引入新的依赖
- 不要修改与 review 无关的代码
- 如某条建议不适用，在回复中说明原因
EOF

echo "✅ 修复计划已保存到 ${FIX_PLAN}"

# --- Step 4: 提示用户下一步 ---
echo ""
echo "========================================"
echo "👉 下一步操作"
echo "========================================"
echo ""
echo "【推荐】在 CodeBuddy Code 中执行："
echo ""
echo "   请根据以下文件中的 AI Code Review 结果修复代码问题："
echo "   - 审查报告: .ai-review-last.md"
echo "   - 修复计划: .ai-fix-plan.md"
echo ""
echo "   修复完成后，提交并推送到 ${BRANCH} 分支。"
echo ""
echo "【或者】手动修复："
echo "   1. 阅读 ${REVIEW_FILE}"
echo "   2. 手动修改对应文件"
echo "   3. git add . && git commit -F .ai-fix-commit-msg.txt"
echo "   4. git push origin ${BRANCH}"
echo ""
echo "========================================"

# 生成 commit message
cat > ".ai-fix-commit-msg.txt" << EOF
fix: address AI code review feedback on PR #${PR_NUMBER}

AI Review: ${REVIEW_FILE}

$(cat "${FIXES_DIR}/raw_issues.txt" | sed 's/^[0-9]*:/-/' | head -20)
EOF

echo "✅ Commit message 模板: .ai-fix-commit-msg.txt"
echo "✅ 修复完成后，PR 会自动更新"
