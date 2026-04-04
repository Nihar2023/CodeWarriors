# SmartLearn AI — Minimal Frontend

This frontend is intentionally simple: **static HTML + vanilla JS** (no React, no build step).

It talks to your FastAPI backend using the same endpoints defined in `backend/*.py` and uses the JWT returned by:

- `POST /register`
- `POST /login`

The token is stored in `localStorage` and sent as:

`Authorization: Bearer <token>`

## Run it

### 1) Environment variables

In the `CodeWarriors` folder, copy the example env file and edit it:

```bash
copy .env.example .env
```

Set at least `SECRET_KEY` and, for AI features, `GEMINI_API_KEY` (see comments inside `.env`).

### 2) Start the backend (port 8000)

From the `CodeWarriors` folder:

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

On Windows, if `uvicorn` is not found, use `python -m uvicorn` (Scripts folder may not be on `PATH`).

### 3) Serve the frontend (port 3000)

From the `CodeWarriors/frontend` folder:

```bash
python -m http.server 3000
```

Then open `http://localhost:3000` in your browser.

## Notes

- The backend CORS currently allows `http://localhost:3000` and `http://127.0.0.1:3000` (see `backend/main.py`).
- If you change frontend port, update the backend CORS list.

## AI (Gemini)

Personalized quizzes, resource blurbs, recommendations, chat, and learning paths call **Google Gemini** from the backend.

Configure in **`.env`** at the project root (loaded automatically when you start the app via `backend/main.py`):

- `GEMINI_API_KEY` — required for those features
- `GEMINI_MODEL` — optional (see default in `utils/gemini_client.py`)

Without the key, the UI still works; AI endpoints return clear errors or skip text (e.g. empty `personalized_note`).

