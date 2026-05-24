#!/bin/bash
# fetch-ai-review.sh
# 从 GitHub PR 获取 AI 审查评论并保存到本地

set -e

PR_NUMBER="${1:-1}"
REPO="${2:-XGuang4010/LuaN1aoAgent}"
OUTPUT_FILE=".ai-review-last.md"

echo "🔍 Fetching AI review comments from PR #${PR_NUMBER}..."

# 获取 PR 的所有评论
COMMENTS=$(gh api repos/${REPO}/issues/${PR_NUMBER}/comments --jq '.[] | select(.body | contains("🤖 AI Code Review")) | {id: .id, body: .body, created_at: .created_at}' 2>/dev/null || echo "")

if [ -z "$COMMENTS" ]; then
    echo "⚠️ No AI review comments found on PR #${PR_NUMBER}"
    echo "Make sure the AI review workflow has completed and posted a comment."
    exit 1
fi

# 获取最新的一条 AI 评论
LATEST_COMMENT=$(echo "$COMMENTS" | jq -s 'sort_by(.created_at) | last')
REVIEW_BODY=$(echo "$LATEST_COMMENT" | jq -r '.body')
COMMENT_ID=$(echo "$LATEST_COMMENT" | jq -r '.id')

# 保存到本地文件
cat > "${OUTPUT_FILE}" << EOF
# AI Code Review Report
# PR: #${PR_NUMBER}
# Comment ID: ${COMMENT_ID}
# Fetched at: $(date -Iseconds)

${REVIEW_BODY}
EOF

echo "✅ AI review saved to ${OUTPUT_FILE}"
echo "💡 Next step: Ask CodeBuddy Code to fix issues based on this review."
echo "   Example: /review-pr .ai-review-last.md"
