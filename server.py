"""
server.py — Star Raise FastAPI Backend  (v4)

端點
----
GET /              → 健康確認
GET /api/game_state → 當前遊戲狀態快照（礦石、單位數、建築 HP）
GET /api/units     → 所有單位列表（含 HP / 狀態）
GET /api/buildings → 所有建築狀態

部署
----
本地 : uvicorn server:app --reload --port 8000
Zeabur/Render: Procfile → web: uvicorn server:app --host 0.0.0.0 --port $PORT

遊戲執行緒安全
--------------
遊戲主迴圈（pygame, main thread）每幀呼叫 src.shared.write()，
本模組的所有 handler 透過 src.shared.read() 取得快照，
不直接存取任何 pygame 物件，完全無競態風險。
"""

from __future__ import annotations

import os
import sys

# 確保 src/ 在路徑中（uvicorn 直接啟動時工作目錄可能不同）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.shared import read as read_state

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Star Raise Game API",
    description="即時遊戲狀態 API，供前端 Dashboard 或 AI 合作夥伴呼叫",
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 開發階段開放，部署時限縮
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── 端點 ─────────────────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def root() -> dict:
    """健康確認端點，Zeabur 健康檢查用。"""
    return {"status": "ok", "service": "star_raise_api", "version": "0.4.0"}


@app.get("/api/game_state", tags=["game"])
def game_state() -> JSONResponse:
    """
    回傳完整遊戲狀態快照。

    欄位說明
    --------
    frame        : 當前遊戲幀數
    game_result  : null | "VICTORY" | "DEFEAT"
    minerals     : 玩家當前礦石數
    income_rate  : 每收入週期獲得的礦石數
    unit_count   : 場上存活單位總數
    units        : 所有單位的詳細資訊列表
    buildings    : 所有建築的詳細資訊列表
    """
    return JSONResponse(content=read_state())


@app.get("/api/units", tags=["game"])
def units() -> JSONResponse:
    """只回傳單位列表（輕量版，適合高頻輪詢）。"""
    state = read_state()
    return JSONResponse(content={
        "frame":      state["frame"],
        "unit_count": state["unit_count"],
        "units":      state["units"],
    })


@app.get("/api/buildings", tags=["game"])
def buildings() -> JSONResponse:
    """回傳建築 HP 狀態（用於前端基地血條）。"""
    state = read_state()
    return JSONResponse(content={
        "frame":       state["frame"],
        "game_result": state["game_result"],
        "buildings":   state["buildings"],
    })


# ── 本地直接執行 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
