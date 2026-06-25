# ============================================================
#  MX GEO Report — Cloud Run Job 배포 스크립트 (PowerShell)
#
#  사전 준비:
#    - gcloud CLI 설치 및 로그인:  gcloud auth login
#    - 결제 연결된 GCP 프로젝트
#    - 아래 CONFIG 값 수정
#
#  실행:  .\deploy\deploy_cloudrun.ps1
#  (이 스크립트는 리포지토리 루트에서 실행해야 함 — 빌드 컨텍스트에 raw_data/ 포함)
# ============================================================
$ErrorActionPreference = "Stop"

# ── CONFIG ──────────────────────────────────────────────────
$PROJECT_ID = "your-project-id"            # ← 수정
$REGION     = "asia-northeast3"            # 서울 리전
$REPO       = "mx-geo"                     # Artifact Registry 저장소명
$IMAGE_NAME = "mx-geo-report"
$JOB_NAME   = "mx-geo-report"
$BUCKET     = "your-project-id-mx-geo-reports"   # ← 전역 고유해야 함
$SA_NAME    = "mx-geo-report-job"          # 잡 전용 서비스 계정
$SECRET     = "score-claude-api-key"       # Secret Manager 시크릿명
$USE_LLM    = "1"

$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$IMAGE_NAME:latest"
$SA_EMAIL = "$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
$GCS_URI = "gs://$BUCKET/reports"

Write-Host "▶ Project: $PROJECT_ID / Region: $REGION" -ForegroundColor Cyan
gcloud config set project $PROJECT_ID

# ── 1) 필요한 API 활성화 ────────────────────────────────────
Write-Host "▶ Enabling APIs..." -ForegroundColor Cyan
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  secretmanager.googleapis.com `
  storage.googleapis.com

# ── 2) Artifact Registry 저장소 (없으면 생성) ───────────────
Write-Host "▶ Ensuring Artifact Registry repo..." -ForegroundColor Cyan
$repoExists = gcloud artifacts repositories describe $REPO --location=$REGION 2>$null
if (-not $?) {
  gcloud artifacts repositories create $REPO `
    --repository-format=docker --location=$REGION `
    --description="MX GEO report images"
}

# ── 3) GCS 출력 버킷 (없으면 생성) ──────────────────────────
Write-Host "▶ Ensuring output bucket gs://$BUCKET ..." -ForegroundColor Cyan
$bucketExists = gcloud storage buckets describe "gs://$BUCKET" 2>$null
if (-not $?) {
  gcloud storage buckets create "gs://$BUCKET" --location=$REGION --uniform-bucket-level-access
}

# ── 4) Secret Manager: Claude API 키 ────────────────────────
#  최초 1회만 값 입력. 이후 실행 시 이미 존재하면 건너뜀.
Write-Host "▶ Ensuring secret '$SECRET' ..." -ForegroundColor Cyan
$secretExists = gcloud secrets describe $SECRET 2>$null
if (-not $?) {
  gcloud secrets create $SECRET --replication-policy=automatic
  $key = Read-Host "  Claude API 키를 입력하세요 (Score_Claude_API_KEY)" -AsSecureString
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))
  $plain | gcloud secrets versions add $SECRET --data-file=-
}

# ── 5) 잡 전용 서비스 계정 + 권한 ───────────────────────────
Write-Host "▶ Ensuring service account..." -ForegroundColor Cyan
$saExists = gcloud iam service-accounts describe $SA_EMAIL 2>$null
if (-not $?) {
  gcloud iam service-accounts create $SA_NAME --display-name="MX GEO Report Job"
}
# 버킷에 결과 업로드 권한
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" `
  --member="serviceAccount:$SA_EMAIL" --role="roles/storage.objectAdmin" | Out-Null
# 시크릿 읽기 권한
gcloud secrets add-iam-policy-binding $SECRET `
  --member="serviceAccount:$SA_EMAIL" --role="roles/secretmanager.secretAccessor" | Out-Null

# ── 6) 이미지 빌드 & 푸시 (Cloud Build) ─────────────────────
#  raw_data/ (~95MB) 포함 → 업로드에 다소 시간 소요.
Write-Host "▶ Building & pushing image via Cloud Build..." -ForegroundColor Cyan
gcloud builds submit --tag $IMAGE .

# ── 7) Cloud Run Job 생성/갱신 ──────────────────────────────
#  엑셀(최대 40MB) + pandas 메모리 여유 위해 2Gi / 타임아웃 30분.
Write-Host "▶ Deploying Cloud Run Job..." -ForegroundColor Cyan
$jobExists = gcloud run jobs describe $JOB_NAME --region=$REGION 2>$null
$action = if ($?) { "update" } else { "create" }
gcloud run jobs $action $JOB_NAME `
  --image=$IMAGE `
  --region=$REGION `
  --service-account=$SA_EMAIL `
  --memory=2Gi `
  --cpu=2 `
  --task-timeout=1800s `
  --max-retries=1 `
  --set-env-vars="USE_LLM=$USE_LLM,OUTPUT_GCS_URI=$GCS_URI" `
  --set-secrets="Score_Claude_API_KEY=${SECRET}:latest"

# ── 8) 즉시 실행 ────────────────────────────────────────────
Write-Host "▶ Executing job now..." -ForegroundColor Cyan
gcloud run jobs execute $JOB_NAME --region=$REGION

Write-Host ""
Write-Host "✔ 완료. 결과 확인:" -ForegroundColor Green
Write-Host "    gcloud storage ls $GCS_URI/"
Write-Host "  로그:"
Write-Host "    gcloud run jobs executions list --job=$JOB_NAME --region=$REGION"
