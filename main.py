"""
main.py — Star Raise Game  (v3: Economy & Spawning)

場景配置
--------
  [玩家左側]
    Barracks  (80, H/2)         → B 鍵生產 Marine (50💎)
    Refinery  (80, H/2-120)     → 被動收入 +15/週期

  [敵方右側]
    Barracks  (W-80, H/2)       → 未來 AI 擴充
    Refinery  (W-80, H/2-120)   → 敵方用（不影響玩家收入）

熱鍵
----
  B       → 生產 Marine   (50 礦)
  T       → 生產 Tank    (150 礦)
  D       → 切換 Debug 模式
  R       → 重置場景
  ESC     → 離開
  左鍵   → 手動爆炸 VFX
"""

import sys
import os
import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.asset_manager import AssetManager
from src.sprite        import Building, Unit, VFXSprite
from src.battle        import BattleManager
from src.logic         import ResourceManager, ProductionQueue, UNIT_COSTS, UNIT_BUILD_FRAMES

# ── 視窗與常數 ────────────────────────────────────────────────────────────────
SCREEN_W = 1024
SCREEN_H = 768
FPS      = 60
TITLE    = "⭐ Star Raise — Economy v3"

COLOR_BG       = (18, 22, 36)
COLOR_GRID     = (28, 34, 50)
COLOR_TEXT     = (200, 220, 255)
COLOR_HOTKEY   = (255, 200, 60)
COLOR_WARN     = (255, 80,  80)
COLOR_OK       = (80,  220, 120)
COLOR_MINERAL  = (100, 200, 255)
COLOR_GOLD     = (255, 200, 30)
COLOR_QUEUE    = (80,  140, 255)

# 自動重生延遲（敵方 AI 專用，玩家改為手動生產）
AI_RESPAWN_DELAY = 180   # 3 秒


# ── 單位工廠（遵循既有 lane 路徑邏輯）─────────────────────────────────────────
def make_unit(
    unit_type: str,
    manager: AssetManager,
    spawn_pos: tuple[float, float],
    team: int,
) -> Unit:
    """
    從 spawn_pos 出發，朝對方基地行軍。
    lane 終點固定為 X 方向對岸（Y 與出生點相同），
    和 v2 的 make_marine / make_tank 行為一致。
    """
    if team == 0:
        dest = (SCREEN_W - 160, spawn_pos[1])
    else:
        dest  = (160, spawn_pos[1])

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


# ── HUD 繪製 ──────────────────────────────────────────────────────────────────
def draw_economy_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    res: ResourceManager,
    queue: ProductionQueue,
    income_flash: bool,
) -> None:
    """左上角：礦石 / 收入 / 佇列面板。"""
    panel_w, panel_h = 260, 120
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 150))
    screen.blit(panel, (8, 8))

    y = 14
    # ── 礦石 ──
    mineral_col = COLOR_GOLD if income_flash else COLOR_MINERAL
    screen.blit(
        font.render(f"💎 礦石: {res.minerals}", True, mineral_col),
        (14, y)
    )
    y += 18

    # ── 收入資訊 ──
    screen.blit(
        font.render(
            f"收入: +{res.income_per_cycle}/週期  ({res.frames_to_next_cycle}幀後)",
            True, COLOR_TEXT,
        ),
        (14, y),
    )
    y += 14

    # 收入進度條
    bar_w = 240
    prog = res.cycle_progress
    pygame.draw.rect(screen, (40, 40, 60),   (14, y, bar_w, 6))
    pygame.draw.rect(screen, COLOR_GOLD,     (14, y, int(bar_w * prog), 6))
    pygame.draw.rect(screen, (120, 100, 40), (14, y, bar_w, 6), 1)
    y += 12

    # ── 生產佇列 ──
    screen.blit(font.render("── 生產佇列 ──", True, COLOR_QUEUE), (14, y))
    y += 16

    if queue.is_busy:
        unit_name = queue.current_unit or "?"
        remain    = queue.frames_remaining
        prog_q    = queue.current_progress
        screen.blit(
            font.render(
                f"▶ {unit_name.upper()}  剩餘 {remain} 幀 ({queue.queue_len} 個排隊)",
                True, COLOR_OK,
            ),
            (14, y),
        )
        y += 14
        pygame.draw.rect(screen, (30, 60, 30),   (14, y, bar_w, 7))
        pygame.draw.rect(screen, COLOR_OK,       (14, y, int(bar_w * prog_q), 7))
        pygame.draw.rect(screen, (60, 120, 60),  (14, y, bar_w, 7), 1)
        y += 10
        # 佇列縮圖列
        icons = queue.queue_summary()
        for idx, kind in enumerate(icons):
            label = "M" if kind == "marine" else "T"
            col   = (80, 160, 255) if kind == "marine" else (80, 220, 80)
            pygame.draw.rect(screen, col, (14 + idx * 22, y, 18, 18))
            screen.blit(font.render(label, True, (0, 0, 0)), (18 + idx * 22, y + 2))
    else:
        screen.blit(font.render("閒置 — 按 B/T 生產單位", True, (140, 140, 180)), (14, y))


def draw_hotkey_bar(
    screen: pygame.Surface,
    font: pygame.font.Font,
    res: ResourceManager,
    debug: bool,
) -> None:
    """底部熱鍵說明欄。"""
    marine_cost = UNIT_COSTS["marine"]
    tank_cost   = UNIT_COSTS["tank"]
    can_marine  = res.minerals >= marine_cost
    can_tank    = res.minerals >= tank_cost

    marine_col = COLOR_OK if can_marine else COLOR_WARN
    tank_col   = COLOR_OK if can_tank   else COLOR_WARN

    parts = [
        (f"[B] Marine {marine_cost}💎", marine_col),
        ("  ", COLOR_TEXT),
        (f"[T] Tank {tank_cost}💎", tank_col),
        ("  |  ", COLOR_TEXT),
        ("[D] Debug", COLOR_WARN if debug else COLOR_HOTKEY),
        ("  [R] Reset  [ESC] 離開", COLOR_HOTKEY),
    ]

    x = 10
    y = SCREEN_H - 20
    for text, color in parts:
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))
        x += surf.get_width()


def draw_unit_cards(
    screen: pygame.Surface,
    font: pygame.font.Font,
    units: list[Unit],
    respawn_timer: dict,
) -> None:
    """右側單位狀態卡片（敵方 + 玩家所有存活單位）。"""
    # 只顯示最多 6 個（上下各 3）
    team0 = [u for u in units if u.team == 0][:3]
    team1 = [u for u in units if u.team == 1][:3]

    for group, x_base in [(team0, 10), (team1, SCREEN_W - 220)]:
        for i, u in enumerate(group):
            y_base = 140 + i * 60
            card = pygame.Surface((210, 52), pygame.SRCALPHA)
            card.fill((0, 0, 0, 130))
            screen.blit(card, (x_base, y_base))

            state_sym = {"march": "🚶", "combat": "⚔", "dead": "💀"}.get(u.state, u.state)
            team_name = ["[玩家]", "[敵方]"][u.team]
            name_col  = COLOR_OK if u.team == 0 else COLOR_WARN
            screen.blit(
                font.render(f"{team_name} {u.kind.upper()} {state_sym}", True, name_col),
                (x_base + 6, y_base + 4),
            )

            bar_w, bar_h = 196, 10
            ratio = max(0.0, u.hp / u.max_hp) if not u.is_dead else 0.0
            bar_color = (
                (0, 200, 80)  if ratio > 0.5  else
                (220, 180, 0) if ratio > 0.25 else
                (220, 50, 50)
            )
            pygame.draw.rect(screen, (80, 0, 0),    (x_base + 6, y_base + 26, bar_w, bar_h))
            pygame.draw.rect(screen, bar_color,     (x_base + 6, y_base + 26, int(bar_w * ratio), bar_h))
            pygame.draw.rect(screen, (160, 160, 160),(x_base + 6, y_base + 26, bar_w, bar_h), 1)
            screen.blit(
                font.render(f"HP {u.hp}/{u.max_hp}", True, COLOR_TEXT),
                (x_base + 6, y_base + 38),
            )


# ── GameLoop ──────────────────────────────────────────────────────────────────
class GameLoop:

    def __init__(self) -> None:
        pygame.init()
        self.screen  = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.font    = pygame.font.Font(None, 18)
        self.fps_clk = pygame.time.Clock()

        # ── 素材 ──────────────────────────────────────────────────────────────
        self.manager = AssetManager()
        print("\n📦 預載素材...")
        self.manager.preload_all()
        print("✅ 預載完成\n")

        # ── VFX 回調 ──────────────────────────────────────────────────────────
        self.vfx_list: list[VFXSprite] = []

        def spawn_vfx(pos: tuple[float, float]) -> None:
            self.vfx_list.append(
                VFXSprite("explosion_sheet", self.manager, pos, frame_delay=3)
            )

        self.spawn_vfx = spawn_vfx

        # ── 經濟系統 ──────────────────────────────────────────────────────────
        self.resource_mgr = ResourceManager(starting=100)

        # ── 玩家建築 ──────────────────────────────────────────────────────────
        # Barracks（左中）→ 生產佇列
        self.player_barracks = Building(
            "barracks", self.manager,
            pos=(80, SCREEN_H // 2), team=0,
        )
        barracks_queue = ProductionQueue(
            spawn_pos=self.player_barracks.spawn_point
        )
        self.player_barracks.queue = barracks_queue

        # Refinery（左上方）→ 收入加成
        self.player_refinery = Building(
            "refinery", self.manager,
            pos=(80, SCREEN_H // 2 - 120), team=0,
        )
        self.resource_mgr.register_refinery()   # 預設場景中有一座煉油廠

        # ── 敵方建築（AI 未來擴充，目前靜態）────────────────────────────────
        self.enemy_barracks = Building(
            "barracks", self.manager,
            pos=(SCREEN_W - 80, SCREEN_H // 2), team=1,
        )
        self.enemy_refinery = Building(
            "refinery", self.manager,
            pos=(SCREEN_W - 80, SCREEN_H // 2 - 120), team=1,
        )

        # ── 單位列表 + 初始敵方單位 ───────────────────────────────────────────
        self.units: list[Unit] = [
            make_unit("tank", self.manager,
                      self.enemy_barracks.spawn_point, team=1),
        ]

        # ── 敵方 AI 重生計時器（舊機制，僅用於敵方）────────────────────────
        self.ai_respawn_timer: dict[str, int] = {}

        # ── UI 狀態 ───────────────────────────────────────────────────────────
        self.debug_mode   = False
        self.income_flash = 0   # 收入閃爍幀數計數

    # ── 便利屬性 ──────────────────────────────────────────────────────────────
    @property
    def barracks_queue(self) -> ProductionQueue:
        return self.player_barracks.queue  # type: ignore[return-value]

    # ── 場景重置 ──────────────────────────────────────────────────────────────
    def reset_scene(self) -> None:
        self.units = [
            make_unit("tank", self.manager,
                      self.enemy_barracks.spawn_point, team=1),
        ]
        self.vfx_list.clear()
        self.ai_respawn_timer.clear()
        # 重置佇列（但不重置礦石）
        self.player_barracks.queue = ProductionQueue(
            spawn_pos=self.player_barracks.spawn_point
        )
        print("[GameLoop] 🔄 場景已重置")

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
                    elif event.key == pygame.K_r:
                        self.reset_scene()
                    elif event.key == pygame.K_b:
                        # 生產 Marine
                        ok = self.player_barracks.produce("marine", self.resource_mgr)
                        if not ok:
                            print(f"[Input] ⚠️  Marine 生產失敗 (礦石={self.resource_mgr.minerals})")
                    elif event.key == pygame.K_t:
                        # 生產 Tank
                        ok = self.player_barracks.produce("tank", self.resource_mgr)
                        if not ok:
                            print(f"[Input] ⚠️  Tank 生產失敗 (礦石={self.resource_mgr.minerals})")

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.spawn_vfx(pygame.mouse.get_pos())

            # ── 更新 ──────────────────────────────────────────────────────────

            # 1) 收入週期
            if self.resource_mgr.update():
                self.income_flash = 30   # 閃爍 30 幀
            if self.income_flash > 0:
                self.income_flash -= 1

            # 2) 生產佇列 → 若完成則生成新單位
            finished_unit = self.barracks_queue.update()
            if finished_unit:
                spawn_pos = self.player_barracks.spawn_point
                new_unit  = make_unit(finished_unit, self.manager, spawn_pos, team=0)
                self.units.append(new_unit)
                print(f"[GameLoop] 🔵 玩家 {finished_unit} 出兵於 {spawn_pos}")

            # 3) 戰鬥邏輯
            BattleManager.process_combat(self.units, self.spawn_vfx)

            # 4) 碰撞分離
            BattleManager.resolve_collisions(self.units)

            # 5) 敵方 AI 重生（舊機制保留，確保場面不空）
            for u in self.units:
                if u.is_dead and u.team == 1 and u.kind not in self.ai_respawn_timer:
                    self.ai_respawn_timer[u.kind] = 0

            for kind in list(self.ai_respawn_timer.keys()):
                self.ai_respawn_timer[kind] += 1
                if self.ai_respawn_timer[kind] >= AI_RESPAWN_DELAY:
                    del self.ai_respawn_timer[kind]
                    new_enemy = make_unit(kind, self.manager,
                                          self.enemy_barracks.spawn_point, team=1)
                    self.units.append(new_enemy)
                    print(f"[AI] 🔴 敵方 {kind} 重生")

            # 6) 死亡清理
            self.units = BattleManager.cleanup_dead(self.units)

            # 7) VFX 更新
            self.vfx_list = BattleManager.update_vfx(self.vfx_list)

            # ── 渲染 ──────────────────────────────────────────────────────────
            draw_background(self.screen)

            # 建築
            for bld in [
                self.player_barracks, self.player_refinery,
                self.enemy_barracks,  self.enemy_refinery,
            ]:
                bld.draw(self.screen)

            # 單位
            for u in self.units:
                u.draw(self.screen)
                if self.debug_mode:
                    u.draw_debug(self.screen)

            # VFX
            for vfx in self.vfx_list:
                vfx.draw(self.screen)

            # HUD
            draw_economy_panel(
                self.screen, self.font,
                self.resource_mgr, self.barracks_queue,
                income_flash=self.income_flash > 0,
            )
            draw_unit_cards(
                self.screen, self.font,
                self.units, self.ai_respawn_timer,
            )
            draw_hotkey_bar(
                self.screen, self.font,
                self.resource_mgr, self.debug_mode,
            )

            # FPS（右上角）
            self.screen.blit(
                self.font.render(f"FPS: {fps:.0f}", True, COLOR_TEXT),
                (SCREEN_W - 70, 10),
            )

            pygame.display.flip()

        pygame.quit()
        sys.exit()


# ── 入口 ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    GameLoop().run()
