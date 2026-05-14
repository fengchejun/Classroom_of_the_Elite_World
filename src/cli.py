"""
实教AI模拟器 - CLI交互界面

命令行方式启动游戏，支持文本输入和选项选择。
用法: py -m src.cli [--session SESSION_SLUG]
"""

from __future__ import annotations

import asyncio
import json
import sys
import io
from pathlib import Path

# Fix Windows GBK encoding for emoji support
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---- Standalone Game State (works without database) ----

TIME_SLOTS = ["morning", "noon", "dusk", "evening", "late_night"]
TIME_DISPLAY = {
    "morning": "上午", "noon": "中午", "dusk": "傍晚",
    "evening": "晚上", "late_night": "深夜",
}

LOCATIONS = {
    "classroom_d": {
        "name": "D班教室",
        "desc": "一年D班的教室。桌椅有些陈旧，靠窗的后排能看到中庭。",
        "connected": ["hallway_1f", "corridor_d"],
    },
    "hallway_1f": {
        "name": "一楼走廊",
        "desc": "教学楼一楼的走廊，墙上贴着社团海报和通知。",
        "connected": ["classroom_d", "cafeteria", "school_gymnasium", "school_gate", "hallway_3f"],
    },
    "hallway_3f": {
        "name": "三楼走廊",
        "desc": "比一楼安静得多，偶有小团体在此密谈。",
        "connected": ["hallway_1f", "library"],
    },
    "library": {
        "name": "图书馆",
        "desc": "藏书丰富的图书馆，靠窗的自习区总是座无虚席。",
        "connected": ["hallway_3f"],
    },
    "cafeteria": {
        "name": "学生食堂",
        "desc": "宽敞的学生食堂，可以用个人点数购买各种套餐。",
        "connected": ["hallway_1f", "school_field"],
    },
    "school_gymnasium": {
        "name": "体育馆",
        "desc": "宽敞的室内体育馆，配备了可移动舞台。",
        "connected": ["hallway_1f", "school_field"],
    },
    "school_field": {
        "name": "操场",
        "desc": "标准的田径运动场，足球部和田径部在这里训练。",
        "connected": ["school_gymnasium", "cafeteria"],
    },
    "rooftop": {
        "name": "天台",
        "desc": "教学楼顶层的天台，视野开阔。门通常是锁的。",
        "connected": ["hallway_5f"],
    },
    "hallway_5f": {
        "name": "五楼走廊",
        "desc": "教学楼顶层，通往天台。人迹罕至。",
        "connected": ["hallway_1f", "rooftop"],
    },
    "dormitory": {
        "name": "学生宿舍",
        "desc": "你的单人宿舍。虽然不大，但干净整洁。",
        "connected": ["school_gate"],
    },
    "school_gate": {
        "name": "校门",
        "desc": "高度育成高中的正门，有保安值守。",
        "connected": ["dormitory", "hallway_1f", "school_bus"],
    },
    "school_bus": {
        "name": "校车",
        "desc": "往返学校和市区的班车。",
        "connected": ["school_gate"],
    },
    "special_building": {
        "name": "特别教学楼",
        "desc": "校园深处独立的建筑，平时大门紧闭。",
        "connected": ["school_field"],
    },
}


class CLIGameState:
    """In-memory game state for CLI testing (no DB required)."""

    def __init__(self, session_slug: str = "cli_session"):
        self.session_slug = session_slug
        self.game_date = "2024-04-01"
        self.time_slot = "morning"
        self.player_name = "绫小路清隆"
        self.location_id = "classroom_d"
        self.class_points = 0
        self.private_points = 100000
        self.dialogue_count = 0
        self.story_summaries: list[str] = []

    def advance_time(self, slots: int = 1) -> str:
        idx = TIME_SLOTS.index(self.time_slot)
        new_idx = idx + slots
        days = new_idx // len(TIME_SLOTS)
        remainder = new_idx % len(TIME_SLOTS)
        if days > 0:
            from datetime import datetime, timedelta
            dt = datetime.strptime(self.game_date, "%Y-%m-%d") + timedelta(days=days)
            self.game_date = dt.strftime("%Y-%m-%d")
        self.time_slot = TIME_SLOTS[remainder]
        return f"{self.game_date} {TIME_DISPLAY[self.time_slot]}"

    def move_to(self, location_id: str) -> str | None:
        current = LOCATIONS.get(self.location_id, {})
        connected = current.get("connected", [])
        if location_id in connected or location_id == self.location_id:
            self.location_id = location_id
            return LOCATIONS[location_id]["name"]
        return None

    def to_dict(self) -> dict:
        return {
            "session_slug": self.session_slug,
            "game_date": self.game_date,
            "time_slot": self.time_slot,
            "time_display": TIME_DISPLAY.get(self.time_slot, self.time_slot),
            "player_name": self.player_name,
            "location_id": self.location_id,
            "location_name": LOCATIONS.get(self.location_id, {}).get("name", "未知"),
            "class_points": self.class_points,
            "private_points": self.private_points,
        }


class CLIGame:
    """Interactive CLI game loop."""

    def __init__(self, session_slug: str = "cli_session"):
        self.state = CLIGameState(session_slug)

    def run(self):
        """Main CLI loop."""
        self._print_banner()
        self._print_help()

        while True:
            try:
                self._print_status()
                cmd = input("\n> ").strip()
                if not cmd:
                    continue

                if cmd.lower() in ("/quit", "/exit", "/q"):
                    print("\n再见。下次继续。")
                    break
                elif cmd.lower() in ("/help", "/h"):
                    self._print_help()
                elif cmd.lower() == "/status":
                    self._print_detailed_status()
                elif cmd.lower() == "/locations":
                    self._print_locations()
                elif cmd.startswith("/go "):
                    loc = cmd[4:].strip()
                    self._handle_move(loc)
                elif cmd.startswith("/wait"):
                    parts = cmd.split()
                    slots = int(parts[1]) if len(parts) > 1 else 1
                    self._handle_wait(slots)
                elif cmd.startswith("/rest"):
                    self._handle_wait(1)  # rest = wait 1 slot
                elif cmd.startswith("/sleep"):
                    # Sleep until morning
                    self._handle_sleep()
                else:
                    self._handle_text_input(cmd)

            except KeyboardInterrupt:
                print("\n\n再见。下次继续。")
                break
            except EOFError:
                break

    def _handle_move(self, location_id: str):
        # Try exact match
        result = self.state.move_to(location_id)
        if result:
            print(f"\n你前往了【{result}】。")
            return

        # Try fuzzy match
        for lid, loc in LOCATIONS.items():
            if location_id in lid or location_id in loc["name"]:
                result = self.state.move_to(lid)
                if result:
                    print(f"\n你前往了【{result}】。")
                    return

        print(f"\n无法前往'{location_id}'。输入 /locations 查看可前往的地点。")

    def _handle_wait(self, slots: int):
        time_str = self.state.advance_time(slots)
        print(f"\n你等了一会儿... 现在是【{time_str}】。")

    def _handle_sleep(self):
        current_idx = TIME_SLOTS.index(self.state.time_slot)
        if current_idx == 0:  # Already morning
            self.state.advance_time(len(TIME_SLOTS))  # Next day morning
        else:
            slots_until_morning = len(TIME_SLOTS) - current_idx
            self.state.advance_time(slots_until_morning)
        print(f"\n你睡了一觉。醒来时已是【{self.state.game_date} {TIME_DISPLAY['morning']}】。")

    def _handle_text_input(self, text: str):
        """Simulate an LLM response (offline mode)."""
        print(f"\n[系统] 在完整模式下，你的输入 '{text}' 将被发送到LLM进行处理。")
        print("[系统] 当前为离线测试模式。请确保配置了ANTHROPIC_API_KEY以启用完整功能。")
        print(f"[系统] 地点: {LOCATIONS[self.state.location_id]['name']}")

    def _print_banner(self):
        print("=" * 60)
        print("  《实力至上主义的教室》混合驱动AI互动引擎")
        print("  Classroom of the Elite - AI Interactive Engine")
        print("  v0.1.0 (CLI 测试模式)")
        print("=" * 60)

    def _print_help(self):
        print("""
┌──────────────────────────────────────────────────────────┐
│ 命令列表:                                                 │
│   /go <地点>    移动到指定地点  (/go hallway_1f)         │
│   /wait [N]     等待N个时间段  (/wait 1)                 │
│   /rest         休息一个时间段                           │
│   /sleep        睡到第二天早上                           │
│   /status       查看详细状态                             │
│   /locations    查看可到达的地点                         │
│   /help         显示此帮助                               │
│   /quit         退出游戏                                 │
│                                                          │
│  直接输入文本进行自由行动 (需要LLM API)                    │
└──────────────────────────────────────────────────────────┘
        """)

    def _print_status(self):
        loc = LOCATIONS.get(self.state.location_id, {})
        conn_str = ", ".join(loc.get("connected", []))
        print(f"\n{'─' * 50}")
        print(f"📍 {self.state.game_date} {TIME_DISPLAY[self.state.time_slot]} | {loc.get('name', '?')}")
        print(f"💰 私人点数: {self.state.private_points:,}")
        print(f"🚪 可前往: {conn_str}")

    def _print_detailed_status(self):
        s = self.state.to_dict()
        print("\n══════════ 角色状态 ══════════")
        print(f"  角色: {s['player_name']}")
        print(f"  日期: {s['game_date']}")
        print(f"  时段: {s['time_display']}")
        print(f"  位置: {s['location_name']} ({s['location_id']})")
        print(f"  班级点数: {s['class_points']}")
        print(f"  私人点数: {s['private_points']:,}")
        print("═══════════════════════════════")

    def _print_locations(self):
        current = self.state.location_id
        conn = LOCATIONS.get(current, {}).get("connected", [])
        print("\n⭐ 可前往的地点:")
        for lid in conn:
            loc = LOCATIONS.get(lid, {})
            print(f"  {lid:20s} → {loc.get('name', '?')}")
        print("\n💡 提示: 使用 /go <地点ID> 移动")


def main():
    session = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--session" else "cli_default"

    try:
        import argparse
        parser = argparse.ArgumentParser(description="实教AI模拟器 CLI")
        parser.add_argument("--session", default="cli_default", help="Session slug")
        args = parser.parse_args()
        session = args.session
    except Exception:
        pass

    game = CLIGame(session)
    game.run()


if __name__ == "__main__":
    main()
