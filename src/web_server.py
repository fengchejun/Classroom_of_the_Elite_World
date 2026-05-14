"""
实教AI模拟器 - Web前端服务器 (SQLite版)

启动: py -m src.web_server
然后打开 http://localhost:8000
"""

from __future__ import annotations

import io
import json
import sys

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timedelta

import httpx

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, delete

from src.config.settings import settings
from src.core.time_engine.clock import TIME_SLOTS
from src.db import async_session, init_db
from src.models.dialogue import DialogueLog, StorySummary
from src.models.game_session import GameSession

# ---- Constants ----

TIME_DISPLAY = {
    "morning": "上午", "noon": "中午", "dusk": "傍晚",
    "evening": "晚上", "late_night": "深夜",
}

LOCATIONS = {
    "classroom_d": {
        "location_id": "classroom_d", "name": "D班教室",
        "description": "一年D班的教室。桌椅有些陈旧，靠窗的后排能看到中庭。教室里弥漫着慵懒散漫的氛围——有人趴着睡觉，有人旁若无人地聊天。",
        "tags": ["indoor", "classroom"],
        "connected_to": ["hallway_1f"],
        "zone_id": "teaching_building",
    },
    "hallway_1f": {
        "location_id": "hallway_1f", "name": "一楼走廊",
        "description": "教学楼一楼的走廊，连接着各个教室和办公室。墙上贴着社团海报和通知。学生们来来往往。",
        "tags": ["indoor", "corridor"],
        "connected_to": ["classroom_d", "cafeteria", "school_gymnasium", "hallway_3f", "school_gate"],
        "zone_id": "teaching_building",
    },
    "hallway_3f": {
        "location_id": "hallway_3f", "name": "三楼走廊",
        "description": "比一楼安静得多。图书馆在这层，偶尔有小团体在角落密谈。",
        "tags": ["indoor", "corridor", "quiet"],
        "connected_to": ["hallway_1f", "library"],
        "zone_id": "teaching_building",
    },
    "library": {
        "location_id": "library", "name": "图书馆",
        "description": "藏书丰富的图书馆，靠窗的自习区总是座无虚席。空气里弥漫着书页的味道。",
        "tags": ["indoor", "quiet"],
        "connected_to": ["hallway_3f"],
        "zone_id": "teaching_building",
    },
    "cafeteria": {
        "location_id": "cafeteria", "name": "学生食堂",
        "description": "宽敞的食堂，可以用个人点数购买各种套餐。午餐时间总是人满为患。",
        "tags": ["indoor", "noisy"],
        "connected_to": ["hallway_1f", "school_field"],
        "zone_id": "living_area",
    },
    "school_gymnasium": {
        "location_id": "school_gymnasium", "name": "体育馆",
        "description": "宽敞的室内体育馆，配备了可移动舞台。可容纳全校学生。",
        "tags": ["indoor", "large"],
        "connected_to": ["hallway_1f", "school_field"],
        "zone_id": "sports_area",
    },
    "school_field": {
        "location_id": "school_field", "name": "操场",
        "description": "标准的田径运动场，足球部和田径部在这里训练。跑道边有几个学生在慢跑。",
        "tags": ["outdoor", "sports"],
        "connected_to": ["school_gymnasium", "cafeteria", "special_building"],
        "zone_id": "sports_area",
    },
    "rooftop": {
        "location_id": "rooftop", "name": "天台",
        "description": "教学楼顶层的天台。视野开阔，能俯瞰整个校园。门通常是锁的，但今天似乎被谁打开了。",
        "tags": ["outdoor", "secluded"],
        "connected_to": ["hallway_5f"],
        "zone_id": "teaching_building",
    },
    "hallway_5f": {
        "location_id": "hallway_5f", "name": "五楼走廊",
        "description": "教学楼顶层的走廊，人迹罕至。通往天台的门就在走廊尽头。",
        "tags": ["indoor", "corridor", "secluded"],
        "connected_to": ["hallway_1f", "rooftop"],
        "zone_id": "teaching_building",
    },
    "dormitory": {
        "location_id": "dormitory", "name": "学生宿舍",
        "description": "你的单人宿舍。虽然不大，但设施齐全。这里是你在这个学校里唯一的私人空间。",
        "tags": ["indoor", "private"],
        "connected_to": ["school_gate"],
        "zone_id": "living_area",
    },
    "school_gate": {
        "location_id": "school_gate", "name": "校门",
        "description": "高度育成高中的正门，有保安值守。学生出入需要刷学生卡。",
        "tags": ["outdoor"],
        "connected_to": ["dormitory", "hallway_1f", "school_bus"],
        "zone_id": "entrance",
    },
    "school_bus": {
        "location_id": "school_bus", "name": "校车",
        "description": "往返学校和市区的班车。每天早晚各一班，座位常常不够用。",
        "tags": ["indoor", "vehicle"],
        "connected_to": ["school_gate"],
        "zone_id": "entrance",
    },
    "special_building": {
        "location_id": "special_building", "name": "特别教学楼",
        "description": "校园深处独立的建筑。平时大门紧闭，只在进行特别考试时才开放。",
        "tags": ["indoor", "restricted"],
        "connected_to": ["school_field"],
        "zone_id": "special_area",
    },
}

NPC_SCHEDULES = {
    "classroom_d": [
        {"name": "堀北铃音", "brief_status": "独自坐在前排看书", "is_critical": True},
        {"name": "须藤健", "brief_status": "趴在桌上睡觉", "is_critical": False},
    ],
    "hallway_1f": [
        {"name": "栉田桔梗", "brief_status": "微笑着和朋友聊天", "is_critical": True},
    ],
    "cafeteria": [
        {"name": "轻井泽惠", "brief_status": "和几个女生一起吃饭", "is_critical": False},
    ],
    "school_field": [
        {"name": "平田洋介", "brief_status": "在足球场上训练", "is_critical": False},
        {"name": "须藤健", "brief_status": "在篮球场上投篮", "is_critical": False},
    ],
    "library": [
        {"name": "堀北铃音", "brief_status": "专注地看书", "is_critical": True},
    ],
    "rooftop": [
        {"name": "龙园翔", "brief_status": "靠在栏杆上，居高临下地看着校园", "is_critical": True},
    ],
    "hallway_3f": [
        {"name": "石崎大地", "brief_status": "在走廊里徘徊", "is_critical": False},
    ],
}

CHARACTER_LIBRARY = {
    "绫小路清隆": {
        "role_id": "ayanokoji", "class_name": "D",
        "traits": ["冷静", "观察力极强", "隐藏实力", "智谋深沈"],
        "public_info": [
            {"label": "外貌", "content": "普通高中男生外表，棕发，不起眼的表情，总是坐在教室后排靠窗的位置"},
            {"label": "身份", "content": "一年D班学生，入学成绩平平"},
            {"label": "性格", "content": "寡言少语，不引人注目，刻意维持低调形象"},
        ],
    },
    "堀北铃音": {
        "role_id": "horikita", "class_name": "D",
        "traits": ["孤高", "认真", "不擅社交", "目标坚定"],
        "public_info": [
            {"label": "外貌", "content": "黑长直发，容貌端正，总是独自一人坐在前排"},
            {"label": "身份", "content": "一年D班学生，以优异成绩入学却被分配到D班"},
            {"label": "性格", "content": "冷傲孤高，不愿与人来往，目标是升入A班"},
        ],
    },
    "栉田桔梗": {
        "role_id": "kushida", "class_name": "D",
        "traits": ["表里不一", "社交达人", "人脉广泛"],
        "public_info": [
            {"label": "外貌", "content": "棕发，笑容甜美，在校内人气极高"},
            {"label": "身份", "content": "一年D班学生，深受同学信赖"},
            {"label": "性格", "content": "表面温柔善良，乐于助人；隐藏着不为人知的另一面"},
        ],
    },
    "龙园翔": {
        "role_id": "ryuen", "class_name": "C",
        "traits": ["暴力", "狡猾", "支配欲强", "领导力"],
        "public_info": [
            {"label": "外貌", "content": "红发，眼神锐利，体格强健"},
            {"label": "身份", "content": "一年C班的实际支配者"},
            {"label": "性格", "content": "以暴力和恐惧统治C班，为达目的不择手段"},
        ],
    },
    "轻井泽惠": {
        "role_id": "karuizawa", "class_name": "D",
        "traits": ["辣妹系", "女生团体领袖", "隐藏脆弱"],
        "public_info": [
            {"label": "外貌", "content": "染发辣妹风格，在女生中很显眼"},
            {"label": "身份", "content": "一年D班女生团体的中心人物"},
            {"label": "性格", "content": "表面开朗强势，实际上内心有创伤"},
        ],
    },
    "平田洋介": {
        "role_id": "hirata", "class_name": "D",
        "traits": ["正义感", "人望高", "足球部王牌"],
        "public_info": [
            {"label": "外貌", "content": "英俊的运动系男生，足球部成员"},
            {"label": "身份", "content": "一年D班的优等生，足球部王牌"},
            {"label": "性格", "content": "正义感强，深受信赖，想要守护班级"},
        ],
    },
    "须藤健": {
        "role_id": "sudo", "class_name": "D",
        "traits": ["冲动", "篮球天才", "暴躁"],
        "public_info": [
            {"label": "外貌", "content": "身材高大的运动系男生"},
            {"label": "身份", "content": "一年D班学生，篮球部成员"},
            {"label": "性格", "content": "脾气暴躁，容易冲动，但本质不坏"},
        ],
    },
    "一之濑帆波": {
        "role_id": "ichinose", "class_name": "B",
        "traits": ["开朗", "正义", "学生会成员", "天然"],
        "public_info": [
            {"label": "外貌", "content": "活泼开朗的美少女，笑容灿烂"},
            {"label": "身份", "content": "一年B班的核心人物"},
            {"label": "性格", "content": "性格开朗大方，正义感强，但有天然的一面"},
        ],
    },
    "坂柳有栖": {
        "role_id": "sakayanagi", "class_name": "A",
        "traits": ["天才", "毒舌", "体弱", "理事长之女"],
        "public_info": [
            {"label": "外貌", "content": "银发，拄着拐杖，身形娇小"},
            {"label": "身份", "content": "一年A班的领袖，理事长之女"},
            {"label": "性格", "content": "智力超群，言辞犀利，享受与强者较量"},
        ],
    },
    "葛城康平": {
        "role_id": "katsuragi", "class_name": "A",
        "traits": ["稳重", "光头", "防守型策略"],
        "public_info": [
            {"label": "外貌", "content": "光头，体格魁梧，给人一种压迫感"},
            {"label": "身份", "content": "一年A班的核心人物之一"},
            {"label": "性格", "content": "沉稳冷静，采取防守策略维持A班地位"},
        ],
    },
    "伊吹澪": {
        "role_id": "ibuki", "class_name": "C",
        "traits": ["格斗高手", "寡言", "忠诚"],
        "public_info": [
            {"label": "外貌", "content": "蓝色短发，身材纤细但格斗能力极强"},
            {"label": "身份", "content": "一年C班学生，龙园的得力助手"},
            {"label": "性格", "content": "话少，行动力强，对龙园有一定忠诚"},
        ],
    },
    "石崎大地": {
        "role_id": "ishizaki", "class_name": "C",
        "traits": ["混混", "冲动", "龙园手下"],
        "public_info": [
            {"label": "外貌", "content": "不良少年打扮"},
            {"label": "身份", "content": "一年C班学生，龙园的手下"},
            {"label": "性格", "content": "典型的混混，但偶尔也显露人情味"},
        ],
    },
    "椎名日和": {
        "role_id": "shina", "class_name": "D",
        "traits": ["文学少女", "安静", "观察者"],
        "public_info": [
            {"label": "外貌", "content": "戴眼镜的文静女生"},
            {"label": "身份", "content": "一年D班学生"},
            {"label": "性格", "content": "热爱阅读，安静观察周围一切"},
        ],
    },
}

# ---- Tool Definitions & Handlers ----

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_character_info",
            "description": "查询某个角色的详细信息，包括外貌、身份、性格特质、班级等公开资料。当需要深入了解某个NPC、角色在剧情中出现、或玩家与该角色互动时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "char_name": {
                        "type": "string",
                        "description": "要查询的角色名字，如'堀北铃音'、'须藤健'、'龙园翔'等",
                    },
                },
                "required": ["char_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_location_info",
            "description": "查询某个地点的详细信息，包括描述、连接的其他地点等。当玩家移动到新地点或需要了解周围环境时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_id": {
                        "type": "string",
                        "description": "地点ID，如'library'、'cafeteria'、'school_gymnasium'、'rooftop'、'dormitory'等",
                    },
                },
                "required": ["location_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_exam_rules",
            "description": "查阅特别考试的规则。仅在考试相关内容出现、玩家询问考试、或需要根据规则推演NPC行为时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "考试关键词：'midterm_exam'（期中考试）、'uninhabited_island'（无人岛考试）",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
]


def _execute_tool(tool_name: str, arguments: dict, player_name: str = "") -> str:
    """Execute a tool by name and return the result as a JSON string."""
    if tool_name == "get_character_info":
        return _tool_get_character_info(arguments.get("char_name", ""))
    elif tool_name == "query_location_info":
        return _tool_query_location_info(arguments.get("location_id", ""), player_name)
    elif tool_name == "check_exam_rules":
        return _tool_check_exam_rules(arguments.get("keyword", ""))
    else:
        return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)


def _tool_get_character_info(char_name: str) -> str:
    """Query character info from CHARACTER_LIBRARY."""
    if not char_name:
        return json.dumps({"error": "未提供角色名"}, ensure_ascii=False)

    # Try exact match first
    char = CHARACTER_LIBRARY.get(char_name)
    if char is None:
        # Try loose match
        for name in CHARACTER_LIBRARY:
            if char_name in name or name in char_name:
                char = CHARACTER_LIBRARY[name]
                char_name = name
                break

    if char is None:
        return json.dumps({"error": f"未找到角色: {char_name}",
                           "available": list(CHARACTER_LIBRARY.keys())},
                          ensure_ascii=False)

    # Find the character in NPC_SCHEDULES to get their current location
    current_location = "未知"
    brief_status = ""
    for loc_id, npcs in NPC_SCHEDULES.items():
        for n in npcs:
            if n["name"] == char_name:
                current_location = LOCATIONS.get(loc_id, {}).get("name", loc_id)
                brief_status = n.get("brief_status", "")
                break

    info = {
        "name": char_name,
        "class": f"{char['class_name']}班",
        "traits": char["traits"],
        "public_info": [f"{item['label']}: {item['content']}" for item in char.get("public_info", [])],
        "current_location": current_location,
        "current_status": brief_status,
    }
    return json.dumps(info, ensure_ascii=False)


def _tool_query_location_info(location_id: str, player_name: str = "") -> str:
    """Query location info from LOCATIONS."""
    if not location_id:
        return json.dumps({"error": "未提供地点ID"}, ensure_ascii=False)

    loc = LOCATIONS.get(location_id)
    if loc is None:
        # Try finding by name keywords
        for lid, ldata in LOCATIONS.items():
            if location_id in lid or location_id in ldata.get("name", ""):
                loc = ldata
                location_id = lid
                break

    if loc is None:
        return json.dumps({"error": f"未找到地点: {location_id}",
                           "available": [f"{lid}: {ld['name']}" for lid, ld in LOCATIONS.items()]},
                          ensure_ascii=False)

    info = {
        "id": location_id,
        "name": loc["name"],
        "description": loc["description"],
        "connected_to": loc.get("connected_to", []),
        "connected_names": {cid: LOCATIONS.get(cid, {}).get("name", cid)
                           for cid in loc.get("connected_to", [])},
        "tags": loc.get("tags", []),
    }

    # Add NPCs at this location (filter out player character)
    npcs_at_loc = [n for n in NPC_SCHEDULES.get(location_id, [])
                   if n["name"] != player_name]
    if npcs_at_loc:
        info["npcs_here"] = [{"name": n["name"], "status": n["brief_status"]} for n in npcs_at_loc]

    return json.dumps(info, ensure_ascii=False)


def _tool_check_exam_rules(keyword: str) -> str:
    """Query exam rulebooks."""
    rulebook_dir = Path(__file__).parent / "config" / "data" / "rulebooks"
    rulebook_map = {
        "midterm_exam": "midterm_exam.txt",
        "uninhabited_island": "uninhabited_island.txt",
        "期中考试": "midterm_exam.txt",
        "无人岛": "uninhabited_island.txt",
    }

    filename = rulebook_map.get(keyword.lower())
    if filename is None:
        return json.dumps({"error": f"未知考试关键词: {keyword}",
                           "available": ["midterm_exam", "uninhabited_island"]},
                          ensure_ascii=False)

    file_path = rulebook_dir / filename
    if not file_path.exists():
        return json.dumps({"error": f"规则文件不存在: {filename}"}, ensure_ascii=False)

    content = file_path.read_text(encoding="utf-8")
    return json.dumps({"keyword": keyword, "rules": content}, ensure_ascii=False)


# ---- LLM Config ----

DEEPSEEK_API_KEY = "sk-a027465f568346db99147bb047d7a643"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
LLM_MODEL = "deepseek-chat"

GAME_SYSTEM_PROMPT = """你是一个高级AI叙事引擎，负责驱动《实力至上主义的教室》世界观下的文字冒险游戏。

## 核心身份
你同时扮演两个角色：
1. 叙述者：以第一人称视角（"我"）描写玩家角色的所见所闻、内心活动
2. 所有NPC：替所有非玩家角色生成对话和行为

## 绝对叙事法则
1. 第一人称视角，使用"我"来指代玩家角色
2. 信息不对称：你知道所有角色的隐藏秘密，但绝不能让不知情角色泄露秘密
3. 首次见面规则：玩家第一次遇见某角色时，不能直接使用该角色的全名，必须通过自我介绍等合理方式让玩家获知
4. 禁止替玩家做决定：悬停在关键时刻，将选择权交给玩家
5. 环境叙事克制：自然融入，每次不超过2-3句话
6. 角色一致性：每个NPC严格遵循其公开形象的性格、说话方式、行为模式
7. 换行要求（极其重要）：叙事文本必须使用\n来分隔段落。每段之间必须有\n\n（空行分隔），长段落内部也应用\n合理分行。禁止输出没有换行符的整块文本。JSON中narrative字段的值必须包含\n换行符。

## 选项生成规则（极其重要）
每次回复必须包含2-4个choices选项，除非玩家的行动是纯粹的环境观察（如"看看周围""观察""看窗外"）。
选项应引导故事向有意义的冲突或社交互动发展。选项用中文撰写。

## 返回格式
你必须以严格的JSON格式返回。以下是两个完整示例：

示例1（玩家在教室决定去食堂，时间从上午推进到中午）：
{
  "narrative": "我推开教室的后门，走向走廊。穿过一楼大厅，食堂就在前方。窗口飘来味噌汤的香气，正午的阳光透过玻璃窗洒进来...",
  "choices": [{"id": "1", "text": "去点一份午餐"}, {"id": "2", "text": "找个位置坐下观察"}],
  "state_changes": {"new_location_id": "cafeteria", "new_time_slot": "noon"}
}

示例2（玩家观察周围环境，时间不变）：
{
  "narrative": "我环顾四周。教室里一片嘈杂——有人趴在桌上睡觉，有人三三两两聚在一起聊天。黑板上写着值日表，角落里贴着社团招新海报。",
  "choices": [{"id": "1", "text": "走向前排的女生"}, {"id": "2", "text": "去走廊透透气"}],
  "state_changes": {}
}

示例3（玩家睡觉，推进到第二天早上）：
{
  "narrative": "我回到宿舍，躺在床上。白天的喧嚣在脑海中逐渐远去。闹钟响起时，窗外已经大亮——新的一天开始了。",
  "choices": [{"id": "1", "text": "起床洗漱"}, {"id": "2", "text": "再睡五分钟"}],
  "state_changes": {"new_location_id": "dormitory", "sleep_to_morning": true, "new_time_slot": "morning", "new_game_date": "2024-04-02"}
}

## state_changes规则（由AI自主判断）
- new_location_id：仅当玩家明确移动到了新地点时填写目标地点ID
- new_time_slot：当叙事中时间确实发生了变化时，直接填写目标时间段。可选值：morning（上午）、noon（中午）、dusk（傍晚）、evening（晚上）、late_night（深夜）。短暂行动（观察、简单回应、短暂思考、说几句话）不应改变时间，不要填写此字段
- new_game_date：当日期发生变化时（如跨天），填写新日期，格式YYYY-MM-DD（如2024-04-02）。仅在同一天内不需要填写
- sleep_to_morning：仅当玩家明确去睡觉时填写true，并移动至dormitory。同时应填写new_time_slot为morning，如有跨天需填写new_game_date
- 以下情况state_changes留空{}：纯粹观察、思考、看窗外、短暂闲聊、原地犹豫、简单回应
- 重要：不必每次都推进时间。如果玩家在原地进行了多个短暂行动，可以连续多次不改变时间，让剧情在同一时间段内充分展开
- 重要：在JSON中展示明确的new_time_slot，才能保证时间系统正确运行

可用的地点ID：classroom_d, hallway_1f, hallway_3f, hallway_5f, library, cafeteria, school_gymnasium, school_field, rooftop, dormitory, school_gate, school_bus, special_building

## 可用工具（函数调用）
你可以调用以下工具来获取准确的游戏数据。在生成叙事之前，根据需要使用工具查询信息：
- get_character_info(char_name)：查询角色的详细信息（外貌、身份、性格、班级、当前所在位置）。当你需要深入了解某个NPC、角色首次出场、或玩家与角色深入互动时应主动调用，确保角色行为符合其设定。
- query_location_info(location_id)：查询地点的描述、连接的其他地点、以及当前在场NPC。当玩家移动到新地点或观察环境时调用。
- check_exam_rules(keyword)：查询特别考试的完整规则（keyword为'midterm_exam'或'uninhabited_island'）。当剧情涉及考试、玩家讨论考试时调用。

工具调用要点：
- 先调用工具获取准确数据，再生成叙事——不要凭空编造角色背景或考试规则
- 工具返回的数据是此世界的权威事实，请自然地融入叙事，不要机械复述
- 可以一次调用多个工具（如果剧情涉及多个角色或多个地点）
- 纯粹的环境观察、简单问候等不需要调用工具

最终回复必须以JSON格式返回（narrative + choices + state_changes）。"""

PERSPECTIVE_SYSTEM_PROMPT = """你是一个心理侧写引擎，负责以特定角色的第一人称视角重写一段已经发生的剧情。

## 核心任务
你将以「{character_name}」的第一人称视角（"我"），重写下方提供的剧情片段。你必须严格代入该角色的内心世界。

## 绝对规则
1. **严格单一视角**：只写「{character_name}」能感知到、思考到、感受到的内容。绝不越界描写其他角色的内心想法——其他角色只能通过他们的表情、语气、动作等外部可观察特征来呈现。
2. **我的叙事**：全文使用"我"来指代「{character_name}」。
3. **基于性格推演**：该角色的心理活动必须符合其性格特质。从角色的立场出发，合理地推演他看到/听到这些事后的真实反应——他可能在想什么？有什么他没有说出口的？
4. **不可改变剧情**：重写时不能改变原剧情中发生的客观事实（谁说了什么、做了什么）。只能补充角色的内心视角——那些在原剧情中没有被呈现的心理活动。
5. **信息边界的尊重**：如果该角色不应该知道某些秘密或背景信息，就不要在心理活动中提及。
6. **纯文本输出**：只输出叙事文本，不需要JSON、不需要选项、不需要state_changes。禁止输出任何JSON格式的内容。
7. **换行要求**：使用\\n分隔段落，段落之间用\\n\\n空行分隔。禁止输出没有换行符的整块文本。

## 输出格式
仅输出一段连续的叙事文本，以第一人称"我"的视角展开。不需要任何前缀或后缀标记。"""


def _build_perspective_context(
    target_npc_name: str,
    char_info: dict | None,
    last_narrative: str,
    last_user_input: str,
    player_name: str,
    location_id: str,
    time_display: str,
) -> list[dict]:
    """Build messages for the perspective shift LLM call."""
    loc_info = LOCATIONS.get(location_id, {})
    loc_name = loc_info.get("name", location_id)

    # Build character profile
    char_profile = ""
    if char_info:
        char_profile += f"【{target_npc_name}的角色资料】\n"
        char_profile += f"班级：{char_info.get('class_name', '未知')}班\n"
        char_profile += f"性格特质：{'、'.join(char_info.get('traits', []))}\n"
        for info in char_info.get("public_info", []):
            char_profile += f"{info['label']}：{info['content']}\n"
        char_profile += f"\n"
    else:
        char_profile = f"【{target_npc_name}的角色资料】\n班级：未知\n性格特质：未知\n（以下为角色的公开言行模式，请基于此合理推演心理活动）\n\n"

    # Build scene info
    npcs_here = [n for n in NPC_SCHEDULES.get(location_id, []) if n["name"] != target_npc_name and n["name"] != player_name]
    npc_names = [n["name"] for n in npcs_here] if npcs_here else ["无其他人"]

    system_msg = PERSPECTIVE_SYSTEM_PROMPT.replace("{character_name}", target_npc_name)

    user_msg = f"""{char_profile}【场景信息】
时间：{time_display}
地点：{loc_name}（{loc_info.get('description', '')}）
在场其他人：{'、'.join(npc_names)}
角色「{player_name}」的行动：{last_user_input}

【原始剧情（以{player_name}视角叙述）】
{last_narrative}

请以「{target_npc_name}」的第一人称视角重写上述剧情，展现其内心心理活动。"""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ---- Database Helpers ----

def _build_state_dict(session: GameSession) -> dict:
    """Build a state dict from a GameSession ORM object."""
    loc = LOCATIONS.get(session.player_location_id, {})
    npcs = NPC_SCHEDULES.get(session.player_location_id, [])
    # 过滤掉玩家自己扮演的角色，避免提示词中将玩家视为NPC
    npcs = [n for n in npcs if n["name"] != session.player_name]
    char_entry = CHARACTER_LIBRARY.get(session.player_name, {})
    player_class = char_entry.get("class_name", "D") if char_entry else "D"
    return {
        "session_id": session.id,
        "game_date": session.game_date,
        "time_slot": session.time_slot,
        "location_id": session.player_location_id,
        "class_points": session.class_points,
        "private_points": session.private_points,
        "player_name": session.player_name,
        "player_char_id": session.player_char_id,
        "player_class": player_class,
        "dialogue_count_since_summary": session.dialogue_count_since_summary,
        "location": {
            "location_id": session.player_location_id,
            "name": loc.get("name", "未知"),
            "description": loc.get("description", ""),
            "connected_to": loc.get("connected_to", []),
            "tags": loc.get("tags", []),
            "zone_id": loc.get("zone_id"),
        },
        "spotlight_npcs": npcs,
        "time_display": f"{session.game_date} {TIME_DISPLAY[session.time_slot]}",
    }


def _advance_state(state_dict: dict, slots: int = 1) -> dict:
    """Advance time in a state dict. Returns updated dict."""
    idx = TIME_SLOTS.index(state_dict["time_slot"])
    new_idx = idx + slots
    days = new_idx // len(TIME_SLOTS)
    remainder = new_idx % len(TIME_SLOTS)
    if days > 0:
        dt = datetime.strptime(state_dict["game_date"], "%Y-%m-%d") + timedelta(days=days)
        state_dict["game_date"] = dt.strftime("%Y-%m-%d")
    state_dict["time_slot"] = TIME_SLOTS[remainder]
    return state_dict


def _sleep_to_morning(state_dict: dict) -> dict:
    """Advance time to next morning."""
    idx = TIME_SLOTS.index(state_dict["time_slot"])
    if idx == 0:
        return _advance_state(state_dict, len(TIME_SLOTS))
    else:
        return _advance_state(state_dict, len(TIME_SLOTS) - idx)


def _apply_state_changes(session: GameSession, changes: dict) -> None:
    """Apply AI-requested state changes directly to the ORM object."""
    if not changes:
        return
    new_loc = changes.get("new_location_id", "")
    if new_loc and new_loc in LOCATIONS:
        session.player_location_id = new_loc
    # Prefer explicit time fields (AI directly specifies the target)
    new_time_slot = changes.get("new_time_slot", "")
    if new_time_slot in ("morning", "noon", "dusk", "evening", "late_night"):
        session.time_slot = new_time_slot
    new_game_date = changes.get("new_game_date", "")
    if new_game_date and len(new_game_date) == 10:  # YYYY-MM-DD
        session.game_date = new_game_date
    # Fallback: legacy advance_slots (for backward compatibility)
    if not new_time_slot:
        slots = changes.get("advance_slots")
        if isinstance(slots, (int, float)) and 0 < slots <= 4:
            sd = {"game_date": session.game_date, "time_slot": session.time_slot}
            sd = _advance_state(sd, int(slots))
            session.game_date = sd["game_date"]
            session.time_slot = sd["time_slot"]
    if changes.get("sleep_to_morning"):
        sd = {"game_date": session.game_date, "time_slot": session.time_slot}
        sd = _sleep_to_morning(sd)
        session.game_date = sd["game_date"]
        session.time_slot = sd["time_slot"]
        session.player_location_id = "dormitory"


async def _get_or_create_session(db) -> GameSession:
    """Get the active game session or create a new one."""
    result = await db.execute(
        select(GameSession).where(GameSession.is_active == True).limit(1)
    )
    gs = result.scalar_one_or_none()
    if gs is None:
        gs = GameSession(session_slug="default", player_name="绫小路清隆")
        db.add(gs)
        await db.flush()
    return gs


async def _save_dialogue(
    db, session_id: str, seq: int, user_input: str, llm_response: str,
    response_data: dict | None = None, choice_id: str | None = None,
    location_id: str | None = None,
) -> DialogueLog:
    dl = DialogueLog(
        session_id=session_id, sequence_num=seq,
        user_input=user_input, llm_response=llm_response,
        response_data=response_data, choice_id=choice_id,
        location_at_time=location_id,
    )
    db.add(dl)
    await db.flush()
    return dl


async def _get_recent_history(db, session_id: str, limit: int = 10) -> list[dict]:
    """Get recent N rounds of dialogue as a list of dicts."""
    result = await db.execute(
        select(DialogueLog)
        .where(DialogueLog.session_id == session_id)
        .order_by(DialogueLog.sequence_num.desc())
        .limit(limit * 2)  # user + assistant per round
    )
    rows = result.scalars().all()
    rows.reverse()  # chronological order
    history = []
    for r in rows:
        entry = {
            "sequence_num": r.sequence_num,
            "user_input": r.user_input,
            "narrative": r.llm_response,
        }
        if r.response_data and "choices" in r.response_data:
            entry["choices"] = r.response_data["choices"]
        history.append(entry)
    return history


async def _get_latest_summary(db, session_id: str) -> str:
    """Get the latest consolidated story summary."""
    result = await db.execute(
        select(StorySummary)
        .where(StorySummary.session_id == session_id)
        .order_by(StorySummary.dialogue_end_seq.desc())
        .limit(1)
    )
    summary = result.scalar_one_or_none()
    return summary.summary_text if summary else ""


async def _maybe_summarize(db, session_id: str, gs: GameSession) -> None:
    """If dialogue count exceeds threshold, summarize oldest unsummarized dialogues."""
    threshold = settings.dialogue_summary_threshold
    if gs.dialogue_count_since_summary < threshold:
        return

    total_result = await db.execute(
        select(func.count()).select_from(DialogueLog)
        .where(DialogueLog.session_id == session_id)
    )
    total_count = total_result.scalar() or 0

    if total_count <= threshold:
        gs.dialogue_count_since_summary = total_count
        return

    # Get the oldest 10 un-summarized dialogues
    last_summary_result = await db.execute(
        select(func.max(StorySummary.dialogue_end_seq))
        .where(StorySummary.session_id == session_id)
    )
    last_end = last_summary_result.scalar()
    unsummarized_count = total_count - (last_end or 0)

    if unsummarized_count < threshold:
        gs.dialogue_count_since_summary = unsummarized_count
        return

    # Fetch the oldest unsummarized block
    offset = last_end if last_end is not None else 0
    old_result = await db.execute(
        select(DialogueLog)
        .where(DialogueLog.session_id == session_id)
        .order_by(DialogueLog.sequence_num.asc())
        .offset(offset)
        .limit(threshold * 2)
    )
    old_rows = old_result.scalars().all()

    if len(old_rows) < 2:
        gs.dialogue_count_since_summary = 0
        return

    # Build summary prompt
    dialogue_text_parts = []
    for r in old_rows:
        dialogue_text_parts.append(f"玩家: {r.user_input}")
        narrative = r.llm_response
        dialogue_text_parts.append(f"AI: {narrative}")
    dialogue_text = "\n".join(dialogue_text_parts)

    summary_prompt = f"""请用1-2段中文总结以下游戏对话的关键情节发展。只输出总结文本，不要其他内容。

{dialogue_text}

关键情节总结："""

    # Call LLM for summary
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的游戏叙事总结者。请用简洁的中文总结对话的关键情节。"},
                        {"role": "user", "content": summary_prompt},
                    ],
                    "max_tokens": 300,
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            summary_text = data["choices"][0]["message"]["content"].strip()
    except Exception:
        summary_text = f"（共{len(old_rows)}条对话，情节略）"

    start_seq = old_rows[0].sequence_num
    end_seq = old_rows[-1].sequence_num

    new_summary = StorySummary(
        session_id=session_id,
        dialogue_start_seq=start_seq,
        dialogue_end_seq=end_seq,
        summary_text=summary_text,
    )
    db.add(new_summary)

    gs.dialogue_count_since_summary = 0


# ---- Narrative Generation ----

def _build_llm_context(
    user_input: str, state_dict: dict, max_tokens: int = 1024,
    history: list[dict] | None = None, summary: str = "",
) -> list[dict]:
    """Build messages for LLM call, with chat history injected."""
    loc = state_dict.get("location", {})
    time_str = state_dict["time_display"]
    npcs = state_dict.get("spotlight_npcs", [])

    npc_context = ""
    if npcs:
        npc_lines = []
        for n in npcs:
            marker = "★" if n.get("is_critical") else "·"
            npc_lines.append(f"{marker} {n['name']}：{n['brief_status']}")
        npc_context = "在场角色：\n" + "\n".join(npc_lines)

    # Dynamic word count based on max_tokens
    nar_min = max(500, max_tokens // 2)
    choice_max = min(30, max(15, max_tokens // 100))
    word_req = f"\n【字数要求】叙事不少于{nar_min}字。每个选项不超过{choice_max}字。"

    # Build history section
    history_section = ""
    if summary:
        history_section += f"【历史摘要】\n{summary}\n\n"
    if history and len(history) > 0:
        recent_lines = ["【最近对话】"]
        for entry in history:
            recent_lines.append(f"- 我：{entry['user_input']}")
            narrative = entry.get('narrative', '')
            recent_lines.append(f"- AI：{narrative}")
        history_section += "\n".join(recent_lines) + "\n\n"

    player_name = state_dict.get("player_name", "学生")
    player_class = state_dict.get("player_class", "D")

    if user_input.strip() == "/intro":
        user_msg = f"""{history_section}【当前状态】
玩家：{player_name}（{player_class}班学生）
时间：{time_str}
位置：{loc.get('name', '未知')}（{loc.get('description', '')}）
班级点数：{state_dict['class_points']} | 私人点数：{state_dict['private_points']}
{npc_context}

【系统指令】
这是游戏的开场。请生成一段高质量的开场叙事：
- 以第一人称"我"（{player_name}）的视角，作为刚入学的新生
- 描述D班教室的慵懒氛围，介绍在场的关键角色
- 暗示"特别考试"即将到来（距第一次特别考试还有15天）
- 营造《实力至上主义的教室》独特的暗流涌动氛围
{word_req}
- 必须包含2-3个引导下一步行动的选项"""
    else:
        user_msg = f"""{history_section}【当前状态】
玩家：{player_name}（{player_class}班学生）
时间：{time_str}
位置：{loc.get('name', '未知')}（{loc.get('description', '')}）
班级点数：{state_dict['class_points']} | 私人点数：{state_dict['private_points']}
{npc_context}

【玩家行动】
{user_input}

请根据以上信息生成叙事。如果有【最近对话】，请保持叙事连贯性。
{word_req}
【重要】请在JSON回复中包含至少2个choices选项，引导下一步行动。"""

    return [
        {"role": "system", "content": GAME_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def _parse_llm_content(content: str) -> dict:
    """Parse JSON from LLM response text. Returns dict with narrative, choices, and state_changes."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(l for l in lines if not l.startswith("```"))
    try:
        result = json.loads(content)
        return {
            "narrative": result.get("narrative", content),
            "choices": result.get("choices", []),
            "state_changes": result.get("state_changes", {}),
        }
    except json.JSONDecodeError:
        return {"narrative": content, "choices": [], "state_changes": {}}


# ---- Offline Response Generator ----

def generate_offline_response(user_input: str, state_dict: dict) -> dict:
    """Generate a narrative response without LLM (demo/offline mode)."""
    loc = state_dict.get("location", {})
    loc_name = loc.get("name", "未知地点")
    location_id = state_dict["location_id"]
    player_name = state_dict.get("player_name", "")
    npcs = [n for n in NPC_SCHEDULES.get(location_id, []) if n["name"] != player_name]
    time_str = state_dict["time_display"]

    inp = user_input.lower().strip()

    if inp in ("/rest", "休息", "休息一会"):
        return {
            "narrative": f"你决定在{loc_name}休息一会儿。时间悄然流逝...",
            "choices": [],
            "state_changes": {"advance_slots": 1},
        }

    if inp in ("/sleep", "睡觉", "去睡觉", "回宿舍睡觉"):
        return {
            "narrative": "你回到宿舍，躺在床上。在这个陌生的学校里，宿舍是你唯一的私人空间。\n\n第二天早上，闹钟准时响起。新的一天开始了。",
            "choices": [],
            "state_changes": {"new_location_id": "dormitory", "sleep_to_morning": True},
        }

    if inp.startswith("/go "):
        target = inp[4:].strip()
        for lid, ldata in LOCATIONS.items():
            if target in lid or target in ldata["name"]:
                npcs_there = [n for n in NPC_SCHEDULES.get(lid, []) if n["name"] != player_name]
                npc_str = ""
                if npcs_there:
                    npc_str = " " + "、".join(n["name"] for n in npcs_there) + "也在这里。"
                return {
                    "narrative": f"你来到了【{ldata['name']}】。{ldata['description']}{npc_str}",
                    "choices": [],
                    "state_changes": {"new_location_id": lid, "advance_slots": 1},
                }
        return {
            "narrative": f"你想去{target}，但不知道怎么从这里过去。看看其他地方吧。",
            "choices": [],
            "state_changes": {},
        }

    if any(w in inp for w in ("去", "前往", "走到", "去往")):
        for lid, ldata in LOCATIONS.items():
            if ldata["name"] in user_input or lid in user_input:
                npcs_there = [n for n in NPC_SCHEDULES.get(lid, []) if n["name"] != player_name]
                npc_str = ""
                if npcs_there:
                    npc_str = "\n\n" + "、".join(n["name"] for n in npcs_there) + "也在这里。"
                return {
                    "narrative": f"你来到了【{ldata['name']}】。{ldata['description']}{npc_str}",
                    "choices": [],
                    "state_changes": {"new_location_id": lid, "advance_slots": 1},
                }

    if any(w in inp for w in ("看", "观察", "打量", "环顾")):
        desc = loc.get("description", "")
        npc_desc = ""
        if npcs:
            npc_desc = "\n\n在附近，你注意到" + "、".join(
                f"{n['name']}（{n['brief_status']}）" for n in npcs
            ) + "。"
        return {
            "narrative": f"你环顾四周。{desc}{npc_desc}",
            "choices": [],
            "state_changes": {},
        }

    if any(w in inp for w in ("走", "出去", "离开", "出")):
        conn = loc.get("connected_to", [])
        if conn:
            first = conn[0]
            first_loc = LOCATIONS.get(first, {})
            return {
                "narrative": f"你离开了{loc_name}，来到了【{first_loc.get('name', '走廊')}】。",
                "choices": [],
                "state_changes": {"new_location_id": first, "advance_slots": 1},
            }

    npc_mention = ""
    if npcs:
        npc_mention = f"\n\n在{loc_name}里，" + "、".join(
            f"{n['name']}（{n['brief_status']}）" for n in npcs
        ) + "。"

    return {
        "narrative": f"（{time_str} | {loc_name}）\n你{user_input}。{npc_mention}\n\n这是{loc.get('description', '一个普通的校园角落。')}",
        "choices": [],
        "state_changes": {},
    }


# ---- LLM Integration ----

async def generate_llm_response(
    user_input: str, state_dict: dict, max_tokens: int = 1024,
    history: list[dict] | None = None, summary: str = "",
) -> dict:
    """Send the player input to DeepSeek and get a narrative response (with tool calling)."""
    messages = _build_llm_context(user_input, state_dict, max_tokens, history, summary)

    async with httpx.AsyncClient(timeout=120.0) as client:
        # ---- Tool calling loop ----
        MAX_TOOL_ROUNDS = 3
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                resp = await client.post(
                    f"{DEEPSEEK_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "tools": TOOL_DEFINITIONS,
                        "tool_choice": "auto",
                        "max_tokens": 512,
                        "temperature": 0.8,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0].get("message", {})

                if msg.get("tool_calls"):
                    messages.append(msg)
                    for tc in msg["tool_calls"]:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            fn_args = {}
                        result = _execute_tool(fn_name, fn_args, state_dict.get("player_name", ""))
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                else:
                    # No more tools — got content response
                    content = msg.get("content", "").strip()
                    if not content:
                        break
                    parsed = _parse_llm_content(content)
                    parsed["_tool_calls"] = len(
                        [m for m in messages if m.get("role") == "tool"]
                    )
                    return parsed
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
                return {"narrative": f"[LLM错误: {e}]", "choices": [], "state_changes": {}}

        # Fall back to a full-token call if tool loop exhausted
        try:
            resp = await client.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.8,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            return _parse_llm_content(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
            return {"narrative": f"[LLM错误: {e}]", "choices": [], "state_changes": {}}


async def generate_llm_stream(
    user_input: str, state_dict: dict, max_tokens: int,
    history: list[dict] | None, summary: str, db_session,
):
    """SSE streaming generator with DB persistence and tool calling support."""
    messages = _build_llm_context(user_input, state_dict, max_tokens, history, summary)
    accumulated_content = ""
    tool_call_history = []

    async with httpx.AsyncClient(timeout=120.0) as client:
        # ---- Phase 1: Tool calling loop (non-streaming) ----
        MAX_TOOL_ROUNDS = 3
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                tool_resp = await client.post(
                    f"{DEEPSEEK_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "tools": TOOL_DEFINITIONS,
                        "tool_choice": "auto",
                        "max_tokens": 512,
                        "temperature": 0.8,
                    },
                )
                tool_resp.raise_for_status()
                tool_data = tool_resp.json()
                choice = tool_data["choices"][0]
                msg = choice.get("message", {})

                if msg.get("tool_calls"):
                    # Add assistant message with tool calls
                    messages.append(msg)
                    for tc in msg["tool_calls"]:
                        fn_name = tc["function"]["name"]
                        try:
                            fn_args = json.loads(tc["function"]["arguments"])
                        except json.JSONDecodeError:
                            fn_args = {}
                        result = _execute_tool(fn_name, fn_args, state_dict.get("player_name", ""))
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result,
                        })
                        tool_call_history.append({
                            "tool": fn_name,
                            "args": tc["function"]["arguments"],
                            "result": result[:300] + "..." if len(result) > 300 else result,
                        })
                else:
                    # No more tool calls — got content (or finish_reason=stop)
                    break
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
                yield f"data: {json.dumps({'error': f'工具调用失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

        # ---- Phase 2: Stream the narrative ----
        try:
            async with client.stream(
                "POST",
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.8,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            accumulated_content += content
                            yield f"data: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except (httpx.HTTPError, httpx.StreamError) as e:
            yield f"data: {json.dumps({'error': f'连接失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            return

    # Parse accumulated content
    parsed = _parse_llm_content(accumulated_content)

    # Get fresh session from DB
    gs_result = await db_session.execute(
        select(GameSession).where(GameSession.id == state_dict["session_id"])
    )
    gs = gs_result.scalar_one()

    # Apply state changes and save dialogue
    _apply_state_changes(gs, parsed.get("state_changes", {}))

    # Increment sequence number
    seq_result = await db_session.execute(
        select(func.coalesce(func.max(DialogueLog.sequence_num), 0))
        .where(DialogueLog.session_id == gs.id)
    )
    next_seq = seq_result.scalar() + 1

    gs.dialogue_count_since_summary += 1

    # Save dialogue
    response_data = {"choices": parsed.get("choices", [])}
    await _save_dialogue(
        db_session, gs.id, next_seq, user_input, parsed["narrative"],
        response_data=response_data,
        location_id=gs.player_location_id,
    )

    # Maybe summarize old dialogues
    await _maybe_summarize(db_session, gs.id, gs)
    await db_session.commit()
    await db_session.refresh(gs)

    # Build state for response
    fresh_state = _build_state_dict(gs)
    fresh_state["narrative"] = parsed["narrative"]
    fresh_state["choices"] = parsed.get("choices", [])

    done_msg = {
        "done": True,
        "choices": parsed.get("choices", []),
        "state": fresh_state,
        "debug": {
            "prompt": json.dumps(messages, ensure_ascii=False, indent=2),
            "raw_json": accumulated_content,
            "tool_calls": tool_call_history,
        },
    }
    yield f"data: {json.dumps(done_msg, ensure_ascii=False)}\n\n"


# ---- FastAPI App ----

app = FastAPI(title="实教AI模拟器 - Web前端")

from pathlib import Path
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_html_content = (templates_dir / "game.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_html_content)


@app.get("/api/demo/state")
async def get_state():
    """Get current game state from DB."""
    async with async_session() as db:
        gs = await _get_or_create_session(db)
        return JSONResponse(_build_state_dict(gs))


@app.post("/api/demo/act")
async def act(request: Request):
    """Non-LLM action endpoint (test mode). Persists to DB."""
    body = await request.json()
    user_input = body.get("user_input", "")
    use_llm = body.get("use_llm", False)
    max_tokens = body.get("max_tokens", 1024)

    async with async_session() as db:
        gs = await _get_or_create_session(db)
        state_dict = _build_state_dict(gs)
        history = await _get_recent_history(db, gs.id, limit=settings.max_history_dialogues)
        summary = await _get_latest_summary(db, gs.id)

        if use_llm:
            result = await generate_llm_response(
                user_input, state_dict, max_tokens=max_tokens,
                history=history, summary=summary,
            )
        else:
            result = generate_offline_response(user_input, state_dict)

        _apply_state_changes(gs, result.get("state_changes", {}))

        seq_result = await db.execute(
            select(func.coalesce(func.max(DialogueLog.sequence_num), 0))
            .where(DialogueLog.session_id == gs.id)
        )
        next_seq = seq_result.scalar() + 1
        gs.dialogue_count_since_summary += 1

        await _save_dialogue(
            db, gs.id, next_seq, user_input, result["narrative"],
            response_data={"choices": result.get("choices", [])},
            location_id=gs.player_location_id,
        )
        await _maybe_summarize(db, gs.id, gs)
        await db.commit()
        await db.refresh(gs)

        state_data = _build_state_dict(gs)
        state_data["narrative"] = result["narrative"]
        state_data["choices"] = result.get("choices", [])
        return JSONResponse(state_data)


@app.post("/api/llm/act")
async def llm_act(request: Request):
    """LLM-powered non-streaming endpoint."""
    body = await request.json()
    user_input = body.get("user_input", "")
    max_tokens = body.get("max_tokens", 1024)

    async with async_session() as db:
        gs = await _get_or_create_session(db)
        state_dict = _build_state_dict(gs)
        history = await _get_recent_history(db, gs.id, limit=settings.max_history_dialogues)
        summary = await _get_latest_summary(db, gs.id)

        result = await generate_llm_response(
            user_input, state_dict, max_tokens=max_tokens,
            history=history, summary=summary,
        )
        _apply_state_changes(gs, result.get("state_changes", {}))

        seq_result = await db.execute(
            select(func.coalesce(func.max(DialogueLog.sequence_num), 0))
            .where(DialogueLog.session_id == gs.id)
        )
        next_seq = seq_result.scalar() + 1
        gs.dialogue_count_since_summary += 1

        await _save_dialogue(
            db, gs.id, next_seq, user_input, result["narrative"],
            response_data={"choices": result.get("choices", [])},
            location_id=gs.player_location_id,
        )
        await _maybe_summarize(db, gs.id, gs)
        await db.commit()
        await db.refresh(gs)

        state_data = _build_state_dict(gs)
        state_data["narrative"] = result["narrative"]
        state_data["choices"] = result.get("choices", [])
        return JSONResponse(state_data)


@app.post("/api/llm/stream")
async def llm_stream(request: Request):
    """SSE streaming LLM endpoint with DB persistence."""
    body = await request.json()
    user_input = body.get("user_input", "")
    max_tokens = body.get("max_tokens", 1024)

    db = async_session()
    try:
        gs = await _get_or_create_session(db)
        state_dict = _build_state_dict(gs)
        history = await _get_recent_history(db, gs.id, limit=settings.max_history_dialogues)
        summary = await _get_latest_summary(db, gs.id)
    except Exception as e:
        await db.close()
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"]),
            media_type="text/event-stream",
        )

    async def stream_with_cleanup():
        try:
            async for chunk in generate_llm_stream(
                user_input, state_dict, max_tokens, history, summary, db,
            ):
                yield chunk
        finally:
            await db.close()

    return StreamingResponse(
        stream_with_cleanup(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/llm/perspective")
async def llm_perspective(request: Request):
    """SSE endpoint for single-character perspective shift (psychological POV)."""
    body = await request.json()
    target_npc_name = body.get("target_npc_name", "")
    last_narrative = body.get("last_narrative", "")
    last_user_input = body.get("last_user_input", "")
    location_id = body.get("location_id", "classroom_d")
    time_display = body.get("time_display", "")
    player_name = body.get("player_name", "")
    max_tokens = body.get("max_tokens", 1024)

    char_info = CHARACTER_LIBRARY.get(target_npc_name)
    messages = _build_perspective_context(
        target_npc_name, char_info,
        last_narrative, last_user_input,
        player_name, location_id, time_display,
    )

    async def stream_perspective():
        accumulated = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{DEEPSEEK_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.8,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                accumulated += content
                                yield f"data: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

            done_msg = {
                "done": True,
                "perspective": accumulated,
                "target_npc": target_npc_name,
            }
            yield f"data: {json.dumps(done_msg, ensure_ascii=False)}\n\n"

        except (httpx.HTTPError, httpx.StreamError) as e:
            yield f"data: {json.dumps({'error': f'连接失败: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_perspective(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Game Management Endpoints ----

@app.get("/api/game/load")
async def game_load():
    """Check for existing save and return state + history."""
    async with async_session() as db:
        result = await db.execute(
            select(GameSession).where(GameSession.is_active == True).limit(1)
        )
        gs = result.scalar_one_or_none()

        if gs is None:
            return JSONResponse({"has_save": False, "state": None, "history": []})

        state_dict = _build_state_dict(gs)
        history = await _get_recent_history(db, gs.id, limit=settings.max_history_dialogues)
        summary = await _get_latest_summary(db, gs.id)

        return JSONResponse({
            "has_save": True,
            "state": state_dict,
            "history": history,
            "summary": summary,
        })


@app.post("/api/game/reset")
async def game_reset(request: Request):
    """Reset game: deactivate old session, clear old secrets, create new one."""
    body = await request.json()
    player_name = body.get("player_name", "绫小路清隆")
    player_char_id = body.get("player_char_id")

    async with async_session() as db:
        # Deactivate old sessions
        old_result = await db.execute(
            select(GameSession).where(GameSession.is_active == True)
        )
        for old_gs in old_result.scalars().all():
            old_gs.is_active = False

        # Clear old secrets and secret knowledge
        from src.models.secret import Secret, SecretKnowledge
        await db.execute(delete(SecretKnowledge))
        await db.execute(delete(Secret))

        # Seed secrets from CHARACTER_LIBRARY
        char_entry = CHARACTER_LIBRARY.get(player_name, {})
        secrets_data = char_entry.get("secrets", [])
        seeded = 0
        for s in secrets_data:
            secret = Secret(
                info_id=s.get("info_id", ""),
                content=s.get("content", ""),
                subject_char_id=player_char_id,
                is_public=False,
            )
            db.add(secret)
            await db.flush()
            # Create SecretKnowledge for known_by entries
            for knower_name in s.get("known_by", []):
                # Look up knower in CHARACTER_LIBRARY for their role_id
                knower = CHARACTER_LIBRARY.get(knower_name, {})
                sk = SecretKnowledge(
                    secret_id=secret.id,
                    character_id=knower.get("role_id", knower_name),
                    unlocked_reason="开局已知",
                )
                db.add(sk)
            seeded += 1

        await db.commit()

        # Create new session
        new_gs = GameSession(
            session_slug=f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            player_name=player_name,
            player_char_id=player_char_id,
            game_date="2024-04-01",
            time_slot="morning",
            player_location_id="classroom_d",
            class_points=0,
            private_points=100000,
            dialogue_count_since_summary=0,
        )
        db.add(new_gs)
        await db.commit()
        await db.refresh(new_gs)

        return JSONResponse({
            "success": True,
            "session_id": new_gs.id,
            "state": _build_state_dict(new_gs),
            "secrets_seeded": seeded,
        })


@app.post("/api/game/match_character")
async def match_character(request: Request):
    """Fuzzy match a character name against the library."""
    body = await request.json()
    name = body.get("name", "").strip()

    if not name:
        return JSONResponse({"matched": False, "error": "请输入名字"})

    # Exact match first
    if name in CHARACTER_LIBRARY:
        char = CHARACTER_LIBRARY[name]
        return JSONResponse({
            "matched": True,
            "name": name,
            "character": char,
        })

    # Fuzzy match (contains)
    for lib_name, char in CHARACTER_LIBRARY.items():
        if name in lib_name or lib_name in name:
            return JSONResponse({
                "matched": True,
                "name": lib_name,
                "character": char,
            })

    return JSONResponse({
        "matched": False,
        "suggestion": "create_new",
        "message": f"未找到与「{name}」匹配的角色，请创建新角色",
    })


@app.post("/api/game/create_character")
async def create_character(request: Request):
    """Create a custom player character."""
    body = await request.json()
    name = body.get("name", "").strip()
    class_name = body.get("class_name", "D")
    traits = body.get("traits", [])
    public_info = body.get("public_info", [])
    private_points = body.get("private_points", 100000)

    if not name:
        return JSONResponse({"success": False, "error": "角色名不能为空"})

    role_id = f"custom_{name.lower().replace(' ', '_')}"

    char_data = {
        "role_id": role_id,
        "class_name": class_name,
        "traits": traits,
        "public_info": public_info,
    }

    # Add to library
    CHARACTER_LIBRARY[name] = char_data

    return JSONResponse({
        "success": True,
        "name": name,
        "character": char_data,
    })


@app.post("/api/game/import")
async def game_import(request: Request):
    """Import JSON data (characters, locations, events)."""
    body = await request.json()
    import_type = body.get("type", "")
    data = body.get("data", [])

    if import_type == "characters":
        count = 0
        for entry in data:
            name = entry.get("name", "")
            if name and name not in CHARACTER_LIBRARY:
                CHARACTER_LIBRARY[name] = {
                    "role_id": entry.get("role_id", f"imported_{name.lower().replace(' ', '_')}"),
                    "class_name": entry.get("class_name", "D"),
                    "traits": entry.get("traits", []),
                    "public_info": entry.get("public_info", []),
                    "secrets": entry.get("secrets", []),
                }
                count += 1
        return JSONResponse({"success": True, "imported": count, "type": "characters"})

    elif import_type == "locations":
        count = 0
        for entry in data:
            lid = entry.get("location_id", "")
            if lid and lid not in LOCATIONS:
                LOCATIONS[lid] = {
                    "location_id": lid,
                    "name": entry.get("name", lid),
                    "description": entry.get("description", ""),
                    "tags": entry.get("tags", []),
                    "connected_to": entry.get("connected_to", []),
                    "zone_id": entry.get("zone_id", ""),
                }
                count += 1
        return JSONResponse({"success": True, "imported": count, "type": "locations"})

    elif import_type == "events":
        # Events are stored in DB; for now, just acknowledge
        return JSONResponse({"success": True, "imported": len(data), "type": "events"})

    elif import_type == "worldview":
        # Worldview is informational; stored for future use
        return JSONResponse({"success": True, "imported": 1, "type": "worldview"})

    return JSONResponse({"success": False, "error": f"Unknown import type: {import_type}"})


# ---- Main ----

def main():
    import asyncio
    import uvicorn

    # Initialize database before starting server
    asyncio.run(init_db())

    print("=" * 60)
    print("  实教AI模拟器 - Web前端服务器 (SQLite版)")
    print("  数据库: elite_simulator.db")
    print("  打开浏览器访问: http://localhost:8000")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
