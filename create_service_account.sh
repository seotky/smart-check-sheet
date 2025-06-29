#!/bin/bash

# 設定
PROJECT_ID="hackathon2025-sotky"
SERVICE_ACCOUNT_NAME="smart-check-sheet-sa"
SERVICE_ACCOUNT_DISPLAY_NAME="Smart Check Sheet Service Account"
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=== Smart Check Sheet サービスアカウント作成スクリプト ==="
echo "プロジェクトID: ${PROJECT_ID}"
echo "サービスアカウント名: ${SERVICE_ACCOUNT_NAME}"
echo ""

# 1. サービスアカウントの作成
echo "1. サービスアカウントを作成中..."
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
    --display-name="${SERVICE_ACCOUNT_DISPLAY_NAME}" \
    --description="Smart Check Sheet application sechrvice account" \
    --project=${PROJECT_ID}

if [ $? -ne 0 ]; then
    echo "エラー: サービスアカウントの作成に失敗しました。"
    exit 1
fi

echo "✅ サービスアカウントが作成されました: ${SERVICE_ACCOUNT_EMAIL}"

# 2. 必要な権限を付与
echo ""
echo "2. 必要な権限を付与中..."

# Document AI 関連の権限
echo "  - Document AI 関連の権限を付与..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/documentai.apiUser"

# Gemini API 関連の権限
echo "  - Gemini API 関連の権限を付与..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/aiplatform.user"

# Cloud SQL 関連の権限（必要に応じて）
echo "  - Cloud SQL 関連の権限を付与..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SERVICE_ACCOUNT_EMAIL}" \
    --role="roles/cloudsql.client"
