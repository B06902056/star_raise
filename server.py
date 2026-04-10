"""
server.py — Star Raise FastAPI Backend  (v5: Auto-Spawn Economy)

Endpoints
---------
GET /                → health check
GET /api/game_state  → full game snapshot (minerals, income breakdown, units, buildings)
GET /api/units       → unit list only (lightweight polling)
GET /api/buildings   → building status (HQs + slot buildings)

Phase 2 notes on /api/game_state
----------------------------------
income_base   : flat 10 minerals / 5 s, always present
income_bonus  : Σ b.income_bonus for every alive slot building
                  barracks → +5 / cycle  (5% of cost 100)
                  refinery → +10 / cycle (5% of cost 200)
income_rate   : income_base + income_bonus  (total per 5 s cycle)

buildings[]   : now includes slot buildings as well as HQs
  is_hq           : true = victory-condition target (not auto-spawning)
  lane            : "top" | "bottom" | "none"
  income_bonus    : per-cycle mineral contribution (0 for HQs)
  spawn_progress  : 0.0–1.0, fraction toward next unit spawn (0 for HQs)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.shared import read as read_state

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Star Raise Game API",
    description="Real-time game state API — Phase 2: Auto-Spawn & Economy-Building Linkage",
    version="0.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/", tags=["health"])
def root() -> dict:
    return {"status": "ok", "service": "star_raise_api", "version": "0.5.0"}


@app.get("/api/game_state", tags=["game"])
def game_state() -> JSONResponse:
    """
    Full game snapshot.

    Key fields (Phase 2)
    --------------------
    minerals       : player's current mineral balance
    income_base    : flat base income (always 10)
    income_bonus   : bonus from placed buildings (barracks +5, refinery +10 each)
    income_rate    : income_base + income_bonus (total per 5 s cycle)
    buildings      : list of all buildings with lane, income_bonus, spawn_progress
    slot_buildings : total count of placed slot buildings
    """
    return JSONResponse(content=read_state())


@app.get("/api/units", tags=["game"])
def units() -> JSONResponse:
    """Unit list — lightweight for high-frequency polling."""
    state = read_state()
    return JSONResponse(content={
        "frame":      state["frame"],
        "unit_count": state["unit_count"],
        "units":      state["units"],
    })


@app.get("/api/buildings", tags=["game"])
def buildings() -> JSONResponse:
    """
    Building HP + slot status.
    Includes HQs (is_hq=true) and all slot buildings (is_hq=false).
    """
    state = read_state()
    return JSONResponse(content={
        "frame":          state["frame"],
        "game_result":    state["game_result"],
        "slot_buildings": state["slot_buildings"],
        "income_rate":    state["income_rate"],
        "buildings":      state["buildings"],
    })


# ── Direct run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
