"""
arena.py — Мини LM Arena (PRO Edition + Fixed Save)
════════════════════════════════════════════════════════════════
Продвинутая версия с режимом дискуссии, Markdown-рендерингом
и поддержкой генерации изображений (Function Calling).
Исправлена функция сохранения истории тестов в JSON.
Безопасная версия: ключ API читается из переменных окружения.
"""

import json
import random
import threading
import os
import urllib.request
import urllib.parse
import httpx
from flask import Flask, request, jsonify, render_template_string, send_file
from openai import OpenAI

# ********************* КОНФИГУРАЦИЯ *********************
OPENROUTER_URL = "https://openrouter.ai/api/v1"
PORT           = 5010
MAX_TOKENS     = 1024
TEMPERATURE    = 0.7
ELO_K          = 32
ELO_START      = 1000
RATINGS_FILE   = "ratings.json"
HISTORY_FILE   = "arena_history.json" # Файл для ДЗ

# БЕЗОПАСНОСТЬ: Читаем ключ из переменной окружения OPENROUTER_API_KEY
# Если переменная не задана, попробуйте подставить ключ временно для тестов локально, 
# но НЕ сохраняйте его в Git.
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

REPO_URL = "https://github.com/SofiaKaush/Local-LM-Arena-with-JSON-export"

# Инструменты для генерации изображений
TOOLS = [{
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": "Генерирует изображение по текстовому описанию (prompt)",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Детальное описание изображения на английском языке"}
            },
            "required": ["prompt"]
        }
    }
}]

# ********************* ИНИЦИАЛИЗАЦИЯ *********************
app = Flask(__name__)
http_client = httpx.Client()
client = OpenAI(base_url=OPENROUTER_URL, api_key=API_KEY, http_client=http_client)

def load_ratings():
    if os.path.exists(RATINGS_FILE):
        try:
            with open(RATINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}
    return {}

ratings = load_ratings()

def save_ratings():
    with open(RATINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(ratings, f, ensure_ascii=False, indent=2)

def save_history_entry(entry):
    """Сохраняет данные теста в arena_history.json для ДЗ."""
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except:
            history = []
    
    history.append(entry)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ********************* ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ *********************

def get_available_models():
    models = []
    try:
        resp = httpx.get(f"{OPENROUTER_URL}/models", headers={"Authorization": f"Bearer {API_KEY}"}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            models = [m["id"] for m in data.get("data", [])]
    except: pass
    
    fallback = ["openai/gpt-4o-mini", "google/gemma-2-9b-it:free", "mistralai/mistral-7b-instruct:free"]
    for m in fallback:
        if m not in models: models.append(m)
    return models

def ensure_rating(model_id):
    if model_id not in ratings:
        ratings[model_id] = {"elo": float(ELO_START), "wins": 0, "losses": 0, "ties": 0, "battles": 0}

def _call_model_with_tools(model_id, messages):
    try:
        if not API_KEY:
            return {"text": "Ошибка: API_KEY не задан в переменных окружения.", "image_url": None}
            
        response = client.chat.completions.create(
            model=model_id,
            messages=messages,
            tools=TOOLS,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            extra_headers={"HTTP-Referer": REPO_URL, "X-Title": "Local LM Arena Pro Agent"}
        )
        msg = response.choices[0].message
        image_url = None
        content = msg.content or getattr(msg, 'reasoning_content', "") or ""
        
        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            if tool_call.function.name == "generate_image":
                try:
                    args = json.loads(tool_call.function.arguments)
                    prompt = args.get("prompt", "A creative artwork")
                    image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?nologo=true"
                    if not content: content = f"Генерирую изображение: {prompt}"
                except: pass
        
        if not content and not image_url: content = "[Пустой ответ]"
        return {"text": content, "image_url": image_url}
    except Exception as e:
        return {"text": f"Ошибка {model_id}: {str(e)}", "image_url": None}

def elo_update(winner_id, loser_id, is_tie=False):
    ra, rb = ratings[winner_id]["elo"], ratings[loser_id]["elo"]
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    
    score = 0.5 if is_tie else 1.0
    delta = round(ELO_K * (score - ea), 1)
    
    ratings[winner_id]["elo"] = round(ra + delta, 1)
    ratings[loser_id]["elo"]  = round(rb - delta, 1)
    save_ratings()
    return delta

# ********************* FLASK МАРШРУТЫ *********************

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/models")
def models_route():
    models = get_available_models()
    for m in models: ensure_rating(m)
    return jsonify({"models": models, "ratings": ratings})

@app.route("/discuss", methods=["POST"])
def discuss():
    data = request.get_json()
    question = data.get("question", "").strip()
    available = get_available_models()
    
    pool = ["openai/gpt-4o-mini", "google/gemma-2-9b-it:free"]
    pool = [m for m in pool if m in available]
    if len(pool) < 2:
        others = [m for m in available if m not in pool]
        pool.extend(random.sample(others, min(len(others), 2 - len(pool))))
    
    random.shuffle(pool)
    m1, m2 = pool[0], pool[1]
    
    res1 = _call_model_with_tools(m1, [{"role": "user", "content": question}])
    crit_msg = f"Вопрос: '{question}'. Ответ коллеги: '{res1['text']}'. Проанализируй и дополни."
    res2 = _call_model_with_tools(m2, [{"role": "user", "content": crit_msg}])
    reb_msg = f"Твой ответ: '{res1['text']}'. Критика: '{res2['text']}'. Ответь и подытожь."
    res3 = _call_model_with_tools(m1, [{"role": "user", "content": reb_msg}])

    return jsonify({
        "left": m1, "right": m2, "question": question,
        "history": [
            {"role": "M1", "text": res1['text'], "image_url": res1['image_url'], "label": "Ответ A"},
            {"role": "M2", "text": res2['text'], "image_url": res2['image_url'], "label": "Критика B"},
            {"role": "M1", "text": res3['text'], "image_url": res3['image_url'], "label": "Вывод A"}
        ]
    })

@app.route("/vote", methods=["POST"])
def vote():
    data = request.get_json()
    winner, left, right = data.get("winner"), data.get("left"), data.get("right")
    
    for m in [left, right]:
        ensure_rating(m)
        ratings[m]["battles"] += 1

    is_tie = (winner == "tie")
    delta = elo_update(left if winner != "right" else right, right if winner != "right" else left, is_tie)

    if winner == "left": ratings[left]["wins"] += 1
    elif winner == "right": ratings[right]["wins"] += 1
    else: ratings[left]["ties"] += 1; ratings[right]["ties"] += 1
    
    # Сохраняем в историю для ДЗ
    save_history_entry({
        "question": data.get("question"),
        "models": {"left": left, "right": right},
        "answers": data.get("history"),
        "outcome": winner,
        "elo_delta": delta
    })

    save_ratings()
    return jsonify({"ratings": ratings})

@app.route("/export")
def export():
    return send_file(HISTORY_FILE, as_attachment=True) if os.path.exists(HISTORY_FILE) else ("Файл пуст", 404)

# ********************* HTML ИНТЕРФЕЙС *********************
HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>LM Arena PRO Agent</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root { --bg: #0f172a; --card: #1e293b; --text: #f1f5f9; --accent: #3b82f6; --border: #334155; }
  body { font-family: 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
  .container { max-width: 1100px; margin: 0 auto; }
  .panel { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 24px; margin-bottom: 20px; }
  textarea { width: 100%; background: #0f172a; color: white; border: 1px solid var(--border); border-radius: 12px; padding: 15px; height: 80px; resize: none; }
  .actions { display: flex; gap: 10px; margin-top: 15px; }
  .btn { padding: 12px 24px; border: none; border-radius: 10px; cursor: pointer; font-weight: 600; }
  .btn-primary { background: var(--accent); color: white; }
  .btn-outline { background: transparent; border: 1px solid var(--border); color: var(--text); }
  .chat-container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
  .bubble { background: #334155; padding: 15px; border-radius: 12px; margin-bottom: 20px; position: relative; }
  .bubble-label { position: absolute; top: -10px; left: 10px; background: var(--accent); font-size: 10px; padding: 2px 8px; border-radius: 4px; }
  .m1-bubble { border-left: 4px solid #10b981; }
  .m2-bubble { border-left: 4px solid #f59e0b; }
  .gen-image { max-width: 100%; border-radius: 8px; margin-top: 10px; }
  .vote-bar { display: flex; justify-content: center; gap: 15px; margin-top: 20px; padding: 20px; background: rgba(255,255,255,0.05); border-radius: 12px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
</style>
</head>
<body>
<div class="container">
  <div class="panel">
    <h1>LM Arena: PRO Agent Discussion</h1>
    <textarea id="q" placeholder="Ваш вопрос..."></textarea>
    <div class="actions">
      <button id="mainBtn" class="btn btn-primary" onclick="startDiscussion()">Начать дискуссию</button>
      <button class="btn btn-outline" onclick="location.href='/export'">Экспорт JSON (ДЗ)</button>
      <span id="status" style="margin-left:auto; align-self:center; color:#94a3b8"></span>
    </div>
  </div>

  <div id="arena" style="display:none">
    <div class="chat-container">
      <div id="colL"><h3>Модель A</h3><div class="bubbles"></div></div>
      <div id="colR"><h3>Модель B</h3><div class="bubbles"></div></div>
    </div>
    <div class="vote-bar" id="voteBtns">
      <button class="btn btn-outline" onclick="vote('left')">A убедительнее</button>
      <button class="btn btn-outline" onclick="vote('tie')">Ничья</button>
      <button class="btn btn-outline" onclick="vote('right')">B убедительнее</button>
    </div>
  </div>

  <div class="panel">
    <h3>Рейтинг моделей (Elo)</h3>
    <table>
      <thead><tr><th>Модель</th><th>Elo</th><th>Битвы</th><th>Win Rate</th></tr></thead>
      <tbody id="statsBody"></tbody>
    </table>
  </div>
</div>

<script>
let curBattle = null;

async function startDiscussion() {
    const q = document.getElementById('q').value;
    if(!q) return;
    document.getElementById('mainBtn').disabled = true;
    document.getElementById('status').innerText = "Модели общаются...";
    document.getElementById('arena').style.display = 'none';
    
    try {
        const r = await fetch('/discuss', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({question: q})
        });
        curBattle = await r.json();
        
        const colL = document.querySelector('#colL .bubbles');
        const colR = document.querySelector('#colR .bubbles');
        colL.innerHTML = ""; colR.innerHTML = "";

        curBattle.history.forEach(item => {
            const div = document.createElement('div');
            div.className = `bubble ${item.role === 'M1' ? 'm1-bubble' : 'm2-bubble'}`;
            let html = item.label ? `<span class="bubble-label">${item.label}</span>` : "";
            html += marked.parse(item.text);
            if(item.image_url) html += `<img src="${item.image_url}" class="gen-image">`;
            div.innerHTML = html;
            (item.role === 'M1' ? colL : colR).appendChild(div);
        });

        document.getElementById('status').innerText = "Готово. Голосуйте!";
        document.getElementById('arena').style.display = 'block';
        document.getElementById('voteBtns').style.display = 'flex';
    } catch(e) {
        document.getElementById('status').innerText = "Ошибка: " + e.message;
    } finally {
        document.getElementById('mainBtn').disabled = false;
    }
}

async function vote(winner) {
    const r = await fetch('/vote', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({...curBattle, winner})
    });
    const d = await r.json();
    updateStats(d.ratings);
    document.getElementById('voteBtns').style.display = 'none';
    document.getElementById('status').innerText = "Голос сохранен в JSON!";
}

function updateStats(ratings) {
    const body = document.getElementById('statsBody');
    body.innerHTML = "";
    Object.entries(ratings).sort((a,b)=>b[1].elo - a[1].elo).forEach(([id, s]) => {
        const wr = s.battles > 0 ? (s.wins / s.battles * 100).toFixed(1) : 0;
        body.innerHTML += `<tr><td>${id.split('/').pop()}</td><td><b>${s.elo}</b></td><td>${s.battles}</td><td>${wr}%</td></tr>`;
    });
}

fetch('/models').then(r=>r.json()).then(d => updateStats(d.ratings));
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(debug=True, port=PORT)