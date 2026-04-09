"""
sprite.py — Star Raise Game  (v3: Economy & Spawning)
定義 Sprite 基底類別、Building（含生產介面）、Unit（含戰鬥 FSM）、VFXSprite。

Unit 狀態機
-----------
  march  ──scan_hit──▶  combat  ──enemy_dead──▶  march
                          │
                       hp <= 0
                          ▼
                         dead

Building 角色
-------------
  "barracks"  → produce(unit_type) 委派給 ProductionQueue
  "refinery"  → 建立時通知 ResourceManager.register_refinery()
"""

from __future__ import annotations
import math
import pygame
from typing import Optional, Callable, TYPE_CHECKING
from src.asset_manager import AssetManager

if TYPE_CHECKING:
    from src.logic import ResourceManager, ProductionQueue

# VFX 回調型別: (pos: tuple[float, float]) -> None
VFXCallback = Callable[[tuple[float, float]], None]


# ── 單位數值規格表 ─────────────────────────────────────────────────────────────
UNIT_STATS: dict[str, dict] = {
    "marine": {
        "scale":       (32, 32),
        "hp":          100,
        "speed":       1.8,
        "atk_dmg":     15,
        "atk_cd":      60,      # frames (60fps → 1 秒 1 擊)
        "scan_range":  150,
        "col_radius":  16,
    },
    "tank": {
        "scale":       (48, 48),
        "hp":          250,
        "speed":       1.1,
        "atk_dmg":     40,
        "atk_cd":      90,      # 1.5 秒 1 擊
        "scan_range":  180,
        "col_radius":  24,
    },
}


# ── 基底 Sprite ───────────────────────────────────────────────────────────────
class GameSprite:
    """
    所有遊戲物件的基底類別。

    Attributes
    ----------
    pos              : 世界座標 [x, y]，中心點
    angle            : 面向角度（度），0 = 朝右，逆時針為正
    surface          : 當前 pygame.Surface（已套用旋轉）
    collision_radius : 圓形碰撞半徑（子類別覆寫）
    """

    collision_radius: int = 16

    def __init__(
        self,
        asset_key: str,
        manager: AssetManager,
        pos: tuple[float, float] = (0.0, 0.0),
        scale: Optional[tuple[int, int]] = None,
    ) -> None:
        self.asset_key     = asset_key
        self.manager       = manager
        self.pos           = list(pos)       # [x, y]
        self.angle         = 0.0
        self._base_surface = manager.get(asset_key, scale=scale)
        self.surface       = self._base_surface

    # ── 旋轉 ──────────────────────────────────────────────────────────────────
    def rotate_to(self, target: tuple[float, float]) -> None:
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        self.angle = math.degrees(math.atan2(-dy, dx))
        self._apply_rotation()

    def rotate_by(self, delta_deg: float) -> None:
        self.angle = (self.angle + delta_deg) % 360
        self._apply_rotation()

    def _apply_rotation(self) -> None:
        self.surface = pygame.transform.rotate(self._base_surface, self.angle)

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        rect = self.surface.get_rect(
            center=(
                int(self.pos[0]) - camera_offset[0],
                int(self.pos[1]) - camera_offset[1],
            )
        )
        screen.blit(self.surface, rect)

    def draw_debug(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        """繪製碰撞圓 + 掃描範圍圓（開發用）。"""
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        # 碰撞圓
        pygame.draw.circle(screen, (0, 255, 0), (cx, cy), self.collision_radius, 1)
        # 中心點
        pygame.draw.circle(screen, (255, 0, 0), (cx, cy), 3)

    @property
    def rect(self) -> pygame.Rect:
        return self.surface.get_rect(center=(int(self.pos[0]), int(self.pos[1])))

    # ── 距離工具 ──────────────────────────────────────────────────────────────
    def dist_to(self, other: "GameSprite") -> float:
        return math.hypot(
            self.pos[0] - other.pos[0],
            self.pos[1] - other.pos[1],
        )


# ── 建築 ─────────────────────────────────────────────────────────────────────
class Building(GameSprite):
    """
    靜態建築物件（不移動、可被攻擊）。

    Parameters
    ----------
    kind  : "barracks" | "refinery"
    hp    : 血量
    team  : 0 = 玩家, 1 = 敵方
    """

    collision_radius = 48

    NAMES = {"barracks": "兵營", "refinery": "採礦場"}

    # 不同建築種類的出兵點偏移（相對建築中心）
    SPAWN_OFFSET: dict[str, tuple[int, int]] = {
        "barracks": (80, 0),    # 兵營右側生成
        "refinery": (80, 0),
    }

    def __init__(
        self,
        kind: str,
        manager: AssetManager,
        pos: tuple[float, float],
        hp: int = 500,
        team: int = 0,
    ) -> None:
        super().__init__(kind, manager, pos, scale=(96, 96))
        self.kind      = kind
        self.hp        = hp
        self.max_hp    = hp
        self.team      = team
        self.is_dead   = False

        # 生產佇列（由 main.py 外部注入，Barracks 專用）
        self.queue: Optional[ProductionQueue] = None

        # 被動收入角色（Refinery 設 True，由 main.py 搭配 ResourceManager 使用）
        self.gives_income: bool = (kind == "refinery")

    # ── 出兵點屬性 ────────────────────────────────────────────────────────────
    @property
    def spawn_point(self) -> tuple[float, float]:
        """
        單位生產完成後的出現座標。
        team=0（玩家）右偏，team=1（敵方）左偏。
        """
        ox, oy = self.SPAWN_OFFSET.get(self.kind, (80, 0))
        if self.team == 1:
            ox = -ox   # 敵方建築向左生成
        return (self.pos[0] + ox, self.pos[1] + oy)

    # ── 生產介面 ──────────────────────────────────────────────────────────────
    def produce(self, unit_type: str, resource_mgr: ResourceManager) -> bool:
        """
        委派生產任務給已注入的 ProductionQueue。
        回傳 True 表示成功入隊；若無佇列或資源不足則 False。
        """
        if self.is_dead:
            print(f"[Building] ⚠️  建築已摧毀，無法生產")
            return False
        if self.queue is None:
            print(f"[Building] ⚠️  {self.kind} 沒有生產佇列")
            return False
        return self.queue.enqueue(unit_type, resource_mgr)

    # ── 受傷 / 死亡 ───────────────────────────────────────────────────────────
    def take_damage(self, amount: int, vfx_callback: Optional[VFXCallback] = None) -> None:
        if self.is_dead:
            return
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.die(vfx_callback)

    def die(self, vfx_callback: Optional[VFXCallback] = None) -> None:
        self.is_dead = True
        if vfx_callback:
            vfx_callback(tuple(self.pos))
        print(f"[Building] 💀 {self.kind} (team={self.team}) 被摧毀")

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        super().draw(screen, camera_offset)
        self._draw_hp_bar(screen, camera_offset)
        # 正在生產時顯示進度弧
        if self.queue and self.queue.is_busy:
            self._draw_production_bar(screen, camera_offset)
        # 煉油廠標示
        if self.gives_income:
            self._draw_refinery_indicator(screen, camera_offset)

    def _draw_hp_bar(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        bar_w, bar_h = 80, 6
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 22
        ratio = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(screen, (80, 0, 0),    (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (0, 200, 60),  (x, y, int(bar_w * ratio), bar_h))
        pygame.draw.rect(screen, (200, 200, 200),(x, y, bar_w, bar_h), 1)

    def _draw_production_bar(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        """在建築下方繪製生產進度條。"""
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        bar_w, bar_h = 80, 5
        x = cx - bar_w // 2
        y = cy + self.surface.get_height() // 2 + 4
        progress = self.queue.current_progress if self.queue else 0.0
        pygame.draw.rect(screen, (40, 40, 80),  (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (80, 160, 255),(x, y, int(bar_w * progress), bar_h))
        pygame.draw.rect(screen, (120, 120, 180),(x, y, bar_w, bar_h), 1)

    def _draw_refinery_indicator(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        """煉油廠：右上角金色閃爍圓點。"""
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        pygame.draw.circle(screen, (255, 200, 30), (cx + 38, cy - 38), 7)
        pygame.draw.circle(screen, (255, 255, 180),(cx + 38, cy - 38), 4)


# ── 單位 ─────────────────────────────────────────────────────────────────────
class Unit(GameSprite):
    """
    可移動的兵種單位，含戰鬥 FSM。

    狀態
    ----
    "march"  : 依 waypoints 前進
    "combat" : 停止移動，對最近敵人持續攻擊
    "dead"   : 已陣亡，等待 BattleManager 移除

    Parameters
    ----------
    kind        : "marine" | "tank"
    speed       : 每幀移動像素（可覆寫規格表）
    hp          : 血量（可覆寫規格表）
    team        : 0 = 玩家, 1 = 敵方
    scan_range  : 偵測敵人的圓形半徑（px）
    atk_cd      : 攻擊冷卻（幀數）
    atk_dmg     : 單次傷害值
    """

    def __init__(
        self,
        kind: str,
        manager: AssetManager,
        pos: tuple[float, float],
        speed: Optional[float]     = None,
        hp: Optional[int]          = None,
        team: int                  = 0,
        scan_range: Optional[float]= None,
        atk_cd: Optional[int]      = None,
        atk_dmg: Optional[int]     = None,
    ) -> None:
        stats = UNIT_STATS.get(kind, UNIT_STATS["marine"])
        scale = stats["scale"]
        super().__init__(kind, manager, pos, scale=scale)

        # 數值（可被呼叫端覆寫，否則用規格表預設）
        self.kind        = kind
        self.hp          = hp        if hp        is not None else stats["hp"]
        self.max_hp      = self.hp
        self.speed       = speed     if speed     is not None else stats["speed"]
        self.atk_dmg     = atk_dmg   if atk_dmg   is not None else stats["atk_dmg"]
        self.atk_cd      = atk_cd    if atk_cd    is not None else stats["atk_cd"]
        self.scan_range  = scan_range if scan_range is not None else stats["scan_range"]
        self.collision_radius = stats["col_radius"]
        self.team        = team

        # FSM
        self.state: str  = "march"
        self.is_dead     = False

        # 移動
        self.target: Optional[list[float]]         = None
        self.waypoints: list[tuple[float, float]]  = []

        # 攻擊冷卻計時器（從 0 開始，避免開場瞬間攻擊）
        self.atk_timer: int = 0

        # 當前鎖定目標（combat 狀態用）
        self._locked_enemy: Optional["Unit"] = None

    # ── 移動介面 ──────────────────────────────────────────────────────────────
    def move_to(self, target: tuple[float, float]) -> None:
        self.target = list(target)
        self.rotate_to(target)

    def set_waypoints(self, waypoints: list[tuple[float, float]]) -> None:
        self.waypoints = list(waypoints)
        if self.waypoints:
            self.move_to(self.waypoints[0])

    # ── 掃描 ──────────────────────────────────────────────────────────────────
    def scan_for_enemies(self, all_units: list["Unit"]) -> Optional["Unit"]:
        """
        在 scan_range 內尋找最近的敵方存活單位。
        等同於 pygame.sprite.spritecollide + collide_circle 的圓形掃描邏輯，
        但這裡回傳距離最近的單一目標。
        """
        nearest: Optional[Unit] = None
        nearest_dist = float("inf")
        for u in all_units:
            if u is self or u.team == self.team or u.is_dead:
                continue
            d = self.dist_to(u)
            if d <= self.scan_range and d < nearest_dist:
                nearest      = u
                nearest_dist = d
        return nearest

    # ── 攻擊 ──────────────────────────────────────────────────────────────────
    def attack(
        self,
        enemy: "Unit",
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        """
        若冷卻結束則對目標造成傷害，並在中間點產生爆炸特效。
        冷卻計時器每 update() 遞增 1，達到 atk_cd 時歸零觸發。
        """
        if self.atk_timer < self.atk_cd:
            return

        self.atk_timer = 0

        # 傷害
        enemy.take_damage(self.atk_dmg, vfx_callback)

        # 爆炸特效：在攻擊者與目標的中間點
        if vfx_callback:
            mid = (
                (self.pos[0] + enemy.pos[0]) / 2,
                (self.pos[1] + enemy.pos[1]) / 2,
            )
            vfx_callback(mid)

    # ── 受傷 / 死亡 ───────────────────────────────────────────────────────────
    def take_damage(
        self,
        amount: int,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        """扣除血量；歸零時觸發 die()。"""
        if self.is_dead:
            return
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.die(vfx_callback)

    def die(self, vfx_callback: Optional[VFXCallback] = None) -> None:
        """
        單位死亡：
        1. 狀態切換到 "dead"
        2. 在自身位置產生爆炸特效
        """
        if self.is_dead:
            return
        self.is_dead = True
        self.state   = "dead"
        self.target  = None
        self.waypoints.clear()
        if vfx_callback:
            vfx_callback(tuple(self.pos))
        print(f"[Unit] 💀 {self.kind} (team={self.team}) 陣亡於 {self.pos}")

    # ── 每幀更新 ──────────────────────────────────────────────────────────────
    def update(
        self,
        enemies: Optional[list["Unit"]] = None,
        vfx_callback: Optional[VFXCallback] = None,
    ) -> None:
        """
        FSM 更新主入口。
        - 傳入 enemies list 時啟用掃描 + 攻擊邏輯
        - 未傳入時退化為純移動模式（向後相容）
        """
        if self.is_dead:
            return

        # 攻擊冷卻累加（每幀 +1）
        if self.atk_timer < self.atk_cd:
            self.atk_timer += 1

        # ── 掃描邏輯 ──────────────────────────────────────────────────────────
        if enemies is not None:
            target_enemy = self.scan_for_enemies(enemies)

            if target_enemy:
                # 切換到 combat：停止前進，朝敵旋轉
                if self.state == "march":
                    self.state = "combat"
                    self._locked_enemy = target_enemy
                self.rotate_to(tuple(target_enemy.pos))
                self.attack(target_enemy, vfx_callback)
                return   # combat 狀態不移動

            else:
                # 敵人離開範圍（或已死亡）→ 恢復行軍
                if self.state == "combat":
                    self.state = "march"
                    self._locked_enemy = None
                    # 恢復剩餘 waypoints
                    if self.waypoints:
                        self.move_to(self.waypoints[0])

        # ── 移動邏輯（march 狀態）─────────────────────────────────────────────
        self._march_step()

    def _march_step(self) -> None:
        """沿 target / waypoints 前進一幀。"""
        if not self.target:
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
            return

        dx = self.target[0] - self.pos[0]
        dy = self.target[1] - self.pos[1]
        dist = math.hypot(dx, dy)

        if dist <= self.speed:
            self.pos[0] = self.target[0]
            self.pos[1] = self.target[1]
            self.target = None
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
        else:
            self.pos[0] += (dx / dist) * self.speed
            self.pos[1] += (dy / dist) * self.speed

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        super().draw(screen, camera_offset)
        self._draw_hp_bar(screen, camera_offset)

    def draw_debug(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_dead:
            return
        super().draw_debug(screen, camera_offset)
        # 掃描範圍圓（半透明感用低飽和色）
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        color = (80, 160, 255) if self.state == "march" else (255, 80, 80)
        pygame.draw.circle(screen, color, (cx, cy), int(self.scan_range), 1)

    def _draw_hp_bar(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        bar_w, bar_h = 32, 4
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 8
        ratio = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(screen, (100, 0, 0),  (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (0, 220, 80), (x, y, int(bar_w * ratio), bar_h))


# ── VFX 動畫 Sprite ───────────────────────────────────────────────────────────
class VFXSprite:
    """
    從 Sprite Sheet 播放一次性動畫（爆炸特效）。
    is_done == True 時由 BattleManager 移除。
    """

    def __init__(
        self,
        sheet_key: str,
        manager: AssetManager,
        pos: tuple[float, float],
        frame_delay: int = 3,
    ) -> None:
        self.pos         = list(pos)
        self.frames      = manager.get_frames(sheet_key)
        self.frame_idx   = 0
        self.frame_timer = 0
        self.frame_delay = frame_delay
        self.is_done     = False

    def update(self) -> None:
        if self.is_done:
            return
        self.frame_timer += 1
        if self.frame_timer >= self.frame_delay:
            self.frame_timer = 0
            self.frame_idx  += 1
            if self.frame_idx >= len(self.frames):
                self.is_done = True

    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        if self.is_done:
            return
        frame = self.frames[self.frame_idx]
        rect  = frame.get_rect(
            center=(
                int(self.pos[0]) - camera_offset[0],
                int(self.pos[1]) - camera_offset[1],
            )
        )
        screen.blit(frame, rect)
