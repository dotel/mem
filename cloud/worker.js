/**
 * Hari Cloud Service - Cloudflare Worker
 * 
 * Serverless backend for:
 * - Heartbeat tracking (laptop activity)
 * - Nudge notifications (motivational messages)
 * - Accountability features
 * 
 * Free tier: 100k requests/day (supports ~4k users)
 * Scales automatically to millions of users
 */

export default {
  /**
   * Main request handler
   */
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // CORS headers for all responses
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Content-Type': 'application/json'
    };
    
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }
    
    try {
      // Route handlers
      if (url.pathname === '/heartbeat' && request.method === 'POST') {
        return await handleHeartbeat(request, env, corsHeaders);
      }
      
      if (url.pathname === '/status' && request.method === 'GET') {
        return await handleStatus(request, env, corsHeaders);
      }
      
      if (url.pathname === '/check-nudges' && request.method === 'POST') {
        return await handleCheckNudges(request, env, corsHeaders);
      }
      
      if (url.pathname === '/settings' && request.method === 'POST') {
        return await handleSettings(request, env, corsHeaders);
      }
      
      // Health check
      if (url.pathname === '/health') {
        return new Response(JSON.stringify({ 
          status: 'ok', 
          service: 'hari-cloud',
          version: '1.0.0'
        }), { headers: corsHeaders });
      }
      
      // 404
      return new Response(JSON.stringify({ 
        error: 'Not found',
        endpoints: ['/heartbeat', '/status', '/check-nudges', '/settings', '/health']
      }), { 
        status: 404, 
        headers: corsHeaders 
      });
      
    } catch (error) {
      console.error('Error:', error);
      return new Response(JSON.stringify({ 
        error: error.message 
      }), { 
        status: 500, 
        headers: corsHeaders 
      });
    }
  },
  
  /**
   * Cron trigger - runs every hour
   * Checks for users who need nudges
   */
  async scheduled(event, env, ctx) {
    console.log('Cron triggered at:', new Date().toISOString());
    
    try {
      // Call check-nudges internally
      const request = new Request('http://localhost/check-nudges', {
        method: 'POST',
        headers: { 'X-Internal': 'true' }
      });
      
      await this.fetch(request, env);
      console.log('Nudge check completed');
    } catch (error) {
      console.error('Cron error:', error);
    }
  }
};

/**
 * Handle heartbeat from user's laptop
 * Updates last_seen timestamp
 */
async function handleHeartbeat(request, env, corsHeaders) {
  const { chat_id, stats } = await request.json();
  
  if (!chat_id) {
    return new Response(JSON.stringify({ 
      error: 'chat_id required' 
    }), { 
      status: 400, 
      headers: corsHeaders 
    });
  }
  
  const now = Date.now();
  
  // Update or insert user
  await env.DB.prepare(`
    INSERT INTO users (chat_id, last_heartbeat, stats, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET
      last_heartbeat = excluded.last_heartbeat,
      stats = excluded.stats,
      updated_at = excluded.updated_at
  `).bind(
    chat_id,
    now,
    JSON.stringify(stats || {}),
    now
  ).run();
  
  console.log(`Heartbeat received from ${chat_id}`);
  
  return new Response(JSON.stringify({ 
    ok: true,
    timestamp: now
  }), { 
    headers: corsHeaders 
  });
}

/**
 * Get user status
 */
async function handleStatus(request, env, corsHeaders) {
  const url = new URL(request.url);
  const chat_id = url.searchParams.get('chat_id');
  
  if (!chat_id) {
    return new Response(JSON.stringify({ 
      error: 'chat_id required' 
    }), { 
      status: 400, 
      headers: corsHeaders 
    });
  }
  
  const user = await env.DB.prepare(
    'SELECT * FROM users WHERE chat_id = ?'
  ).bind(chat_id).first();
  
  if (!user) {
    return new Response(JSON.stringify({ 
      error: 'User not found' 
    }), { 
      status: 404, 
      headers: corsHeaders 
    });
  }
  
  const hoursAgo = (Date.now() - user.last_heartbeat) / (1000 * 60 * 60);
  
  return new Response(JSON.stringify({
    chat_id: user.chat_id,
    last_heartbeat: user.last_heartbeat,
    hours_since_last_seen: Math.round(hoursAgo * 10) / 10,
    stats: JSON.parse(user.stats || '{}'),
    settings: JSON.parse(user.settings || '{}')
  }), { 
    headers: corsHeaders 
  });
}

/**
 * Check for users who need nudges and send them
 * 1) Inactivity nudges (no heartbeat for 48h+)
 * 2) Goal reminders (goal not met today, send once per day at reminder hour)
 */
async function handleCheckNudges(request, env, corsHeaders) {
  const settings = {
    threshold_hours: 48,
    enabled: true
  };

  const threshold_ms = settings.threshold_hours * 60 * 60 * 1000;
  const cutoff = Date.now() - threshold_ms;
  const oneDayMs = 24 * 60 * 60 * 1000;
  const now = Date.now();

  // --- 1) Inactivity nudges ---
  const { results: inactiveUsers } = await env.DB.prepare(`
    SELECT chat_id, last_heartbeat, settings, stats
    FROM users
    WHERE last_heartbeat < ?
    AND (last_nudge IS NULL OR last_nudge < ?)
  `).bind(cutoff, now - oneDayMs).all();

  let sent = 0;
  let failed = 0;

  for (const user of inactiveUsers) {
    const userSettings = JSON.parse(user.settings || '{}');
    if (userSettings.nudges_enabled === false) continue;

    const hoursAgo = Math.round((now - user.last_heartbeat) / (1000 * 60 * 60));
    const stats = JSON.parse(user.stats || '{}');
    const message = craftNudgeMessage(hoursAgo, stats);
    const success = await sendTelegram(env.BOT_TOKEN, user.chat_id, message);

    if (success) {
      await env.DB.prepare('UPDATE users SET last_nudge = ? WHERE chat_id = ?')
        .bind(now, user.chat_id).run();
      sent++;
      console.log(`Inactivity nudge sent to ${user.chat_id}`);
    } else {
      failed++;
    }
  }

  // --- 2) Goal reminders (goal not met today, once per day) ---
  const goalReminderHourUtc = 20; // 8pm UTC default
  const todayStartUtc = new Date(Date.UTC(
    new Date().getUTCFullYear(),
    new Date().getUTCMonth(),
    new Date().getUTCDate()
  )).getTime();

  const { results: allActive } = await env.DB.prepare(`
    SELECT chat_id, last_heartbeat, last_goal_reminder, settings, stats
    FROM users
    WHERE last_heartbeat > ?
  `).bind(now - oneDayMs).all();

  let goalSent = 0;
  const currentHourUtc = new Date().getUTCHours();

  for (const user of allActive) {
    const userSettings = JSON.parse(user.settings || '{}');
    if (userSettings.goal_reminders_enabled === false) continue;

    const hourUtc = userSettings.goal_reminder_hour_utc ?? goalReminderHourUtc;
    if (currentHourUtc < hourUtc) continue;

    const stats = JSON.parse(user.stats || '{}');
    const todayWorkMinutes = stats.today_work_minutes ?? 0;

    // Support multiple goals: stats.goals[] or single stats.goal_minutes (backward compat)
    const goalItems = Array.isArray(stats.goals) && stats.goals.length > 0
      ? stats.goals
      : (stats.goal_minutes != null && stats.goal_minutes > 0
          ? [{ goal_minutes: stats.goal_minutes, goal_label: stats.goal_label }]
          : []);

    const unmet = goalItems.filter(
      (g) => (g.goal_minutes ?? 0) > 0 && todayWorkMinutes < (g.goal_minutes ?? 0)
    );
    if (unmet.length === 0) continue;

    const lastGoalReminder = user.last_goal_reminder ?? 0;
    if (lastGoalReminder >= todayStartUtc) continue; // already sent today

    const message = craftGoalReminderMessage(todayWorkMinutes, unmet);

    const success = await sendTelegram(env.BOT_TOKEN, user.chat_id, message);
    if (success) {
      await env.DB.prepare(
        'UPDATE users SET last_goal_reminder = ? WHERE chat_id = ?'
      ).bind(now, user.chat_id).run();
      goalSent++;
      console.log(`Goal reminder sent to ${user.chat_id}`);
    } else {
      failed++;
    }
  }

  return new Response(JSON.stringify({
    checked: inactiveUsers.length,
    sent,
    failed,
    goal_reminders_sent: goalSent
  }), {
    headers: corsHeaders
  });
}

/**
 * Update user settings
 */
async function handleSettings(request, env, corsHeaders) {
  const { chat_id, settings } = await request.json();
  
  if (!chat_id) {
    return new Response(JSON.stringify({ 
      error: 'chat_id required' 
    }), { 
      status: 400, 
      headers: corsHeaders 
    });
  }
  
  await env.DB.prepare(`
    UPDATE users SET settings = ?, updated_at = ?
    WHERE chat_id = ?
  `).bind(
    JSON.stringify(settings),
    Date.now(),
    chat_id
  ).run();
  
  return new Response(JSON.stringify({ 
    ok: true 
  }), { 
    headers: corsHeaders 
  });
}

/**
 * Craft a motivational nudge message (inactivity)
 */
function craftNudgeMessage(hoursAgo, stats) {
  const streak = stats.current_streak || 0;

  if (hoursAgo >= 72) {
    return `🌟 Haven't seen you in ${Math.floor(hoursAgo / 24)} days! Ready to get back on track?`;
  }
  if (hoursAgo >= 48) {
    if (streak > 0) {
      return `🔥 Your ${streak}-day streak is waiting! Start a focus session?`;
    }
    return `🤔 2 days without focus time. Everything okay? Ready to start a timer?`;
  }
  return `⏰ Time for some productive work? Start a pomodoro session!`;
}

/**
 * Craft goal-reminder message (one or more goals not met today).
 * unmet: array of { goal_minutes, goal_label }
 */
function craftGoalReminderMessage(todayWorkMinutes, unmet) {
  if (!unmet || unmet.length === 0) return null;

  if (unmet.length === 1) {
    const g = unmet[0];
    const goal = g.goal_minutes ?? 0;
    const remaining = goal - todayWorkMinutes;
    const label = (g.goal_label && ` (${g.goal_label})`) || '';
    if (todayWorkMinutes === 0) {
      return `🎯 Your daily goal${label} is ${goal} minutes. You haven't clocked any focus yet today — start a session?`;
    }
    return `🎯 You're at ${todayWorkMinutes} min today; goal is ${goal} min${label}. ${remaining} minutes to go — one more block?`;
  }

  const lines = unmet.map((g) => {
    const goal = g.goal_minutes ?? 0;
    const remaining = goal - todayWorkMinutes;
    const label = (g.goal_label && ` ${g.goal_label}`) || `${goal} min`;
    return `• ${label}: ${remaining} min to go`;
  });
  const intro = todayWorkMinutes === 0
    ? "🎯 You haven't clocked any focus yet today. Goals:"
    : `🎯 You're at ${todayWorkMinutes} min today. Still to meet:`;
  return intro + "\n" + lines.join("\n") + "\n\nStart a session?";
}

/**
 * Send message via Telegram Bot API
 */
async function sendTelegram(token, chatId, text) {
  if (!token) {
    console.error('BOT_TOKEN not configured');
    return false;
  }
  
  try {
    const response = await fetch(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text: text,
          parse_mode: 'HTML'
        })
      }
    );
    
    const result = await response.json();
    return result.ok === true;
  } catch (error) {
    console.error('Telegram API error:', error);
    return false;
  }
}
