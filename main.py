"""
main.py — Star Raise Game  (v4: AI + API + Base Assault)

執行緒架構
----------
  主執行緒  : pygame GameLoop（必須在主執行緒）
  背景執行緒: uvicorn FastAPI（daemon，隨主執行緒結束）

場景配置
--------
  [玩家 Team 0 — 左側]
    Barracks  (80, H/2)       → B 鍵 Marine(50💎) / T 鍵 Tank(150💎)
    Refinery  (80, H/2-120)   → +15/週期被動收入

  [敵方 Team 1 — 右側]
    Barracks  (W-80, H/2)     → AIController 每 10s 決策生產
    Refinery  (W-80, H/2-120) → AI 收入來源

勝敗條件
--------
  VICTORY : 敵方 Barracks 或 Refinery HP 歸零
  DEFEAT  : 玩家 Barracks 或 Refinery HP 歸零

熱鍵
----
  B     生產 Marine   (50 礦)
  T     生產 Tank    (150 礦)
  D     切換 Debug 模式
  R     重置場景
  ESC   離開
  左鍵  手動爆炸 VFX
"""

from __future__ import annotations

import os
import sys
import threading

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite
from src.battle        import BattleManager
from src.logic         import (
    ResourceManager, ProductionQueue, AIController,
    UNIT_COSTS,
)
import src.shared as shared

# ── 視窗與常數 ────────────────────────────────────────────────────────────────
SCREEN_W = 1024
SCREEN_H = 768
FPS      = 60
TITLE    = "⭐ Star Raise — v4 AI + API"

COLOR_BG      = (18,  22,  36)
COLOR_GRID    = (28,  34,  50)
COLOR_TEXT    = (200, 220, 255)
COLOR_HOTKEY  = (255, 200, 60)
COLOR_WARN    = (255, 80,  80)
COLOR_OK      = (80,  220, 120)
COLOR_MINERAL = (100, 200, 255)
COLOR_GOLD    = (255, 200, 30)
COLOR_QUEUE   = (80,  140, 255)
COLOR_VICTORY = (60,  220, 100)
COLOR_DEFEAT  = (220, 60,  60)

API_PORT = int(os.environ.get("PORT", 8000))


# ── 背景 API 執行緒 ───────────────────────────────────────────────────────────
def _start_api_server() -> None:
    """在 daemon 執行緒中啟動 uvicorn，不阻塞 pygame 主執行緒。"""
    try:
        import uvicorn
        uvicorn.run(
            "server:app",
            host="0.0.0.0",
            port=API_PORT,
            log_level="warning",
            access_log=False,
        )
    except Exception as e:
        print(f"[API] ⚠️  API 伺服器啟動失敗: {e}")


def launch_api_thread() -> threading.Thread:
    t = threading.Thread(target=_start_api_server, daemon=True, name="api-server")
    t.start()
    print(f"[API] 🚀 FastAPI 啟動於 http://localhost:{API_PORT}")
    print(f"[API]    端點: /api/game_state  /api/units  /api/buildings")
    return t


# ── 單位工廠 ──────────────────────────────────────────────────────────────────
def make_unit(
    unit_type: str,
    manager: AssetManager,
    spawn_pos: tuple[float, float],
    team: int,
) -> Unit:
    """team=0 → 向右行軍，team=1 → 向左行軍。"""
    dest = (SCREEN_W - 160, spawn_pos[1]) if team == 0 else (160, spawn_pos[1])
    u = Unit(unit_type, manager, pos=spawn_pos, team=team)
    u.set_waypoints([dest])
    return u


# ── 背景 ──────────────────────────────────────────────────────────────────────
def draw_background(screen: pygame.Surface) -> None:
    screen.fill(COLOR_BG)
    for x in range(0, SCREEN_W, 64):
        pygame.draw.line(screen, COLOR_GRID, (x, 0), (x, SCREEN_H))
    for y in range(0, SCREEN_H, 64):
        pygame.draw.line(screen, COLOR_GRID, (0, y), (SCREEN_W, y))
    pygame.draw.line(screen, (40, 60, 110),
                     (SCREEN_W // 2, 0), (SCREEN_W // 2, SCREEN_H), 1)


# ── 勝敗覆蓋層 ────────────────────────────────────────────────────────────────
def draw_result_overlay(screen: pygame.Surface, result: str) -> None:
    """VICTORY / DEFEAT 半透明全螢幕覆蓋，按 R 重置。"""
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    if result == "VICTORY":
        overlay.fill((20, 80, 20, 180))
        main_color   = COLOR_VICTORY
        main_text    = "★  VICTORY  ★"
    else:
        overlay.fill((80, 20, 20, 180))
        main_color   = COLOR_DEFEAT
        main_text    = "✕  DEFEAT  ✕"

    screen.blit(overlay, (0, 0))

    font_big = pygame.font.Font(None, 96)
    font_sub = pygame.font.Font(None, 32)

    main_surf = font_big.render(main_text, True, main_color)
    sub_surf  = font_sub.render("按 R 重置  |  按 ESC 離開", True, COLOR_TEXT)

    screen.blit(main_surf, main_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 - 30)))
    screen.blit(sub_surf,  sub_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2 + 60)))


# ── 經濟面板（玩家）─────────────────────────────────────────────────────────
def draw_economy_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    res: ResourceManager,
    queue: ProductionQueue,
    income_flash: bool,
) -> None:
    panel = pygame.Surface((262, 128), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 155))
    screen.blit(panel, (8, 8))

    y = 14
    mineral_col = COLOR_GOLD if income_flash else COLOR_MINERAL
    screen.blit(font.render(f"💎 礦石: {res.minerals}", True, mineral_col), (14, y))
    y += 18

    screen.blit(
        font.render(
            f"收入: +{res.income_per_cycle}/週期  ({res.frames_to_next_cycle}f)",
            True, COLOR_TEXT,
        ), (14, y),
    )
    y += 14
    bar_w = 242
    pygame.draw.rect(screen, (40, 40, 60),   (14, y, bar_w, 6))
    pygame.draw.rect(screen, COLOR_GOLD,     (14, y, int(bar_w * res.cycle_progress), 6))
    pygame.draw.rect(screen, (120, 100, 40), (14, y, bar_w, 6), 1)
    y += 12

    screen.blit(font.render("── 生產佇列 ──", True, COLOR_QUEUE), (14, y))
    y += 16

    if queue.is_busy:
        screen.blit(
            font.render(
                f"▶ {(queue.current_unit or '?').upper()}  "
                f"{queue.frames_remaining}f  [{queue.queue_len}排隊]",
                True, COLOR_OK,
            ), (14, y),
        )
        y += 14
        pygame.draw.rect(screen, (30, 60, 30), (14, y, bar_w, 7))
        pygame.draw.rect(screen, COLOR_OK,     (14, y, int(bar_w * queue.current_progress), 7))
        pygame.draw.rect(screen, (60, 120, 60),(14, y, bar_w, 7), 1)
        y += 10
        for idx, kind in enumerate(queue.queue_summary()):
            label = "M" if kind == "marine" else "T"
            col   = (80, 160, 255) if kind == "marine" else (80, 220, 80)
            pygame.draw.rect(screen, col, (14 + idx * 22, y, 18, 18))
            screen.blit(font.render(label, True, (0, 0, 0)), (18 + idx * 22, y + 2))
    else:
        screen.blit(font.render("閒置 — 按 B 生產 Marine / T 生產 Tank",
                                True, (140, 140, 180)), (14, y))


# ── AI 狀態面板（右側）──────────────────────────────────────────────────────
def draw_ai_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    ai: AIController,
) -> None:
    panel = pygame.Surface((220, 80), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 155))
    x0 = SCREEN_W - 228
    screen.blit(panel, (x0, 8))

    y = 14
    screen.blit(font.render("🤖 AI 狀態", True, COLOR_WARN), (x0 + 6, y))
    y += 16
    screen.blit(
        font.render(
            f"礦石: {ai.resource_mgr.minerals}  "
            f"收入: {ai.resource_mgr.income_per_cycle}",
            True, COLOR_TEXT,
        ), (x0 + 6, y),
    )
    y += 14
    next_dec = ai.decision_frames - ai._timer
    screen.blit(
        font.render(
            f"決策倒數: {next_dec}f  "
            f"佇列: {ai.queue.queue_len}  "
            f"已派: {ai.total_spawned}",
            True, COLOR_TEXT,
        ), (x0 + 6, y),
    )
    y += 14
    screen.blit(
        font.render(f"上次: {ai.last_decision}", True, (180, 140, 200)),
        (x0 + 6, y),
    )


# ── 底部熱鍵欄 ────────────────────────────────────────────────────────────────
def draw_hotkey_bar(
    screen: pygame.Surface,
    font: pygame.font.Font,
    res: ResourceManager,
    debug: bool,
) -> None:
    marine_col = COLOR_OK if res.minerals >= UNIT_COSTS["marine"] else COLOR_WARN
    tank_col   = COLOR_OK if res.minerals >= UNIT_COSTS["tank"]   else COLOR_WARN
    parts = [
        (f"[B] Marine {UNIT_COSTS['marine']}💎", marine_col),
        ("  ", COLOR_TEXT),
        (f"[T] Tank {UNIT_COSTS['tank']}💎", tank_col),
        ("  |  [D] Debug", COLOR_WARN if debug else COLOR_HOTKEY),
        ("  [R] Reset  [ESC] 離開", COLOR_HOTKEY),
    ]
    x, y = 10, SCREEN_H - 20
    for text, color in parts:
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))
        x += surf.get_width()


# ── 單位卡片 ──────────────────────────────────────────────────────────────────
def draw_unit_cards(
    screen: pygame.Surface,
    font: pygame.font.Font,
    units: list[Unit],
) -> None:
    team0 = [u for u in units if u.team == 0][:3]
    team1 = [u for u in units if u.team == 1][:3]
    for group, x_base in [(team0, 10), (team1, SCREEN_W - 220)]:
        for i, u in enumerate(group):
            y_base = 148 + i * 58
            card = pygame.Surface((210, 50), pygame.SRCALPHA)
            card.fill((0, 0, 0, 130))
            screen.blit(card, (x_base, y_base))
            sym   = {"march": "🚶", "combat": "⚔", "assault": "🏰", "dead": "💀"}.get(u.state, u.state)
            col   = COLOR_OK if u.team == 0 else COLOR_WARN
            label = ["[玩家]", "[敵方]"][u.team]
            screen.blit(
                font.render(f"{label} {u.kind.upper()} {sym}", True, col),
                (x_base + 6, y_base + 4),
            )
            bar_w, bar_h = 196, 9
            ratio = max(0.0, u.hp / u.max_hp)
            bar_c = (0, 200, 80) if ratio > 0.5 else (220, 180, 0) if ratio > 0.25 else (220, 50, 50)
            pygame.draw.rect(screen, (80, 0, 0),    (x_base + 6, y_base + 26, bar_w, bar_h))
            pygame.draw.rect(screen, bar_c,          (x_base + 6, y_base + 26, int(bar_w * ratio), bar_h))
            pygame.draw.rect(screen, (160, 160, 160),(x_base + 6, y_base + 26, bar_w, bar_h), 1)
            screen.blit(
                font.render(f"HP {u.hp}/{u.max_hp}", True, COLOR_TEXT),
                (x_base + 6, y_base + 37),
            )


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.font    = pygame.font.Font(None, 18)
        self.fps_clk = pygame.time.Clock()
        self.frame   = 0

        # ── 素材 ──────────────────────────────────────────────────────────────
        self.manager = AssetManager()
        print("\n📦 預載素材...")
        self.manager.preload_all()
        print("✅ 預載完成\n")

        # ── API 背景執行緒 ────────────────────────────────────────────────────
        launch_api_thread()

        # ── 場景初始化 ────────────────────────────────────────────────────────
        self._init_scene()

    # ── 場景初始化（可重置）──────────────────────────────────────────────────
    def _init_scene(self) -> None:
        # VFX
        self.vfx_list: list[VFXSprite] = []

        def spawn_vfx(pos: tuple[float, float]) -> None:
            self.vfx_list.append(
                VFXSprite("explosion_sheet", self.manager, pos, frame_delay=3)
            )
        self.spawn_vfx = spawn_vfx

        # ── 玩家建築 ──────────────────────────────────────────────────────────
        self.player_barracks = Building(
            "barracks", self.manager, pos=(80, SCREEN_H // 2), team=0, hp=600,
        )
        self.player_refinery = Building(
            "refinery", self.manager, pos=(80, SCREEN_H // 2 - 120), team=0, hp=400,
        )
        # 玩家資源
        self.res = ResourceManager(starting=100)
        self.res.register_refinery()
        # 玩家生產佇列注入 Barracks
        self.player_barracks.queue = ProductionQueue(
            spawn_pos=self.player_barracks.spawn_point
        )

        # ── 敵方建築 ──────────────────────────────────────────────────────────
        self.enemy_barracks = Building(
            "barracks", self.manager, pos=(SCREEN_W - 80, SCREEN_H // 2), team=1, hp=600,
        )
        self.enemy_refinery = Building(
            "refinery", self.manager, pos=(SCREEN_W - 80, SCREEN_H // 2 - 120), team=1, hp=400,
        )
        # 敵方 AI 資源 + 佇列
        ai_res   = ResourceManager(starting=100)
        ai_res.register_refinery()
        ai_queue = ProductionQueue(spawn_pos=self.enemy_barracks.spawn_point)
        self.enemy_barracks.queue = ai_queue
        self.ai = AIController(ai_res, ai_queue, decision_frames=600)

        # ── 單位列表 ──────────────────────────────────────────────────────────
        self.units: list[Unit] = []

        # ── 勝敗狀態 ──────────────────────────────────────────────────────────
        self.game_result: str | None = None

        # ── UI 狀態 ───────────────────────────────────────────────────────────
        self.debug_mode   = False
        self.income_flash = 0

        print("[GameLoop] 🔄 場景初始化完成")

    # ── 便利屬性 ──────────────────────────────────────────────────────────────
    @property
    def player_queue(self) -> ProductionQueue:
        return self.player_barracks.queue  # type: ignore[return-value]

    @property
    def all_buildings(self) -> list[Building]:
        return [
            self.player_barracks, self.player_refinery,
            self.enemy_barracks,  self.enemy_refinery,
        ]

    # ── 勝敗檢查 ──────────────────────────────────────────────────────────────
    def _check_victory_condition(self) -> None:
        if self.game_result:
            return
        player_dead = (self.player_barracks.is_dead or self.player_refinery.is_dead)
        enemy_dead  = (self.enemy_barracks.is_dead  or self.enemy_refinery.is_dead)
        if enemy_dead and not player_dead:
            self.game_result = "VICTORY"
            shared.write({"game_result": "VICTORY"})
            print("[Game] 🏆 VICTORY")
        elif player_dead:
            self.game_result = "DEFEAT"
            shared.write({"game_result": "DEFEAT"})
            print("[Game] 💔 DEFEAT")

    # ── 共享狀態快照（每幀寫入 src.shared）──────────────────────────────────
    def _push_state(self) -> None:
        shared.write({
            "frame":       self.frame,
            "game_result": self.game_result,
            "minerals":    self.res.minerals,
            "income_rate": self.res.income_per_cycle,
            "unit_count":  sum(1 for u in self.units if not u.is_dead),
            "units": [
                {
                    "kind":   u.kind,
                    "team":   u.team,
                    "hp":     u.hp,
                    "max_hp": u.max_hp,
                    "state":  u.state,
                    "pos":    [round(u.pos[0], 1), round(u.pos[1], 1)],
                }
                for u in self.units if not u.is_dead
            ],
            "buildings": [
                {
                    "kind":    b.kind,
                    "team":    b.team,
                    "hp":      b.hp,
                    "max_hp":  b.max_hp,
                    "is_dead": b.is_dead,
                }
                for b in self.all_buildings
            ],
        })

    # ── 主迴圈 ────────────────────────────────────────────────────────────────
    def run(self) -> None:
        running = True
        while running:
            self.fps_clk.tick(FPS)
            self.frame += 1
            fps = self.fps_clk.get_fps()

            # ── 事件 ──────────────────────────────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self._init_scene()
                    elif event.key == pygame.K_d:
                        self.debug_mode = not self.debug_mode
                    elif event.key == pygame.K_b and not self.game_result:
                        self.player_barracks.produce("marine", self.res)
                    elif event.key == pygame.K_t and not self.game_result:
                        self.player_barracks.produce("tank", self.res)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.spawn_vfx(pygame.mouse.get_pos())

            # ── 遊戲邏輯（勝負已定時暫停）────────────────────────────────────
            if not self.game_result:

                # 1) 玩家收入週期
                if self.res.update():
                    self.income_flash = 30
                if self.income_flash > 0:
                    self.income_flash -= 1

                # 2) 玩家生產佇列
                finished_player = self.player_queue.update()
                if finished_player:
                    u = make_unit(finished_player, self.manager,
                                  self.player_barracks.spawn_point, team=0)
                    self.units.append(u)
                    print(f"[Player] 🔵 {finished_player} 出兵")

                # 3) 敵方 AI（收入 + 佇列 + 決策 一體呼叫）
                finished_ai = self.ai.update()
                if finished_ai:
                    u = make_unit(finished_ai, self.manager,
                                  self.enemy_barracks.spawn_point, team=1)
                    self.units.append(u)
                    print(f"[AI] 🔴 {finished_ai} 出兵")

                # 4) 戰鬥（Unit vs Unit + Unit vs Building）
                BattleManager.process_combat(
                    self.units,
                    self.spawn_vfx,
                    buildings=self.all_buildings,
                )

                # 5) 碰撞分離
                BattleManager.resolve_collisions(self.units)

                # 6) 死亡清理
                self.units = BattleManager.cleanup_dead(self.units)

                # 7) VFX
                self.vfx_list = BattleManager.update_vfx(self.vfx_list)

                # 8) 勝敗判斷
                self._check_victory_condition()

            # 9) API 快照（無論勝負都更新）
            self._push_state()

            # ── 渲染 ──────────────────────────────────────────────────────────
            draw_background(self.screen)

            for bld in self.all_buildings:
                bld.draw(self.screen)

            for u in self.units:
                u.draw(self.screen)
                if self.debug_mode:
                    u.draw_debug(self.screen)

            for vfx in self.vfx_list:
                vfx.draw(self.screen)

            draw_economy_panel(
                self.screen, self.font,
                self.res, self.player_queue,
                income_flash=self.income_flash > 0,
            )
            draw_ai_panel(self.screen, self.font, self.ai)
            draw_unit_cards(self.screen, self.font, self.units)
            draw_hotkey_bar(self.screen, self.font, self.res, self.debug_mode)

            self.screen.blit(
                self.font.render(f"FPS:{fps:.0f}  Frame:{self.frame}", True, COLOR_TEXT),
                (SCREEN_W // 2 - 60, 10),
            )

            # 勝敗覆蓋層（最後繪製）
            if self.game_result:
                draw_result_overlay(self.screen, self.game_result)

            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    GameLoop().run()
