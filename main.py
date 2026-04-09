"""
main.py — Star Raise Game  (v2: Battle Logic Demo)

示範場景：Marine (Team 0, 左) vs Tank (Team 1, 右)
- 兩者從對角出發，互相行軍
- 進入 scan_range 後自動停步、攻擊、播放爆炸 VFX
- 死亡後 120 幀 (2 秒) 重生，循環測試
- 左鍵: 手動觸發爆炸
- R 鍵: 立即重置雙方
- D 鍵: 切換 Debug 模式（顯示碰撞圓 + 掃描範圍）
- ESC : 離開
"""

import sys
import os
import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite
from src.battle        import BattleManager

# ── 視窗與常數 ────────────────────────────────────────────────────────────────
SCREEN_W  = 1024
SCREEN_H  = 768
FPS       = 60
TITLE     = "⭐ Star Raise — Battle Demo v2"

COLOR_BG      = (18, 22, 36)
COLOR_GRID    = (28, 34, 50)
COLOR_TEXT    = (200, 220, 255)
COLOR_HOTKEY  = (255, 200, 60)
COLOR_WARN    = (255, 80, 80)
COLOR_OK      = (80, 220, 120)

# 重生計時（幀）
RESPAWN_DELAY = 120


# ── 場景工廠 ──────────────────────────────────────────────────────────────────
def make_marine(manager: AssetManager) -> Unit:
    u = Unit("marine", manager, pos=(160, SCREEN_H // 2), team=0)
    u.set_waypoints([(SCREEN_W - 160, SCREEN_H // 2)])
    return u


def make_tank(manager: AssetManager) -> Unit:
    u = Unit("tank", manager, pos=(SCREEN_W - 160, SCREEN_H // 2), team=1)
    u.set_waypoints([(160, SCREEN_H // 2)])
    return u


# ── 背景 ──────────────────────────────────────────────────────────────────────
def draw_background(screen: pygame.Surface) -> None:
    screen.fill(COLOR_BG)
    for x in range(0, SCREEN_W, 64):
        pygame.draw.line(screen, COLOR_GRID, (x, 0), (x, SCREEN_H))
    for y in range(0, SCREEN_H, 64):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))
    # 中線
    pygame.draw.line(screen, (40, 60, 110), (SCREEN_W // 2, 0), (SCREEN_W // 2, SCREEN_H), 1)


# ── HUD ───────────────────────────────────────────────────────────────────────
def draw_hud(
    screen: pygame.Surface,
    font: pygame.font.Font,
    fps: float,
    units: list[Unit],
    debug: bool,
    respawn_timer: dict,
) -> None:

    # FPS
    screen.blit(font.render(f"FPS: {fps:.0f}", True, COLOR_TEXT), (10, 10))

    # 按鍵說明
    hints = ["D: Debug  |  R: Reset  |  左鍵: VFX  |  ESC: 離開"]
    screen.blit(font.render(hints[0], True, COLOR_HOTKEY), (10, SCREEN_H - 20))

    # Debug 標示
    if debug:
        screen.blit(
            font.render("● DEBUG ON", True, COLOR_WARN), (SCREEN_W - 120, 10)
        )

    # 每個單位狀態卡片
    for i, u in enumerate(units):
        x_base = 10 if u.team == 0 else SCREEN_W - 220
        y_base = 36 + i * 60

        # 底板
        card = pygame.Surface((210, 52), pygame.SRCALPHA)
        card.fill((0, 0, 0, 120))
        screen.blit(card, (x_base, y_base))

        # 名稱 + 狀態
        state_sym = {"march": "🚶 行軍", "combat": "⚔ 戰鬥", "dead": "💀 陣亡"}.get(u.state, u.state)
        team_name = ["[玩家]", "[敵方]"][u.team]
        name_col  = COLOR_OK if u.team == 0 else COLOR_WARN
        screen.blit(
            font.render(f"{team_name} {u.kind.upper()}  {state_sym}", True, name_col),
            (x_base + 6, y_base + 4),
        )

        # HP 條
        bar_w, bar_h = 196, 10
        ratio = max(0.0, u.hp / u.max_hp) if not u.is_dead else 0.0
        bar_color = (
            (0, 200, 80)  if ratio > 0.5 else
            (220, 180, 0) if ratio > 0.25 else
            (220, 50, 50)
        )
        pygame.draw.rect(screen, (80, 0, 0),   (x_base + 6, y_base + 26, bar_w, bar_h))
        pygame.draw.rect(screen, bar_color,     (x_base + 6, y_base + 26, int(bar_w * ratio), bar_h))
        pygame.draw.rect(screen, (160, 160, 160),(x_base + 6, y_base + 26, bar_w, bar_h), 1)
        screen.blit(
            font.render(f"HP {u.hp}/{u.max_hp}", True, COLOR_TEXT),
            (x_base + 6, y_base + 38),
        )

        # 重生倒計時
        if u.is_dead and u.kind in respawn_timer:
            remain = max(0, RESPAWN_DELAY - respawn_timer[u.kind])
            screen.blit(
                font.render(f"重生倒數: {remain} 幀", True, (200, 200, 80)),
                (x_base + 6, y_base + 38),
            )

    # BattleManager 報告（底部）
    if units:
        report = BattleManager.debug_report(units)
        screen.blit(font.render(report, True, (140, 160, 200)), (10, SCREEN_H - 36))


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.font    = pygame.font.Font(None, 18)
        self.fps_clk = pygame.time.Clock()

        # 素材
        self.manager = AssetManager()
        print("\n📦 預載素材...")
        self.manager.preload_all()
        print("✅ 預載完成\n")

        # VFX 回調（閉包，讓 Unit/BattleManager 呼叫）
        self.vfx_list: list[VFXSprite] = []

        def spawn_vfx(pos: tuple[float, float]) -> None:
            self.vfx_list.append(
                VFXSprite("explosion_sheet", self.manager, pos, frame_delay=3)
            )

        self.spawn_vfx = spawn_vfx

        # 建築（純裝飾 / 未來擴充目標）
        self.player_base = Building("barracks", self.manager, pos=(80, SCREEN_H // 2), team=0)
        self.enemy_base  = Building("refinery", self.manager, pos=(SCREEN_W - 80, SCREEN_H // 2), team=1)

        # 單位列表
        self.units: list[Unit] = [
            make_marine(self.manager),
            make_tank(self.manager),
        ]

        # 重生計時器 { kind: 已過幀數 }
        self.respawn_timer: dict[str, int] = {}

        # 模式旗標
        self.debug_mode = False

    # ── 重置 ──────────────────────────────────────────────────────────────────
    def reset_units(self) -> None:
        self.units = [make_marine(self.manager), make_tank(self.manager)]
        self.respawn_timer.clear()
        self.vfx_list.clear()
        print("[GameLoop] 🔄 單位已重置")

    # ── 主迴圈 ────────────────────────────────────────────────────────────────
    def run(self) -> None:
        running = True
        while running:
            self.fps_clk.tick(FPS)
            fps = self.fps_clk.get_fps()

            # ── 事件 ──────────────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_d:
                        self.debug_mode = not self.debug_mode
                        print(f"[GameLoop] Debug: {self.debug_mode}")
                    elif event.key == pygame.K_r:
                        self.reset_units()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.spawn_vfx(pygame.mouse.get_pos())

            # ── 更新 ──────────────────────────────────────────────────────────

            # 1) 戰鬥邏輯（掃描 + 攻擊）
            BattleManager.process_combat(self.units, self.spawn_vfx)

            # 2) 碰撞分離（等價 pygame.sprite.spritecollide + collide_circle）
            BattleManager.resolve_collisions(self.units)

            # 3) 死亡清理 + 重生計時
            for u in self.units:
                if u.is_dead and u.kind not in self.respawn_timer:
                    self.respawn_timer[u.kind] = 0

            for kind in list(self.respawn_timer.keys()):
                self.respawn_timer[kind] += 1
                if self.respawn_timer[kind] >= RESPAWN_DELAY:
                    del self.respawn_timer[kind]
                    # 重生對應單位
                    if kind == "marine":
                        self.units.append(make_marine(self.manager))
                        print("[GameLoop] 🔵 Marine 重生")
                    elif kind == "tank":
                        self.units.append(make_tank(self.manager))
                        print("[GameLoop] 🟢 Tank 重生")

            self.units = BattleManager.cleanup_dead(self.units)

            # 4) VFX 更新
            self.vfx_list = BattleManager.update_vfx(self.vfx_list)

            # ── 渲染 ──────────────────────────────────────────────────────────
            draw_background(self.screen)

            # 建築
            self.player_base.draw(self.screen)
            self.enemy_base.draw(self.screen)

            # 單位
            for u in self.units:
                u.draw(self.screen)
                if self.debug_mode:
                    u.draw_debug(self.screen)

            # VFX
            for vfx in self.vfx_list:
                vfx.draw(self.screen)

            # HUD
            draw_hud(
                self.screen, self.font, fps,
                self.units, self.debug_mode, self.respawn_timer,
            )

            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    GameLoop().run()
