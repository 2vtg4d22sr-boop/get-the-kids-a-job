# Daily Job Automation

This folder powers the unattended Bailey + Morgan scan.

## Required GitHub Actions secrets
- OPENAI_API_KEY
- SUPABASE_SERVICE_ROLE_KEY

Never commit either secret to the repository.

## Schedule
The workflow uses two UTC cron entries plus an America/Chicago guard so the effective run remains around 8:30 AM Central across daylight-saving changes. It can also be run manually from GitHub Actions.

## Data safety
The scanner upserts by stable job_key. Existing user tracking fields are never overwritten:
interested, applied, interview, offer, date_applied, application_status, notes.

Old jobs are not automatically deleted.
