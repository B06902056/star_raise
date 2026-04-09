"""
sprite.py — Star Raise Game
定義 Sprite 基底類別、Building、Unit，
以及支援 Sprite Sheet 動畫的 VFXSprite。
"""

import math
import pygame
from typing import Optional
from src.asset_manager import AssetManager


# ── 基底 Sprite ───────────────────────────────────────────────────────────────
class GameSprite:
    """
    所有遊戲物件的基底類別。

    Attributes
    ----------
    pos    : 世界座標 (x, y)，中心點
    angle  : 面向角度（度），0 = 朝右，逆時針為正
    surface: 當前 pygame.Surface
    """

    def __init__(
        self,
        asset_key: str,
        manager: AssetManager,
        pos: tuple[float, float] = (0.0, 0.0),
        scale: Optional[tuple[int, int]] = None,
    ) -> None:
        self.asset_key = asset_key
        self.manager   = manager
        self.pos       = list(pos)       # [x, y]
        self.angle     = 0.0             # 度
        self._base_surface = manager.get(asset_key, scale=scale)
        self.surface   = self._base_surface

    # ── 旋轉 ──────────────────────────────────────────────────────────────────
    def rotate_to(self, target: tuple[float, float]) -> None:
        """
        計算朝向目標點的角度並旋轉 Surface。

        Parameters
        ----------
        target : 目標世界座標 (x, y)
        """
        dx = target[0] - self.pos[0]
        dy = target[1] - self.pos[1]
        # pygame Y 軸向下，因此取負號讓 0° 對應「朝右」
        self.angle = math.degrees(math.atan2(-dy, dx))
        self._apply_rotation()

    def rotate_by(self, delta_deg: float) -> None:
        """累加旋轉角度。"""
        self.angle = (self.angle + delta_deg) % 360
        self._apply_rotation()

    def _apply_rotation(self) -> None:
        self.surface = pygame.transform.rotate(self._base_surface, self.angle)

    # ── 渲染 ──────────────────────────────────────────────────────────────────
    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        """將 Surface 以中心點繪製到螢幕。"""
        rect = self.surface.get_rect(
            center=(
                int(self.pos[0]) - camera_offset[0],
                int(self.pos[1]) - camera_offset[1],
            )
        )
        screen.blit(self.surface, rect)

    def draw_debug(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        """繪製碰撞框與中心點（開發用）。"""
        rect = self.surface.get_rect(
            center=(
                int(self.pos[0]) - camera_offset[0],
                int(self.pos[1]) - camera_offset[1],
            )
        )
        pygame.draw.rect(screen, (0, 255, 0), rect, 1)
        pygame.draw.circle(screen, (255, 0, 0), rect.center, 3)

    @property
    def rect(self) -> pygame.Rect:
        return self.surface.get_rect(center=(int(self.pos[0]), int(self.pos[1])))


# ── 建築 ─────────────────────────────────────────────────────────────────────
class Building(GameSprite):
    """
    靜態建築物件。
    建築不移動，但可被選取或標記為「生產中」。

    Parameters
    ----------
    kind      : "barracks" | "refinery" 等 ASSET_SPEC key
    hp        : 血量
    team      : 0 = 玩家, 1 = 敵方
    """

    NAMES = {
        "barracks": "兵營",
        "refinery": "採礦場",
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
        self.producing = False

    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        super().draw(screen, camera_offset)
        self._draw_hp_bar(screen, camera_offset)
        if self.producing:
            self._draw_produce_indicator(screen, camera_offset)

    def _draw_hp_bar(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        bar_w, bar_h = 80, 6
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 12
        ratio = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(screen, (80, 0, 0),   (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (0, 200, 60),  (x, y, int(bar_w * ratio), bar_h))
        pygame.draw.rect(screen, (200, 200, 200),(x, y, bar_w, bar_h), 1)

    def _draw_produce_indicator(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        pygame.draw.circle(screen, (255, 220, 0), (cx + 36, cy - 36), 6)


# ── 單位 ─────────────────────────────────────────────────────────────────────
class Unit(GameSprite):
    """
    可移動的兵種單位。
    支援朝向目標基地旋轉、沿路徑前進。

    Parameters
    ----------
    kind   : "marine" | "tank" 等 ASSET_SPEC key
    speed  : 每幀移動像素數
    hp     : 血量
    team   : 0 = 玩家, 1 = 敵方
    """

    UNIT_SCALE = {
        "marine": (32, 32),
        "tank":   (48, 48),
    }

    def __init__(
        self,
        kind: str,
        manager: AssetManager,
        pos: tuple[float, float],
        speed: float = 2.0,
        hp: int = 100,
        team: int = 0,
    ) -> None:
        scale = self.UNIT_SCALE.get(kind, (32, 32))
        super().__init__(kind, manager, pos, scale=scale)
        self.kind     = kind
        self.speed    = speed
        self.hp       = hp
        self.max_hp   = hp
        self.team     = team
        self.target:  Optional[list[float]] = None   # 移動目標座標
        self.waypoints: list[tuple[float, float]] = []

    # ── 設定目標 ──────────────────────────────────────────────────────────────
    def move_to(self, target: tuple[float, float]) -> None:
        """設定移動目標並立即旋轉朝向它。"""
        self.target = list(target)
        self.rotate_to(target)

    def set_waypoints(self, waypoints: list[tuple[float, float]]) -> None:
        """設定路徑點列表，單位依序前進。"""
        self.waypoints = list(waypoints)
        if self.waypoints:
            self.move_to(self.waypoints[0])

    # ── 每幀更新 ──────────────────────────────────────────────────────────────
    def update(self) -> None:
        """處理移動邏輯，到達路徑點後自動切換下一個。"""
        if not self.target:
            # 若有 waypoints 未設定 target，取第一個
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
            return

        dx = self.target[0] - self.pos[0]
        dy = self.target[1] - self.pos[1]
        dist = math.hypot(dx, dy)

        if dist <= self.speed:
            # 到達目標
            self.pos[0] = self.target[0]
            self.pos[1] = self.target[1]
            self.target = None
            if self.waypoints:
                self.move_to(self.waypoints.pop(0))
        else:
            self.pos[0] += (dx / dist) * self.speed
            self.pos[1] += (dy / dist) * self.speed

    def draw(self, screen: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)) -> None:
        super().draw(screen, camera_offset)
        self._draw_hp_bar(screen, camera_offset)

    def _draw_hp_bar(self, screen: pygame.Surface, camera_offset: tuple[int, int]) -> None:
        cx = int(self.pos[0]) - camera_offset[0]
        cy = int(self.pos[1]) - camera_offset[1]
        bar_w, bar_h = 28, 4
        x = cx - bar_w // 2
        y = cy - self.surface.get_height() // 2 - 8
        ratio = max(0.0, self.hp / self.max_hp)
        pygame.draw.rect(screen, (100, 0, 0),   (x, y, bar_w, bar_h))
        pygame.draw.rect(screen, (0, 220, 80),  (x, y, int(bar_w * ratio), bar_h))


# ── VFX 動畫 Sprite ───────────────────────────────────────────────────────────
class VFXSprite:
    """
    從 Sprite Sheet 播放一次性動畫（爆炸特效）。

    使用方式
    --------
    vfx = VFXSprite("explosion_sheet", manager, pos=(400, 300))
    # 每幀呼叫 update() 與 draw()，is_done 為 True 時移除
    """

    def __init__(
        self,
        sheet_key: str,
        manager: AssetManager,
        pos: tuple[float, float],
        frame_delay: int = 4,           # 每 N 幀切換一格
    ) -> None:
        self.pos     = list(pos)
        self.frames  = manager.get_frames(sheet_key)
        self.frame_idx    = 0
        self.frame_timer  = 0
        self.frame_delay  = frame_delay
        self.is_done      = False

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
