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
import math
import random
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.sprite import Building   # avoid circular import at runtime


# ── BuildState Enum ───────────────────────────────────────────────────────────
class BuildState(Enum):
    """
    Tracks what the player's cursor/build system is currently doing.

    NONE          : default — camera drag and normal game interaction are active.
    CONSTRUCTING  : player has picked up a building card and is dragging a ghost
                    sprite; camera scrolling is suppressed until drop/cancel.
    DEMOLISHING   : demolish mode is toggled ON; left-clicking an existing slot
                    building triggers Building.demolish() and refunds 60 % cost.
    """
    NONE         = auto()
    CONSTRUCTING = auto()
    DEMOLISHING  = auto()
    NUKING       = auto()   # Phase 4: player is aiming the one-time nuke

# ── GameState Enum ────────────────────────────────────────────────────────────
class GameState(Enum):
    """
    Top-level game lifecycle state.

    PLAYING : Normal gameplay — units spawn, buildings fire, HQs take damage.
    VICTORY : Enemy HQ reached 0 HP.  Overlay shown; all logic paused.
    DEFEAT  : Player HQ reached 0 HP.  Overlay shown; all logic paused.

    Transitions are set by:
      (a) Building.on_hq_death callback (fast, event-driven), or
      (b) GameLoop._check_victory() polling each frame (belt-and-suspenders).
    """
    PLAYING = auto()
    VICTORY = auto()
    DEFEAT  = auto()


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
        # One-time tactical nuke weapon (resets to True on scene reset)
        self.nuke_available:  bool = True

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

    def refund(self, amount: int) -> None:
        """
        Credit minerals back to the player (used by Building.demolish).

        Refund formula: caller passes int(cost * 0.6) — i.e. 60 % of the
        building's original cost.  This method simply adds the amount with
        no cap so the player cannot 'lose' minerals on a demolish.

        Examples
        --------
        barracks (cost 100)  → refund(60)   → minerals += 60
        refinery (cost 200)  → refund(120)  → minerals += 120
        """
        self.minerals += amount
        print(f"[Economy] Refund +{amount}  →  {self.minerals} minerals")

    # ── Nuke ──────────────────────────────────────────────────────────────────
    def launch_nuke(
        self,
        target_pos,          # tuple[float, float]  — world-space detonation point
        units,               # list[Unit]
        buildings,           # list[Building]
        vfx_callback=None,   # Optional[Callable[[tuple[float,float]], None]]
        radius: float = 300.0,
    ) -> bool:
        """
        Fire the one-time tactical nuke at *target_pos*.

        Returns True if the nuke was launched; False if already expended.

        AoE damage model
        ----------------
        • Every Unit within *radius* pixels:
              take_damage(9999)  →  instant kill regardless of HP/armour.

        • Every Building within *radius* pixels:
              take_damage( int(b.max_hp × 0.5) )  →  exactly 50 % of max HP.
              Slot buildings (max_hp ≤ 500) die if already below 50 % HP.
              HQs (max_hp = 800) survive a single nuke hit (take 400 damage),
              but a second nuke (if ever added) would finish them off.

        • VFX: 12 explosion sprites scattered randomly inside the blast circle.

        Side-effect: sets nuke_available = False (one-shot weapon).
        """
        if not self.nuke_available:
            return False
        self.nuke_available = False

        tx, ty = float(target_pos[0]), float(target_pos[1])

        # ── Damage units (instant kill) ───────────────────────────────────────
        for u in units:
            if u.is_dead:
                continue
            if math.hypot(u.pos[0] - tx, u.pos[1] - ty) <= radius:
                u.take_damage(9999, vfx_callback)

        # ── Damage buildings (50 % max-HP) ────────────────────────────────────
        for b in buildings:
            if b.is_dead:
                continue
            if math.hypot(b.pos[0] - tx, b.pos[1] - ty) <= radius:
                dmg = int(b.max_hp * 0.5)
                b.take_damage(dmg, vfx_callback)

        # ── Scatter VFX explosions across the blast zone ──────────────────────
        if vfx_callback:
            for _ in range(12):
                ox = random.uniform(-radius * 0.85, radius * 0.85)
                oy = random.uniform(-radius * 0.85, radius * 0.85)
                if math.hypot(ox, oy) <= radius:
                    vfx_callback((tx + ox, ty + oy))

        print(
            f"[Nuke] Detonated at ({tx:.0f}, {ty:.0f})  "
            f"radius={radius}  minerals={self.minerals}"
        )
        return True

    def __repr__(self) -> str:
        alive = sum(1 for b in self._slot_buildings if not b.is_dead)
        return (
            f"ResourceManager(minerals={self.minerals}, "
            f"income={self.income_per_cycle}/cycle "
            f"[base={BASE_INCOME} + bonus={self.income_bonus}], "
            f"slot_buildings={alive}/{len(self._slot_buildings)})"
        )
