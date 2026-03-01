# Hari Cloud Service

Serverless backend for heartbeat tracking and motivational nudges using Cloudflare Workers + D1.

## Architecture

```
Your Laptop (Hari Daemon)
    ↓ Hourly heartbeat
Cloudflare Worker (Edge)
    ↓ Store timestamp
D1 Database (SQLite@Edge)
    ↓ Cron checks
Telegram Bot API
    ↓ Send nudge
You (Mobile/Desktop)
```


## Features

- **Heartbeat Tracking**: Daemon (or hari-services) pings every hour when active
- **Smart Nudges**: Get messages after 48+ hours of inactivity
- **Goal Reminders**: If you have a daily focus goal and haven’t met it by the reminder hour (default 8pm UTC), get a Telegram reminder with minutes left
- **Streak Protection**: "Your 7-day streak is waiting!"
- **Privacy-First**: Only stores timestamps and minimal stats
- **Free & Scalable**: Supports 4,000 users on free tier

## Quick Start

### 1. Deploy Worker

```bash
cd cloud/
npm install -g wrangler
wrangler login
wrangler d1 create hari-users
# Copy database_id to wrangler.toml
wrangler d1 execute hari-users --file=schema.sql
wrangler secret put BOT_TOKEN
wrangler deploy
```

### 2. Configure Daemon

Edit `~/.hari/config.json`:

```json
{
  "cloud": {
    "enabled": true,
    "heartbeat_endpoint": "https://hari-cloud.YOUR-SUBDOMAIN.workers.dev/heartbeat",
    "threshold_hours": 48
  }
}
```

### 3. Start services

For **goal reminders** you need **hari-services** (Python) running so it can send goal + today’s work minutes in the heartbeat. hari-services sends a simple heartbeat; hari-services sends an enriched one when `cloud.enabled` and `heartbeat_endpoint` and `telegram.chat_id` are set.

```bash
./hari-services
```

Service logs will show when heartbeat is sent successfully.  
Python sends heartbeat every hour with `stats: { today_work_minutes, goal_minutes, goal_label }` so the worker can send “goal not met today” reminders.

## API Endpoints

### POST /heartbeat
Receive heartbeat from laptop (or from hari-services with goal + today’s stats).

**Request:**
```json
{
  "chat_id": "123456789",
  "stats": {
    "today_work_minutes": 45,
    "goal_minutes": 90,
    "goal_label": "2h deep work",
    "current_streak": 7,
    "total_sessions": 42
  }
}
```

When `stats` includes goals and `today_work_minutes`, the cron sends a **goal reminder** (once per day, at the configured hour) for any goal not yet met. Multiple goals are supported: send `stats.goals` as an array of `{ goal_minutes, goal_label }`. Backward compat: a single `goal_minutes` (and optional `goal_label`) still works.

**Response:**
```json
{
  "ok": true,
  "timestamp": 1708459200000
}
```

### GET /status
Query user status

**Request:**
```
GET /status?chat_id=123456789
```

**Response:**
```json
{
  "chat_id": "123456789",
  "last_heartbeat": 1708459200000,
  "hours_since_last_seen": 2.5,
  "stats": { "current_streak": 7 },
  "settings": { "nudges_enabled": true }
}
```

### POST /check-nudges
Manually trigger nudge check (cron calls this automatically)

**Response:**
```json
{
  "checked": 100,
  "sent": 5,
  "failed": 0,
  "goal_reminders_sent": 2
}
```

### POST /settings
Update user settings

**Request:**
```json
{
  "chat_id": "123456789",
  "settings": {
    "nudges_enabled": true,
    "goal_reminders_enabled": true,
    "goal_reminder_hour_utc": 20,
    "threshold_hours": 48
  }
}
```

## Goal reminders

If the heartbeat includes `stats.goal_minutes` and `stats.today_work_minutes`, the worker can send a **goal reminder** when the user hasn’t met their goal by a set hour (default **20:00 UTC**):

- Runs in the same hourly cron as inactivity nudges.
- Only sends if `today_work_minutes < goal_minutes` and the current hour (UTC) is at least `goal_reminder_hour_utc`.
- At most **once per day** per user (`last_goal_reminder` is updated).
- Disable per user with `settings.goal_reminders_enabled: false`.

**Requirement:** Run **hari-services**  so the heartbeat includes goal and today’s work minutes. Set a daily goal with e.g. `hari goal 90 minutes a day`.

**Migration:** If you deployed before goal reminders existed, add the column:
```bash
wrangler d1 execute hari-users --command="ALTER TABLE users ADD COLUMN last_goal_reminder INTEGER;"
```

## Database Schema

```sql
CREATE TABLE users (
    chat_id TEXT PRIMARY KEY,
    last_heartbeat INTEGER,
    last_nudge INTEGER,
    last_goal_reminder INTEGER,
    settings TEXT,  -- JSON
    stats TEXT,     -- JSON
    created_at INTEGER,
    updated_at INTEGER
);
```

## Cron Schedule

Runs every hour (`0 * * * *`):

1. **Inactivity nudges**: Users with no heartbeat for 48+ hours get a motivational nudge (at most once per 24h).
2. **Goal reminders**: Users with a goal set and `today_work_minutes < goal_minutes` at or after `goal_reminder_hour_utc` (default 20:00 UTC) get a reminder (at most once per day).

## Cost Analysis

### Free Tier (Current)
- 100k requests/day
- 5M D1 reads/day
- **Supports: ~4,000 active users**
- **Cost: $0/month**

### Paid Tier (If needed)
- 10M requests/month = $5
- **Supports: ~13,000 users**
- **Cost per user: $0.00038/month**

At 100k users: ~$25/month

## Privacy

**What we store:**
- Telegram chat ID
- Last heartbeat timestamp
- Optional: streak count, total sessions

**What we DON'T store:**
- Session details
- Window titles
- Usage data
- Personal information

## Development

### Local Testing

```bash
# Start dev server
wrangler dev

# Test endpoints
curl http://localhost:8787/health
curl -X POST http://localhost:8787/heartbeat \
  -d '{"chat_id":"test"}'
```

### View Logs

```bash
# Real-time logs
wrangler tail

# Check D1 data
wrangler d1 execute hari-users --command="SELECT * FROM users LIMIT 5"
```

### Update Worker

```bash
# Deploy changes
wrangler deploy

# With version tag
wrangler deploy --tag v1.1.0
```

## Monitoring

**Dashboard:** https://dash.cloudflare.com/workers/hari-cloud

Shows:
- Requests/day
- Error rate  
- Latency (p50, p99)
- Cron execution history

## Security

- ✅ HTTPS enforced
- ✅ Bot token stored as secret
- ✅ CORS configured
- ✅ SQL injection protected (parameterized queries)
- ✅ Rate limiting (can add if needed)

## Files

- `worker.js` - Main Worker code (180 lines)
- `schema.sql` - Database schema
- `wrangler.toml` - Configuration
- `DEPLOYMENT.md` - Full deployment guide
- `README.md` - This file

## Troubleshooting

**Heartbeats not sending?**
- Check events: `grep heartbeat ~/.hari/events.log` (if logged there)
- Verify endpoint in config
- Test manually: `curl -X POST <endpoint> -d '{"chat_id":"your_id"}'`

**Nudges not received?**
- Check cron logs: `wrangler tail`
- Verify bot token: `wrangler secret list`
- Test: `curl -X POST <endpoint>/check-nudges`

**Database errors?**
- Reinitialize: `wrangler d1 execute hari-users --file=schema.sql`
- Check binding in wrangler.toml

## Future Enhancements

- [ ] Streak tracking with graphs
- [ ] Custom nudge schedules
- [ ] Weekly/monthly summaries
- [ ] Multiple notification channels
- [ ] Team accountability features
- [ ] Public leaderboards (opt-in)

## Support

- **Cloudflare Workers**: https://developers.cloudflare.com/workers/
- **D1 Database**: https://developers.cloudflare.com/d1/
- **Wrangler CLI**: https://developers.cloudflare.com/workers/wrangler/

---

**Status: Production Ready** 🚀

Free, scalable, and privacy-first cloud backend for Hari!
