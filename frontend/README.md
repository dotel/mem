# PomodoroAI Frontend

Next.js app: Pomodoro timer, AI chatbot, and Knowledge Base (Memory).

## Setup

1. Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL` if your API runs elsewhere (default `http://127.0.0.1:8765`).
2. Start the Hari backend: `python hari.py run` (from repo root). Ensure FastAPI and auth deps are installed: `pip install -r requirements.txt`.
3. Install and run the frontend:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Register an account first, then sign in.

## Features

- **Login / Register**: JWT-based auth. Create an account with name, email, and password.
- **Pomodoro**: Work / Short Break / Long Break modes, timer display, progress bar, Start/Pause/Reset/Settings controls.
- **Chat**: AI productivity assistant. Ask about time management, goals, or documents in your Knowledge Base.
- **Memory (Knowledge Base)**: Add websites or documents for the chatbot to reference. Uses RAG (in production).
