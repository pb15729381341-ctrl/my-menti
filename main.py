import json
import os
import asyncio
import time
import re
from typing import List, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

# Data persistence
QUESTIONS_FILE = "questions.json"

def load_questions():
    if not os.path.exists(QUESTIONS_FILE):
        with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_questions(questions):
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=4)

class Question(BaseModel):
    id: Optional[int] = None
    text: str
    options: Dict[str, str]
    answer: str

class ImportRequest(BaseModel):
    text: str
    replace: Optional[bool] = False

class BulkDeleteRequest(BaseModel):
    ids: List[int]

# Game State
class Player:
    def __init__(self, websocket: WebSocket, nickname: str):
        self.websocket = websocket
        self.nickname = nickname
        self.score = 0
        self.last_answer_time = 0
        self.answered_current = False

class GameState:
    def __init__(self):
        self.players: Dict[str, Player] = {} # websocket_id -> Player
        self.host_ws: Optional[WebSocket] = None
        self.current_question_idx = -1
        self.status = "waiting" # waiting, showing_question, showing_result, finished
        self.questions = load_questions()
        self.question_start_time = 0
        self.answers_received = 0

game = GameState()

# WebSocket Manager
class ConnectionManager:
    async def connect_player(self, websocket: WebSocket, nickname: str):
        await websocket.accept()
        player_id = str(id(websocket))
        game.players[player_id] = Player(websocket, nickname)
        await self.broadcast_status()
        return player_id

    async def connect_host(self, websocket: WebSocket):
        await websocket.accept()
        game.host_ws = websocket
        await self.broadcast_status()

    def disconnect_player(self, player_id: str):
        if player_id in game.players:
            del game.players[player_id]
            return True
        return False

    def disconnect_host(self):
        game.host_ws = None

    async def broadcast(self, message: dict):
        # Broadcast to all players
        for p_id, player in list(game.players.items()):
            try:
                await player.websocket.send_json(message)
            except:
                del game.players[p_id]
        
        # Also send to host
        if game.host_ws:
            try:
                await game.host_ws.send_json(message)
            except:
                game.host_ws = None

    async def broadcast_status(self):
        status_msg = {
            "type": "status_update",
            "online_count": len(game.players),
            "game_status": game.status,
            "current_question_idx": game.current_question_idx,
            "total_questions": len(game.questions),
            "answers_received": game.answers_received
        }
        await self.broadcast(status_msg)

manager = ConnectionManager()

# Routes
@app.get("/api/questions")
def get_questions():
    return load_questions()

@app.post("/api/questions")
def add_question(q: Question):
    questions = load_questions()
    q.id = int(time.time())
    questions.append(q.dict())
    save_questions(questions)
    game.questions = questions # Update in-memory
    return q

@app.delete("/api/questions/{q_id}")
def delete_question(q_id: int):
    questions = load_questions()
    questions = [q for q in questions if q["id"] != q_id]
    save_questions(questions)
    game.questions = questions # Update in-memory
    return {"status": "success"}

@app.post("/api/questions/delete_bulk")
def delete_questions_bulk(req: BulkDeleteRequest):
    questions = load_questions()
    questions = [q for q in questions if q["id"] not in req.ids]
    save_questions(questions)
    game.questions = questions
    return {"status": "success", "deleted_count": len(req.ids)}

@app.delete("/api/questions_all")
def clear_all_questions():
    save_questions([])
    game.questions = []
    return {"status": "success"}

@app.post("/api/import_text")
def import_text(req: ImportRequest):
    text = req.text
    # 1. 预处理：统一全角标点，移除干扰字符
    text = text.replace("：", ":").replace("．", ".").replace("。", ".")
    
    # 2. 强大的正则表达式
    # 匹配模式：题目 + 内容 + A...B...C...D... + 答案 + 选项
    # 允许内容中有空格或换行，支持紧凑格式
    pattern = r"题目[:\s]*(.*?)\s*A[:.\s]+(.*?)\s*B[:.\s]+(.*?)\s*C[:.\s]+(.*?)\s*D[:.\s]+(.*?)\s*答案[:\s]*([A-D])"
    
    matches = re.finditer(pattern, text, re.DOTALL | re.IGNORECASE)
    new_questions = []
    
    for match in matches:
        try:
            q_text, opt_a, opt_b, opt_c, opt_d, answer = match.groups()
            
            # 基础校验
            if not q_text.strip():
                continue
                
            new_questions.append({
                "id": int(time.time() * 1000) + len(new_questions),
                "text": q_text.strip(),
                "options": {
                    "A": opt_a.strip(),
                    "B": opt_b.strip(),
                    "C": opt_c.strip(),
                    "D": opt_d.strip()
                },
                "answer": answer.strip().upper()
            })
        except Exception as e:
            print(f"解析单条题目失败: {e}")
            continue
            
    if not new_questions:
        raise HTTPException(status_code=400, detail="未识别到任何题目，请检查格式是否包含 '题目'、'A/B/C/D' 及 '答案'")
        
    questions = load_questions() if not req.replace else []
    questions.extend(new_questions)
    save_questions(questions)
    game.questions = questions # 更新内存
    
    return {"status": "success", "count": len(new_questions)}

# WebSocket Endpoints
@app.websocket("/ws/player/{nickname}")
async def websocket_player(websocket: WebSocket, nickname: str):
    player_id = await manager.connect_player(websocket, nickname)
    try:
        while True:
            data = await websocket.receive_json()
            if data["type"] == "answer" and game.status == "showing_question":
                player = game.players.get(player_id)
                if player and not player.answered_current:
                    player.answered_current = True
                    game.answers_received += 1
                    
                    # Scoring logic
                    current_q = game.questions[game.current_question_idx]
                    if data["answer"] == current_q["answer"]:
                        response_time = time.time() - game.question_start_time
                        # Base 1000 points, minus points for time (max 15s)
                        # Formula: max(0, 1000 * (1 - response_time / 15)) + 500 (accuracy)
                        time_bonus = max(0, int(1000 * (1 - response_time / 15)))
                        player.score += (500 + time_bonus)
                        player.last_answer_time = response_time
                    
                    await manager.broadcast_status()
                    await websocket.send_json({"type": "answer_received", "correct": data["answer"] == current_q["answer"]})

    except WebSocketDisconnect:
        manager.disconnect_player(player_id)
        await manager.broadcast_status()

@app.websocket("/ws/host")
async def websocket_host(websocket: WebSocket):
    await manager.connect_host(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data["type"] == "start_game":
                game.current_question_idx = 0
                await start_question()
            elif data["type"] == "next_question":
                game.current_question_idx += 1
                if game.current_question_idx < len(game.questions):
                    await start_question()
                else:
                    await finish_game()
            elif data["type"] == "end_game":
                await finish_game()

    except WebSocketDisconnect:
        manager.disconnect_host()

async def start_question():
    game.status = "showing_question"
    game.answers_received = 0
    game.question_start_time = time.time()
    for p in game.players.values():
        p.answered_current = False
    
    q = game.questions[game.current_question_idx]
    await manager.broadcast({
        "type": "new_question",
        "question": {
            "text": q["text"],
            "options": q["options"]
        },
        "index": game.current_question_idx,
        "total": len(game.questions),
        "timeout": 15
    })
    
    # Start a background task for the countdown
    asyncio.create_task(countdown(15, game.current_question_idx))

async def countdown(seconds: int, q_idx: int):
    await asyncio.sleep(seconds)
    # Only show result if we are still on the same question and not finished
    if game.status == "showing_question" and game.current_question_idx == q_idx:
        await show_result()

async def show_result():
    game.status = "showing_result"
    current_q = game.questions[game.current_question_idx]
    
    # Find fastest correct player for this round
    fastest_player = None
    min_time = 999
    for p in game.players.values():
        if p.answered_current and p.last_answer_time < min_time:
            # Note: this is a bit simplified, ideally check if answer was correct
            # But score is already updated. Let's just use the score increment or similar.
            pass
    
    # Sort players for this round's "fastest"
    # For simplicity, we just send the answer and current leaderboard
    leaderboard = sorted(
        [{"nickname": p.nickname, "score": p.score} for p in game.players.values()],
        key=lambda x: x["score"],
        reverse=True
    )
    
    await manager.broadcast({
        "type": "question_result",
        "answer": current_q["answer"],
        "answer_text": current_q["options"][current_q["answer"]],
        "leaderboard": leaderboard[:5] # Top 5
    })

async def finish_game():
    game.status = "finished"
    leaderboard = sorted(
        [{"nickname": p.nickname, "score": p.score} for p in game.players.values()],
        key=lambda x: x["score"],
        reverse=True
    )
    await manager.broadcast({
        "type": "game_finished",
        "leaderboard": leaderboard[:3] # Top 3
    })

# Serve static files
@app.get("/")
async def get_index():
    return FileResponse("index.html")

@app.get("/admin")
async def get_admin():
    return FileResponse("admin.html")

@app.get("/host")
async def get_host():
    return FileResponse("host.html")

# app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    # 从环境变量读取端口，默认为 8000
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
