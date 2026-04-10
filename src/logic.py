"""
logic.py — Star Raise  (v5: Auto-Spawn Economy)

Phase 2 changes
---------------
- ProductionQueue  : REMOVED (manual queuing deprecated)
- AIController     : REMOVED (replaced by Building auto-spawn timers)
- ResourceManager  : refactored — income now driven by placed buildings

Income formula (per 5 s cycle)
--------------------------------
  income_per_cycle = BASE_INCOME (10)
                   + Σ b.income_bonus  for every alive slot-building b

  income_bonus per building = floor(cost × 5%)

  Example:  2 × barracks (cost 100, bonus 5) + 1 × refinery (cost 200, bonus 10)
            → 10 + 5 + 5 + 10 = 30 minerals / cycle

Building auto-spawn table (BUILDING_SPECS)
------------------------------------------
  Each kind defines:
    unit_type          : which unit it produces
    spawn_rate_frames  : frames between consecutive spawns
    cost               : purchase cost (future use) + basis for income_bonus
    income_bonus       : flat bonus added to income_per_cycle while alive
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sprite import Building   # avoid circular import at runtime

# ── Income constants ──────────────────────────────────────────────────────────
INCOME_CYCLE_FRAMES: int = 300    # 5 s @ 60 fps
BASE_INCOME:         int = 10     # flat base income, always present
STARTING_MINERALS:   int = 150

# ── Building spec table (single source of truth) ──────────────────────────────
BUILDING_SPECS: dict[str, dict] = {
    "barracks": {
        "unit_type":         "marine",
        "spawn_rate_frames": 480,    # 8 s @ 60 fps
        "cost":              100,
        "income_bonus":      5,      # floor(100 × 5%) per income cycle
    },
    "refinery": {
        "unit_type":         "tank",
        "spawn_rate_frames": 720,    # 12 s @ 60 fps
        "cost":              200,
        "income_bonus":      10,     # floor(200 × 5%) per income cycle
    },
}


# ── ResourceManager ───────────────────────────────────────────────────────────
class ResourceManager:
    """
    Manages player minerals and dynamic passive income.

    Income is calculated each cycle as:
        BASE_INCOME + Σ(b.income_bonus for b in alive slot-buildings)

    Buildings are registered via register_building() when placed in a slot.
    Income automatically stops counting a building once b.is_dead == True.

    Typical usage
    -------------
    rm = ResourceManager()
    rm.register_building(barracks_sprite)   # when player places a building
    cycle_fired = rm.update()               # every frame; True = cycle fired
    rm.spend(50)                            # future upgrades / purchases
    """

    def __init__(self, starting: int = STARTING_MINERALS) -> None:
        self.minerals:        int  = starting
        self._cycle_timer:    int  = 0
        # List of Building sprites placed in player slots
        self._slot_buildings: list = []

    # ── Building registration ──────────────────────────────────────────────────
    def register_building(self, building: Building) -> None:
        """Register a slot building so its income_bonus is counted each cycle."""
        if building not in self._slot_buildings:
            self._slot_buildings.append(building)
            print(
                f"[Economy] Registered {building.kind}  "
                f"income_bonus=+{building.income_bonus}  "
                f"→ new income={self.income_per_cycle}/cycle"
            )

    def unregister_building(self, building: Building) -> None:
        """Remove a slot building (e.g. if the player demolishes it)."""
        self._slot_buildings = [b for b in self._slot_buildings if b is not building]

    # ── Income properties ──────────────────────────────────────────────────────
    @property
    def income_bonus(self) -> int:
        """
        Total bonus income from all alive registered slot buildings.
        Dead buildings contribute 0 (is_dead == True).
        """
        return sum(b.income_bonus for b in self._slot_buildings if not b.is_dead)

    @property
    def income_per_cycle(self) -> int:
        """Total minerals earned per 5 s cycle = BASE_INCOME + income_bonus."""
        return BASE_INCOME + self.income_bonus

    @property
    def cycle_progress(self) -> float:
        """Progress toward the next income cycle, 0.0 – 1.0."""
        return self._cycle_timer / INCOME_CYCLE_FRAMES

    @property
    def frames_to_next_cycle(self) -> int:
        return INCOME_CYCLE_FRAMES - self._cycle_timer

    # ── Per-frame update ───────────────────────────────────────────────────────
    def update(self) -> bool:
        """
        Advance income timer by one frame.
        Returns True on the exact frame the cycle fires (for UI flash effect).
        """
        self._cycle_timer += 1
        if self._cycle_timer >= INCOME_CYCLE_FRAMES:
            self._cycle_timer = 0
            earned = self.income_per_cycle
            self.minerals += earned
            print(
                f"[Economy] +{earned} minerals  →  {self.minerals} total  "
                f"(base={BASE_INCOME}  bonus={self.income_bonus}  "
                f"buildings={len([b for b in self._slot_buildings if not b.is_dead])})"
            )
            return True
        return False

    # ── Spending ───────────────────────────────────────────────────────────────
    def spend(self, amount: int) -> bool:
        """Deduct minerals. Returns False without deducting if insufficient."""
        if self.minerals >= amount:
            self.minerals -= amount
            return True
        return False

    def __repr__(self) -> str:
        alive = sum(1 for b in self._slot_buildings if not b.is_dead)
        return (
            f"ResourceManager(minerals={self.minerals}, "
            f"income={self.income_per_cycle}/cycle "
            f"[base={BASE_INCOME} + bonus={self.income_bonus}], "
            f"slot_buildings={alive}/{len(self._slot_buildings)})"
        )
