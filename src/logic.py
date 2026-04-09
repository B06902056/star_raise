"""
logic.py — Star Raise Game  (v4: AI Controller)
ResourceManager : 礦石收入、消費、週期計時
ProductionQueue : 建築生產佇列（一次只跑一個 job）
AIController    : 敵方 AI 決策（每 10 秒評估一次）

數值設計
--------
起始礦石:   100
基礎收入:   +10 / 週期
Refinery:  +15 / 週期（可疊加）
週期長度:   300 幀 = 5 秒 @ 60fps

Marine:  成本 50，建造 180 幀 (3s)
Tank:    成本 150，建造 300 幀 (5s)
"""

from __future__ import annotations
import random
from typing import Optional

# ── 全域數值表（單一修改來源）────────────────────────────────────────────────────
INCOME_CYCLE_FRAMES: int = 300        # 5 秒 @ 60fps
BASE_INCOME:         int = 10         # 基礎被動收入
REFINERY_BONUS:      int = 15         # 每座煉油廠額外收入

UNIT_COSTS: dict[str, int] = {
    "marine": 50,
    "tank":   150,
}

UNIT_BUILD_FRAMES: dict[str, int] = {
    "marine": 180,   # 3 秒
    "tank":   300,   # 5 秒
}

STARTING_MINERALS: int = 100


# ── ResourceManager ───────────────────────────────────────────────────────────
class ResourceManager:
    """
    管理玩家礦石的收支與被動收入週期。

    使用方式
    --------
    rm = ResourceManager()
    rm.register_refinery()          # 建造煉油廠時呼叫
    cycle_fired = rm.update()       # 每幀呼叫，True 表示本幀發放收入
    ok = rm.spend(50)               # 消費礦石，不足回傳 False
    """

    def __init__(self, starting: int = STARTING_MINERALS) -> None:
        self.minerals:     int = starting
        self._cycle_timer: int = 0
        self._refinery_count: int = 0   # 已註冊的煉油廠數量

    # ── 煉油廠管理 ────────────────────────────────────────────────────────────
    def register_refinery(self) -> None:
        """玩家建造或恢復一座 Refinery 時呼叫。"""
        self._refinery_count += 1
        print(f"[Economy] ⛏  Refinery 已註冊 (共 {self._refinery_count} 座，"
              f"收入={self.income_per_cycle}/週期)")

    def unregister_refinery(self) -> None:
        """Refinery 被摧毀時呼叫。"""
        self._refinery_count = max(0, self._refinery_count - 1)
        print(f"[Economy] 💥 Refinery 減少 (共 {self._refinery_count} 座)")

    # ── 屬性 ──────────────────────────────────────────────────────────────────
    @property
    def income_per_cycle(self) -> int:
        """本週期總收入 = 基礎 + 每座煉油廠加成。"""
        return BASE_INCOME + self._refinery_count * REFINERY_BONUS

    @property
    def cycle_progress(self) -> float:
        """當前週期進度 0.0 ~ 1.0（用於 UI 進度條）。"""
        return self._cycle_timer / INCOME_CYCLE_FRAMES

    @property
    def frames_to_next_cycle(self) -> int:
        return INCOME_CYCLE_FRAMES - self._cycle_timer

    # ── 每幀更新 ──────────────────────────────────────────────────────────────
    def update(self) -> bool:
        """
        推進收入計時器。
        回傳 True 表示本幀觸發了一次收入週期（用於 UI 閃爍提示）。
        """
        self._cycle_timer += 1
        if self._cycle_timer >= INCOME_CYCLE_FRAMES:
            self._cycle_timer = 0
            self.minerals += self.income_per_cycle
            print(f"[Economy] 💰 收入 +{self.income_per_cycle}  →  礦石: {self.minerals}")
            return True
        return False

    # ── 消費 ──────────────────────────────────────────────────────────────────
    def spend(self, amount: int) -> bool:
        """
        嘗試消費礦石。
        成功回傳 True 並扣款，不足回傳 False 且不扣款。
        """
        if self.minerals >= amount:
            self.minerals -= amount
            return True
        return False

    def can_afford(self, unit_type: str) -> bool:
        return self.minerals >= UNIT_COSTS.get(unit_type, 9999)

    # ── 除錯資訊 ──────────────────────────────────────────────────────────────
    def __repr__(self) -> str:
        return (
            f"ResourceManager(minerals={self.minerals}, "
            f"income={self.income_per_cycle}/cycle, "
            f"refineries={self._refinery_count})"
        )


# ── ProductionQueue ───────────────────────────────────────────────────────────
class ProductionQueue:
    """
    建築生產佇列。一次只建造一個單位（FIFO 佇列）。
    完成後由 GameLoop 取得 unit_type 並生成 Unit 物件。

    Parameters
    ----------
    spawn_pos : 生產完成後單位出現的世界座標
    max_queue : 最大排隊數量（防止無限堆積）

    典型呼叫
    --------
    queue = ProductionQueue(spawn_pos=(160, 384))
    queue.enqueue("marine", resource_manager)  # B 鍵觸發
    finished = queue.update()                  # 每幀呼叫，有完成時回傳 unit_type
    """

    MAX_QUEUE: int = 5   # 最多排 5 個

    def __init__(self, spawn_pos: tuple[float, float]) -> None:
        self.spawn_pos = list(spawn_pos)
        self._queue: list[dict] = []   # [{unit_type, timer, build_time}]

    # ── 入隊 ──────────────────────────────────────────────────────────────────
    def enqueue(self, unit_type: str, resource_mgr: ResourceManager) -> bool:
        """
        將生產任務加入佇列並扣除礦石。
        佇列已滿或礦石不足時回傳 False。
        """
        if len(self._queue) >= self.MAX_QUEUE:
            print(f"[Queue] ⚠️  佇列已滿 ({self.MAX_QUEUE} 個)，無法加入 {unit_type}")
            return False

        cost = UNIT_COSTS.get(unit_type, 9999)
        if not resource_mgr.spend(cost):
            print(f"[Queue] ❌ 礦石不足: 需要 {cost}，現有 {resource_mgr.minerals}")
            return False

        build_time = UNIT_BUILD_FRAMES.get(unit_type, 180)
        self._queue.append({
            "unit_type":  unit_type,
            "timer":      0,
            "build_time": build_time,
        })
        print(f"[Queue] ➕ {unit_type} 入隊 (費用={cost}，建造={build_time}幀) "
              f"[佇列長度={len(self._queue)}]")
        return True

    # ── 每幀更新 ──────────────────────────────────────────────────────────────
    def update(self) -> Optional[str]:
        """
        推進生產計時器。
        若當前任務完成，從佇列移除並回傳 unit_type；否則回傳 None。
        """
        if not self._queue:
            return None

        job = self._queue[0]
        job["timer"] += 1
        if job["timer"] >= job["build_time"]:
            self._queue.pop(0)
            print(f"[Queue] ✅ 生產完成: {job['unit_type']}  (佇列剩餘={len(self._queue)})")
            return job["unit_type"]
        return None

    # ── 狀態屬性 ──────────────────────────────────────────────────────────────
    @property
    def is_busy(self) -> bool:
        return bool(self._queue)

    @property
    def queue_len(self) -> int:
        return len(self._queue)

    @property
    def current_unit(self) -> Optional[str]:
        """正在建造的單位種類，若空閒則 None。"""
        return self._queue[0]["unit_type"] if self._queue else None

    @property
    def current_progress(self) -> float:
        """當前任務進度 0.0 ~ 1.0（用於 UI 進度條）。"""
        if not self._queue:
            return 0.0
        j = self._queue[0]
        return j["timer"] / j["build_time"]

    @property
    def frames_remaining(self) -> int:
        """當前任務剩餘幀數。"""
        if not self._queue:
            return 0
        j = self._queue[0]
        return j["build_time"] - j["timer"]

    def queue_summary(self) -> list[str]:
        """回傳佇列中所有 unit_type 的列表（供 UI 顯示）。"""
        return [j["unit_type"] for j in self._queue]


# ── AIController ──────────────────────────────────────────────────────────────
# 決策週期
AI_DECISION_FRAMES: int = 600   # 10 秒 @ 60fps

class AIController:
    """
    敵方 AI 決策模組。每 600 幀（10 秒）評估一次，
    根據礦石餘額決定生產哪種單位並加入 ProductionQueue。

    決策規則
    --------
    minerals >= 150 → 40% 機率生產 Tank，60% 機率生產 Marine
    50 <= minerals < 150 → 生產 Marine
    minerals < 50  → 本輪跳過

    設計原則
    --------
    - AI 使用與玩家相同的 ResourceManager / ProductionQueue API，保證公平性
    - 隨機性透過 random.random() 實現，可在初始化時設定 seed 以利測試
    - update() 同時驅動收入週期 + 佇列進度 + 決策計時，
      GameLoop 只需每幀呼叫一次 update()

    使用方式
    --------
    ai = AIController(resource_mgr, queue, spawn_pos)
    finished = ai.update()   # 每幀呼叫；有單位完成時回傳 unit_type
    """

    def __init__(
        self,
        resource_mgr: ResourceManager,
        queue: ProductionQueue,
        *,
        decision_frames: int = AI_DECISION_FRAMES,
        seed: Optional[int] = None,
    ) -> None:
        self.resource_mgr    = resource_mgr
        self.queue           = queue
        self.decision_frames = decision_frames
        self._timer: int     = 0
        self._rng            = random.Random(seed)   # 獨立隨機器，不汙染全局狀態

        # 統計（供 API / HUD 顯示）
        self.total_spawned:  int = 0
        self.last_decision:  str = "idle"

    # ── 每幀更新（主入口）────────────────────────────────────────────────────
    def update(self) -> Optional[str]:
        """
        每幀呼叫。流程：
        1. ResourceManager 收入週期
        2. ProductionQueue 建造進度
        3. 決策計時 → 觸發 _decide()

        回傳值：有單位完成生產時回傳 unit_type 字串，否則 None。
        """
        # 1) 被動收入
        self.resource_mgr.update()

        # 2) 佇列推進
        finished = self.queue.update()
        if finished:
            self.total_spawned += 1

        # 3) 決策計時
        self._timer += 1
        if self._timer >= self.decision_frames:
            self._timer = 0
            self._decide()

        return finished

    # ── 決策邏輯 ──────────────────────────────────────────────────────────────
    def _decide(self) -> None:
        """
        核心決策：依礦石餘額與隨機權重選擇生產目標。

        分支邏輯
        --------
        minerals >= 150:
            roll = random()
            roll < 0.40  → enqueue "tank"   (40%)
            roll >= 0.40 → enqueue "marine" (60%)
        50 <= minerals < 150:
            enqueue "marine"
        minerals < 50:
            跳過（資源不足）
        """
        minerals = self.resource_mgr.minerals

        if minerals >= UNIT_COSTS["tank"]:
            roll = self._rng.random()
            if roll < 0.40:
                chosen = "tank"
            else:
                chosen = "marine"
        elif minerals >= UNIT_COSTS["marine"]:
            chosen = "marine"
        else:
            self.last_decision = f"skip (minerals={minerals})"
            print(f"[AI] ⏸  礦石不足 ({minerals})，跳過本輪")
            return

        ok = self.queue.enqueue(chosen, self.resource_mgr)
        self.last_decision = f"{chosen} ({'ok' if ok else 'queue_full'})"
        print(f"[AI] 🤖 決策: {chosen}  roll={self._rng.random():.2f}  "
              f"minerals={minerals}  result={self.last_decision}")

    # ── 狀態摘要 ──────────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "minerals":       self.resource_mgr.minerals,
            "income":         self.resource_mgr.income_per_cycle,
            "queue_len":      self.queue.queue_len,
            "current_unit":   self.queue.current_unit,
            "last_decision":  self.last_decision,
            "total_spawned":  self.total_spawned,
            "next_decision":  self.decision_frames - self._timer,
        }
