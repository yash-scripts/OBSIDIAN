from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
import os
import datetime
import urllib.request
import urllib.parse

app = FastAPI(title="Obsidian AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Data files ──────────────────────────────────────────────
TASKS_FILE = "tasks.json"
EVENTS_FILE = "events.json"

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── Models ───────────────────────────────────────────────────
class ChatMessage(BaseModel):
    message: str
    history: Optional[List[dict]] = []

class Task(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    due_date: Optional[str] = None
    priority: Optional[str] = "medium"
    completed: Optional[bool] = False

class CalendarEvent(BaseModel):
    id: Optional[str] = None
    title: str
    date: str
    time: Optional[str] = None
    description: Optional[str] = ""

class SearchQuery(BaseModel):
    query: str

# ── Ollama helper ─────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

def call_ollama(prompt: str, system: str = "") -> str:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 1024
        }
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "No response from Ollama.")
    except ConnectionRefusedError:
        return "⚠️ Ollama is not running! Open a terminal and run: ollama serve"
    except Exception as e:
        return f"⚠️ AI error: {str(e)}"

# ── Routes ────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "Obsidian AI running", "model": OLLAMA_MODEL}

@app.get("/health")
def health():
    """Check if Ollama is reachable"""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return {"ollama": "online", "models": models, "active_model": OLLAMA_MODEL}
    except:
        return {"ollama": "offline", "message": "Run: ollama serve"}

# CHAT
@app.post("/chat")
def chat(body: ChatMessage):
    tasks = load_json(TASKS_FILE)
    events = load_json(EVENTS_FILE)
    pending = [t for t in tasks if not t.get("completed")]
    today = datetime.date.today().isoformat()

    system = f"""You are Obsidian AI, a personal AI assistant. Today is {today}.
The user has {len(pending)} pending tasks and {len(events)} calendar events.
Be concise, helpful, and proactive. If the user mentions tasks or scheduling,
offer to help manage them. Keep responses under 200 words unless asked for more."""

    history_text = ""
    for h in (body.history or [])[-6:]:
        role = h.get("role", "user")
        history_text += f"{role.capitalize()}: {h.get('content', '')}\n"

    full_prompt = f"{history_text}User: {body.message}\nAssistant:"
    reply = call_ollama(full_prompt, system)
    return {"reply": reply}

# TASKS
@app.get("/tasks")
def get_tasks():
    return load_json(TASKS_FILE)

@app.post("/tasks")
def create_task(task: Task):
    tasks = load_json(TASKS_FILE)
    task.id = str(datetime.datetime.now().timestamp()).replace(".", "")
    tasks.append(task.dict())
    save_json(TASKS_FILE, tasks)
    return task

@app.put("/tasks/{task_id}")
def update_task(task_id: str, task: Task):
    tasks = load_json(TASKS_FILE)
    for i, t in enumerate(tasks):
        if t["id"] == task_id:
            updated = {**t, **task.dict(exclude_unset=True), "id": task_id}
            tasks[i] = updated
            save_json(TASKS_FILE, tasks)
            return updated
    raise HTTPException(404, "Task not found")

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    tasks = load_json(TASKS_FILE)
    tasks = [t for t in tasks if t["id"] != task_id]
    save_json(TASKS_FILE, tasks)
    return {"status": "deleted"}

# CALENDAR
@app.get("/calendar")
def get_events():
    return load_json(EVENTS_FILE)

@app.post("/calendar")
def create_event(event: CalendarEvent):
    events = load_json(EVENTS_FILE)
    event.id = str(datetime.datetime.now().timestamp()).replace(".", "")
    events.append(event.dict())
    save_json(EVENTS_FILE, events)
    return event

@app.delete("/calendar/{event_id}")
def delete_event(event_id: str):
    events = load_json(EVENTS_FILE)
    events = [e for e in events if e["id"] != event_id]
    save_json(EVENTS_FILE, events)
    return {"status": "deleted"}

# SEARCH
@app.post("/search")
def search(body: SearchQuery):
    encoded = urllib.parse.quote(body.query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_redirect=1&no_html=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ObsidianAI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", "Answer"),
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL", "")
            })
        for r in data.get("RelatedTopics", [])[:5]:
            if isinstance(r, dict) and r.get("Text"):
                results.append({
                    "title": r.get("Text", "")[:60],
                    "snippet": r.get("Text", ""),
                    "url": r.get("FirstURL", "")
                })

        if results:
            snippets = "\n".join([r["snippet"] for r in results[:3]])
            summary = call_ollama(
                f"Summarize these search results for '{body.query}' in 2-3 sentences:\n{snippets}"
            )
        else:
            summary = f"No results found for '{body.query}'."

        return {"results": results, "summary": summary, "query": body.query}
    except Exception as e:
        return {"results": [], "summary": f"Search error: {str(e)}", "query": body.query}

# WEEKLY REPORT
@app.get("/report")
def weekly_report():
    tasks = load_json(TASKS_FILE)
    events = load_json(EVENTS_FILE)

    completed = [t for t in tasks if t.get("completed")]
    pending = [t for t in tasks if not t.get("completed")]

    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    recent_events = [e for e in events if e.get("date", "") >= week_ago]

    prompt = f"""Generate a concise weekly personal productivity report:
- Completed tasks ({len(completed)}): {[t['title'] for t in completed[:5]]}
- Pending tasks ({len(pending)}): {[t['title'] for t in pending[:5]]}
- Events this week ({len(recent_events)}): {[e['title'] for e in recent_events[:5]]}
- Today: {datetime.date.today().isoformat()}

Write an encouraging, insightful report with highlights and suggestions for the week ahead.
Use markdown formatting with sections."""

    report = call_ollama(prompt)
    return {
        "report": report,
        "stats": {
            "completed": len(completed),
            "pending": len(pending),
            "total_tasks": len(tasks),
            "events_this_week": len(recent_events)
        }
    }