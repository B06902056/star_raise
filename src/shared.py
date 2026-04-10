"""
shared.py — Star Raise  (v5: Auto-Spawn Economy)
Thread-safe game-state snapshot for FastAPI.

GameLoop (main thread) writes every frame via write().
uvicorn (daemon thread) reads via read() — no pygame objects involved.
"""

import threading
from typing import Any

_lock:  threading.Lock = threading.Lock()

# Initial snapshot — keys must match what GameLoop._push_state() writes
_state: dict[str, Any] = {
    "frame":        0,
    "game_result":  None,           # None | "VICTORY" | "DEFEAT"

    # Economy (Phase 2: income is now split into base + building bonus)
    "minerals":      0,
    "income_base":   10,            # always BASE_INCOME = 10
    "income_bonus":  0,             # Σ b.income_bonus from alive slot buildings
    "income_rate":   10,            # income_base + income_bonus

    # Units
    "unit_count":    0,
    "units":         [],            # [{kind, team, hp, max_hp, state, pos}]

    # Buildings (HQs + slot buildings)
    "buildings":     [],            # [{kind, team, hp, max_hp, is_dead,
                                    #   is_hq, lane, income_bonus, spawn_progress}]

    # Slot summary
    "slot_buildings": 0,            # count of placed slot buildings
}


def write(data: dict[str, Any]) -> None:
    """GameLoop calls this every frame to update the snapshot."""
    with _lock:
        _state.update(data)


def read() -> dict[str, Any]:
    """API handler calls this; returns a shallow copy of the current snapshot."""
    with _lock:
        return dict(_state)
