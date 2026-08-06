#!/bin/bash
# S.S.T ローカルテスト実行スクリプト
# 実行方法: ./tests/run_tests.sh (ワークスペースルートから)

echo "======================================"
echo "S.S.T Local Test Runner"
echo "======================================"

echo "[1/2] Running Linter (Ruff)..."
uv run ruff check . || echo "⚠️ Ruff found linting issues, but continuing..."

echo ""
echo "[2/2] Running Unit Tests (Pytest)..."
uv run pytest tests/ -v

echo ""
echo "======================================"
echo "Testing Complete."
echo "======================================"
