# Google Cloud Deployment Notes

This is the recommended MVP setup for Heuristics AI LLC's PDF-first sentiment reporting product.

## What To Create First

1. Google Workspace
   - Create the company Workspace for `heuristicsaisolutions.com`.
   - Use named accounts, not shared passwords.
   - Suggested groups:
     - `founders@heuristicsaisolutions.com`
     - `engineering@heuristicsaisolutions.com`
     - `clients@heuristicsaisolutions.com`

2. Google Cloud project
   - Create one project for the MVP, for example `heuristics-sentiment-prod`.
   - Link billing.
   - Enable these APIs:
     - Cloud Run
     - Cloud Run Jobs
     - Cloud Scheduler
     - Artifact Registry
     - Cloud Build
     - Secret Manager
     - Cloud Storage

3. Storage bucket
   - Create a bucket for report PDFs, for example `heuristics-sentiment-reports`.
   - Start with uniform bucket-level access.
   - Do not make it public.

## Access Pattern

Do not share Google passwords. Add users through IAM.

For someone setting up deployment, grant these roles temporarily at the project level:

- Cloud Run Admin
- Cloud Scheduler Admin
- Artifact Registry Administrator
- Cloud Build Editor
- Secret Manager Admin
- Storage Admin
- Service Account User

After deployment is working, reduce broad admin roles where possible.

## Runtime Secrets

Store these in Secret Manager or Cloud Run environment variables:

```env
GEMINI_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=script:sentiment-analyzer:1.0.0 (by /u/your_reddit_username)
X_BEARER_TOKEN=
SERPER_API_KEY=
SOCIAL_LOOKBACK_DAYS=7
REPORT_KEYWORDS=OptioRx,Optio Rx,optiorx
REPORT_GCS_BUCKET=heuristics-sentiment-reports
REPORT_GCS_PREFIX=sentiment-reports
```

## Deploy The Internal App

Build and deploy the container to Cloud Run:

```bash
gcloud run deploy sentiment-analyzer-admin \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GRADIO_SHARE=false
```

For a real client/admin tool, switch away from `--allow-unauthenticated` and put authentication in front of it.

## Create The Scheduled Report Job

Create a Cloud Run Job using the same source/container and override the command:

```bash
gcloud run jobs deploy sentiment-report-job \
  --source . \
  --region us-central1 \
  --command python \
  --args jobs/generate_scheduled_reports.py \
  --set-env-vars REPORT_GCS_BUCKET=heuristics-sentiment-reports,REPORT_GCS_PREFIX=sentiment-reports
```

Run it manually:

```bash
gcloud run jobs execute sentiment-report-job --region us-central1
```

Schedule it weekly:

```bash
gcloud scheduler jobs create http weekly-sentiment-report \
  --location us-central1 \
  --schedule "0 9 * * MON" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/sentiment-report-job:run" \
  --http-method POST \
  --oauth-service-account-email PROJECT_NUMBER-compute@developer.gserviceaccount.com
```

Replace `PROJECT_ID` and `PROJECT_NUMBER` with the Google Cloud project values.

## MVP Architecture

```text
Google Workspace
  - company email
  - client folders
  - manual PDF sharing

Google Cloud Run
  - internal Gradio/admin app
  - scheduled report job

Cloud Scheduler
  - weekly/daily trigger

Cloud Storage
  - generated PDF archive
```

## Next Product Steps

1. Add client-specific report config.
2. Add branded report cover pages.
3. Add email delivery through Gmail API or a transactional email provider.
4. Add a lightweight admin dashboard.
5. Add database-backed client/report history.
