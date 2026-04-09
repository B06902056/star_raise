"""
main.py — Star Raise Game
GameLoop 示範:
  - 初始化 AssetManager，預載素材
  - 渲染一棟 Barracks 建築
  - 渲染一個朝敵方基地前進的 Marine 單位
  - 左鍵點擊產生爆炸特效
  - 右鍵點擊讓 Marine 追蹤滑鼠位置
"""

import sys
import os
import pygame

# 讓 Python 能找到 src/ 模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.asset_manager import AssetManager
from src.sprite import Building, Unit, VFXSprite

# ── 視窗設定 ──────────────────────────────────────────────────────────────────
SCREEN_W  = 1024
SCREEN_H  = 768
FPS       = 60
TITLE     = "⭐ Star Raise — Demo"

# ── 顏色 ──────────────────────────────────────────────────────────────────────
COLOR_BG       = (18, 22, 36)      # 深太空背景
COLOR_GRID     = (28, 34, 50)
COLOR_TEXT     = (200, 220, 255)
COLOR_HOTKEY   = (255, 200, 60)


# ── UI 面板 ───────────────────────────────────────────────────────────────────
def draw_hud(screen: pygame.Surface, font: pygame.font.Font, fps: float, unit_pos: list) -> None:
    """繪製 HUD 資訊列。"""
    lines = [
        f"FPS: {fps:.0f}",
        f"Marine 座標: ({unit_pos[0]:.0f}, {unit_pos[1]:.0f})",
        "右鍵 → Marine 移動到滑鼠",
        "左鍵 → 爆炸特效",
        "ESC  → 離開",
    ]
    for i, line in enumerate(lines):
        color = COLOR_HOTKEY if i >= 2 else COLOR_TEXT
        surf  = font.render(line, True, color)
        screen.blit(surf, (12, 12 + i * 20))


def draw_background(screen: pygame.Surface) -> None:
    """繪製格線背景，模擬戰略地圖感。"""
    screen.fill(COLOR_BG)
    for x in range(0, SCREEN_W, 64):
        pygame.draw.line(screen, COLOR_GRID, (x, 0), (x, SCREEN_H))
    for y in range(0, SCREEN_H, 64):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:
    """
    主遊戲迴圈，封裝：
    - init / load
    - event handling
    - update
    - render
    """

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.clock   = pygame.font.Font(None, 18)   # HUD 字型
        self.fps_clk = pygame.time.Clock()

        # ── 素材管理器 ──
        self.manager = AssetManager()
        print("\n📦 預載所有素材中...")
        self.manager.preload_all()
        print("✅ 素材預載完成\n")

        # ── 場景物件 ──
        # 玩家基地 (左下)
        self.player_base = Building(
            "barracks", self.manager,
            pos=(140, SCREEN_H - 160),
            team=0,
        )
        self.player_base.producing = True

        # 敵方基地 (右上)
        self.enemy_base = Building(
            "refinery", self.manager,
            pos=(SCREEN_W - 140, 160),
            team=1,
        )

        # Marine 從玩家基地出發，朝敵方基地前進
        self.marine = Unit(
            "marine", self.manager,
            pos=(200, SCREEN_H - 220),
            speed=1.8,
            team=0,
        )
        # 設定路徑點：先走中間再到敵基
        self.marine.set_waypoints([
            (SCREEN_W // 2, SCREEN_H // 2),
            (SCREEN_W - 140, 160),
        ])

        # VFX 列表（動態新增）
        self.vfx_list: list[VFXSprite] = []

    # ── 主迴圈 ────────────────────────────────────────────────────────────────
    def run(self) -> None:
        running = True
        while running:
            dt = self.fps_clk.tick(FPS)
            fps = self.fps_clk.get_fps()

            # ── 事件 ──
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = pygame.mouse.get_pos()

                    if event.button == 1:          # 左鍵 → 爆炸
                        vfx = VFXSprite(
                            "explosion_sheet",
                            self.manager,
                            pos=(mx, my),
                            frame_delay=3,
                        )
                        self.vfx_list.append(vfx)

                    elif event.button == 3:        # 右鍵 → Marine 移動
                        self.marine.waypoints.clear()
                        self.marine.move_to((mx, my))

            # ── 更新 ──
            self.marine.update()
            for vfx in self.vfx_list:
                vfx.update()
            self.vfx_list = [v for v in self.vfx_list if not v.is_done]

            # 若 Marine 到達敵基，從玩家基地重生
            dist_to_enemy = (
                (self.marine.pos[0] - self.enemy_base.pos[0]) ** 2 +
                (self.marine.pos[1] - self.enemy_base.pos[1]) ** 2
            ) ** 0.5
            if dist_to_enemy < 30 and not self.marine.target and not self.marine.waypoints:
                self.marine.pos = [200, SCREEN_H - 220]
                self.marine.set_waypoints([
                    (SCREEN_W // 2, SCREEN_H // 2),
                    (SCREEN_W - 140, 160),
                ])

            # ── 渲染 ──
            draw_background(self.screen)

            # 繪製陣營標示線
            pygame.draw.line(
                self.screen, (40, 60, 100),
                (0, SCREEN_H // 2), (SCREEN_W, SCREEN_H // 2), 1
            )

            # 建築
            self.player_base.draw(self.screen)
            self.enemy_base.draw(self.screen)

            # 單位
            self.marine.draw(self.screen)
            self.marine.draw_debug(self.screen)

            # 特效
            for vfx in self.vfx_list:
                vfx.draw(self.screen)

            # HUD
            draw_hud(self.screen, self.clock, fps, self.marine.pos)

            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    loop = GameLoop()
    loop.run()
