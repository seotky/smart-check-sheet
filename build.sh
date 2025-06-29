gcloud auth login
gcloud config set project hackathon2025-sotky
gcloud services enable compute.googleapis.com run.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com

# sample.envファイルから環境変数を読み込んでgcloud run deployに渡す
ENV_VARS=$(grep -v '^#' .env | grep -v '^$' | grep -v '^GOOGLE_APPLICATION_CREDENTIALS=' | tr '\n' ',' | sed 's/,$//')
gcloud run deploy my-app --region "asia-northeast1" --source . \
    --allow-unauthenticated --quiet \
    --set-env-vars="$ENV_VARS" \
    --service-account="express-mode@hackathon2025-sotky.iam.gserviceaccount.com"
