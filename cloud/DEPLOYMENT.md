# Hari Cloud Service - Deployment Guide

Complete guide to deploying the Cloudflare Workers cloud service for heartbeat tracking and motivational nudges.

## Overview

The cloud service provides:
- **Heartbeat tracking**: Your laptop pings the service every hour
- **Motivational nudges**: Get messages when inactive for 48+ hours
- **Accountability**: Streak tracking and encouragement
- **Privacy**: Only stores timestamps and minimal stats

## Prerequisites

1. **Cloudflare account** (free): https://dash.cloudflare.com/sign-up
2. **Node.js** installed (for Wrangler CLI)
3. **Telegram bot** already created (from Phase 3)

## Step 1: Install Wrangler CLI

```bash
# Install globally
npm install -g wrangler

# Or use npx (no install needed)
npx wrangler --version
```

## Step 2: Login to Cloudflare

```bash
wrangler login
```

This opens your browser for authentication.

## Step 3: Create D1 Database

```bash
# Navigate to cloud directory
cd cloud/

# Create database
wrangler d1 create hari-users
```

**Important**: Copy the `database_id` from the output!

Example output:
```
✅ Successfully created DB 'hari-users'

[[d1_databases]]
binding = "DB"
database_name = "hari-users"
database_id = "abc123-def456-ghi789"  ← COPY THIS
```

## Step 4: Update wrangler.toml

Edit `cloud/wrangler.toml` and replace `YOUR_DATABASE_ID_HERE` with your actual ID:

```toml
[[d1_databases]]
binding = "DB"
database_name = "hari-users"
database_id = "abc123-def456-ghi789"  # Your ID here
```

## Step 5: Initialize Database Schema

```bash
# Apply schema to database
wrangler d1 execute hari-users --file=schema.sql
```

Verify it worked:
```bash
wrangler d1 execute hari-users --command="SELECT name FROM sqlite_master WHERE type='table'"
```

Should show: `users`

## Step 6: Set Bot Token Secret

```bash
# Set your Telegram bot token as a secret
wrangler secret put BOT_TOKEN
```

When prompted, paste your Telegram bot token (from @BotFather).

**Important**: This is stored securely and never exposed in logs or code.

## Step 7: Deploy Worker

```bash
# Deploy to production
wrangler deploy
```

You'll get a URL like:
```
✅ Deployed to https://hari-cloud.your-subdomain.workers.dev
```

**Copy this URL!** You'll need it for configuration.

## Step 8: Test Deployment

### Test health check:
```bash
curl https://hari-cloud.your-subdomain.workers.dev/health
```

Should return:
```json
{
  "status": "ok",
  "service": "hari-cloud",
  "version": "1.0.0"
}
```

### Test heartbeat:
```bash
curl -X POST https://hari-cloud.your-subdomain.workers.dev/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"YOUR_TELEGRAM_CHAT_ID"}'
```

Should return:
```json
{
  "ok": true,
  "timestamp": 1708459200000
}
```

### Test status:
```bash
curl "https://hari-cloud.your-subdomain.workers.dev/status?chat_id=YOUR_TELEGRAM_CHAT_ID"
```

Should return your user data.

## Step 9: Configure Hari Daemon

Edit `~/.hari/config.json`:

```json
{
  "pomodoro": {
    "work_duration_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "sessions_until_long_break": 4
  },
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  },
  "cloud": {
    "enabled": true,
    "heartbeat_endpoint": "https://hari-cloud.your-subdomain.workers.dev/heartbeat",
    "threshold_hours": 48
  }
}
```

## Step 10: Test End-to-End

### Start service:
```bash
cd /home/susha/Desktop/portfolio/hari
./hari-services
```

### Check logs:
Look for:
```
[INFO] [telegram] Cloud heartbeat enabled: https://hari-cloud...
[INFO] [telegram] Cloud heartbeat sent successfully
```

### Trigger nudge manually (for testing):
```bash
# Wait 48 hours OR directly trigger
curl -X POST https://hari-cloud.your-subdomain.workers.dev/check-nudges \
  -H "X-Internal: true"
```

You should receive a Telegram message!

## Step 11: Verify Cron (Automatic Nudges)

Cron runs every hour automatically. Check cron logs:

```bash
wrangler tail
```

You'll see:
```
Cron triggered at: 2026-02-20T10:00:00.000Z
Nudge check completed
```

## Monitoring & Logs

### View real-time logs:
```bash
wrangler tail
```

### View dashboard:
https://dash.cloudflare.com → Workers → hari-cloud

Shows:
- Request count
- Error rate
- Latency
- Cron execution history

### Query database:
```bash
# List all users
wrangler d1 execute hari-users --command="SELECT * FROM users"

# Check specific user
wrangler d1 execute hari-users --command="SELECT * FROM users WHERE chat_id='YOUR_ID'"
```

## Updating the Worker

When you make changes to `worker.js`:

```bash
# Deploy updates
wrangler deploy

# Or deploy with a version tag
wrangler deploy --tag v1.1.0
```

## Cost Tracking

### Free tier limits:
- 100,000 requests/day
- 5M D1 reads/day
- 5GB D1 storage

### Check usage:
https://dash.cloudflare.com → Workers → Analytics

### Estimate your usage:
- 1 user: 24 heartbeats/day
- 1000 users: 24,000 requests/day (well within free tier)

## Troubleshooting

### "Database not found"
```bash
# Recreate database
wrangler d1 create hari-users
wrangler d1 execute hari-users --file=schema.sql
```

### "BOT_TOKEN not set"
```bash
# Reset secret
wrangler secret put BOT_TOKEN
```

### "503 Service Unavailable"
- Worker might be deploying (wait 30 seconds)
- Check Cloudflare status: https://www.cloudflarestatus.com/

### "Telegram messages not sending"
```bash
# Test bot token manually
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

### "Heartbeats not working"
Check service logs:
```bash
# Look for heartbeat errors
grep "heartbeat" ~/.hari/events.log
```

## Security Notes

1. **Bot token is secret** - Never commit to git
2. **HTTPS only** - Worker enforces SSL
3. **Rate limiting** - Add if getting abused:
   ```javascript
   // In worker.js
   if (requests_from_ip > 100) {
     return new Response('Rate limited', { status: 429 });
   }
   ```

4. **Authentication** - Optional: Add API key:
   ```javascript
   const apiKey = request.headers.get('X-API-Key');
   if (apiKey !== env.API_KEY) {
     return new Response('Unauthorized', { status: 401 });
   }
   ```

## Next Steps

1. **Customize nudge messages** - Edit `craftNudgeMessage()` in `worker.js`
2. **Add more endpoints** - Stats, analytics, custom commands
3. **Mobile app** - Connect to this API
4. **Multi-user** - It's already ready! Just distribute the service

## Support

- **Cloudflare Docs**: https://developers.cloudflare.com/workers/
- **Wrangler CLI**: https://developers.cloudflare.com/workers/wrangler/
- **D1 Database**: https://developers.cloudflare.com/d1/

---

**Status: Ready for Production! 🚀**

Your cloud service is now deployed and tracking your productivity!
