"""
shared.py — Star Raise Game  (v4: API Integration)
執行緒安全的遊戲狀態快照，供 FastAPI 讀取。

GameLoop（主執行緒）每幀呼叫 write()，
uvicorn（背景執行緒）的 API handler 呼叫 read()。
CPython GIL 已提供基本安全，threading.Lock 確保跨平台一致。
"""

import threading
from typing import Any

_lock: threading.Lock = threading.Lock()

# 初始快照（欄位必須與 GameLoop 每幀寫入的 key 完全對應）
_state: dict[str, Any] = {
    "frame":        0,
    "game_result":  None,          # None | "VICTORY" | "DEFEAT"

    # 玩家資源
    "minerals":     0,
    "income_rate":  0,

    # 單位
    "unit_count":   0,
    "units": [],                   # [{kind, team, hp, max_hp, state}]

    # 建築
    "buildings": [],               # [{kind, team, hp, max_hp, is_dead}]
}


def write(data: dict[str, Any]) -> None:
    """GameLoop 每幀呼叫，覆寫對應欄位。"""
    with _lock:
        _state.update(data)


def read() -> dict[str, Any]:
    """API handler 呼叫，回傳快照深拷貝。"""
    with _lock:
        return dict(_state)
