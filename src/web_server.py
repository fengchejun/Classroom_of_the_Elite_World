"""
实教AI模拟器 - Web前端服务器 (SQLite版)

启动: py -m src.web_server
然后打开 http://localhost:8001
"""

from __future__ import annotations

import io
import json
import re
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
from src.core.npc_funnel import run_npc_funnel
from src.core.variable_agent import extract_variable_changes
from src.core.ai_validator import (
    validate_tool_call,
    validate_llm_response,
    build_validation_error_prompt,
)
from src.core.class_openings import CLASS_OPENING_NARRATIVES, build_opening_system_prompt
from src.core.time_engine.clock import TIME_SLOTS
from src.db import async_session, init_db
from src.models.dialogue import DialogueLog, StorySummary
from src.models.game_session import GameSession

# ---- Constants ----

TIME_DISPLAY = {
    "morning": "上午", "noon": "中午", "dusk": "傍晚",
    "evening": "晚上", "late_night": "深夜",
}

# ============================================================
# ZONES (6 major areas, each contains sub-locations)
# ============================================================
ZONES = {
    "teaching_building": {
        "zone_id": "teaching_building",
        "name": "教学楼",
        "description": "高度育成高中的核心教学区，四层建筑。一层有主入口、图书馆和教员办公室；二层为一年级教室；三层为二年级教室；四层为三年级教室和学生会室。各层由走廊串联，楼梯和走廊设有监视器。屋顶全年开放，仅门外有监视器，是校内少数监控盲区之一。",
        "type": "campus",
        "sub_locations": [
            "hallway_1f", "hallway_2f", "hallway_3f", "hallway_4f",
            "classroom_1a", "classroom_1b", "classroom_1c", "classroom_1d",
            "classroom_2a", "classroom_2b", "classroom_2c", "classroom_2d",
            "classroom_3a", "classroom_3b", "classroom_3c", "classroom_3d",
            "library", "student_council_room", "teachers_office",
            "guidance_room", "rooftop",
        ],
        "entry_points": ["hallway_1f"],
    },
    "special_building": {
        "zone_id": "special_building",
        "name": "特别教学大楼",
        "description": "独立于普通教学楼的建筑。平时人烟稀少，不用于社团活动。三楼是校内极少数未设置监视器的盲区。文化祭时可租用教室摆摊。",
        "type": "campus",
        "sub_locations": [
            "special_building_1f", "special_building_2f", "special_building_3f",
        ],
        "entry_points": ["special_building_1f"],
    },
    "dormitory": {
        "zone_id": "dormitory",
        "name": "宿舍区",
        "description": "学生居住区，共有3栋独立楼宇。男女共用大楼但严禁不正当关系。实行严格的房卡管理和倒垃圾/噪音规范。同一年级的学生住在同一栋楼，男生在低层，女生在高层。主要由电梯上下楼。",
        "type": "campus",
        "sub_locations": [
            "dorm_lobby", "dorm_male_floor", "dorm_female_floor", "dorm_courtyard",
        ],
        "entry_points": ["dorm_lobby"],
    },
    "keyaki_mall": {
        "zone_id": "keyaki_mall",
        "name": "榉树购物中心",
        "description": "校园内独立的庞大商业区。包含学生食堂、帕雷特咖啡馆、便利店、电影院、卡拉OK等设施。是放学后学生最大的聚集地，也是学校生活的重要社交场所。",
        "type": "campus",
        "sub_locations": [
            "mall_entrance", "mall_cafeteria", "mall_cafe",
            "mall_shop", "mall_entertainment",
        ],
        "entry_points": ["mall_entrance"],
    },
    "event_cruise": {
        "zone_id": "event_cruise",
        "name": "豪华游轮·圣维纳斯号",
        "description": "仅在特别考试（如无人岛考试后的船上考试）期间开放。共有地上四层、地下四层及顶层甲板。包含宴会厅、考试区、男女客房、娱乐区等设施。",
        "type": "event",
        "sub_locations": [
            "cruise_0f", "cruise_1f", "cruise_2f", "cruise_3f", "cruise_4f",
            "cruise_b1f", "cruise_b2f", "cruise_b3f", "cruise_b4f",
        ],
        "entry_points": ["cruise_1f"],
    },
    "event_island": {
        "zone_id": "event_island",
        "name": "无人岛",
        "description": "仅在特别考试（无人岛生存考试）期间开放。面积约0.5平方公里的荒岛，包含海岸登陆点、内陆河流（核心水源）、森林陡坡，以及散布在洞窟或河边的占领据点。地形复杂易迷路。",
        "type": "event",
        "sub_locations": [
            "island_beach", "island_forest", "island_river",
            "island_base1", "island_base2", "island_base3",
        ],
        "entry_points": ["island_beach"],
    },
}

# ============================================================
# LOCATIONS (53 sub-locations across all zones + standalone)
# ============================================================
LOCATIONS = {
    # ---- 教学楼 · 走廊 ----
    "hallway_1f": {
        "location_id": "hallway_1f", "name": "一层走廊",
        "description": "教学楼一层的主走廊，连接正门方向。公告栏上贴着各类通知和社团招新海报。下课时间学生来来往往，是最繁忙的通道。",
        "tags": ["indoor", "corridor", "public"],
        "connected_to": ["hallway_2f", "library", "teachers_office",
                         "campus_gate", "special_building_1f", "sports_field"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "1F",
    },
    "hallway_2f": {
        "location_id": "hallway_2f", "name": "二层走廊",
        "description": "教学楼二层的走廊，一年级教室分布在这一层。课间时一年级学生在此穿梭，偶尔能看到二年级学生经过。",
        "tags": ["indoor", "corridor", "public"],
        "connected_to": ["hallway_1f", "hallway_3f",
                         "classroom_1a", "classroom_1b", "classroom_1c", "classroom_1d"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "2F",
    },
    "hallway_3f": {
        "location_id": "hallway_3f", "name": "三层走廊",
        "description": "教学楼三层的走廊，二年级教室分布在这一层。较为安静，偶尔能听到教室里传来的讲课声。",
        "tags": ["indoor", "corridor", "public"],
        "connected_to": ["hallway_2f", "hallway_4f",
                         "classroom_2a", "classroom_2b", "classroom_2c", "classroom_2d"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "3F",
    },
    "hallway_4f": {
        "location_id": "hallway_4f", "name": "四层走廊",
        "description": "教学楼四层的走廊，三年级教室和学生会室分布在这一层。临近毕业的三年级学生行色匆匆，气氛比其他楼层更为严肃。",
        "tags": ["indoor", "corridor", "public"],
        "connected_to": ["hallway_3f", "rooftop", "student_council_room", "guidance_room",
                         "classroom_3a", "classroom_3b", "classroom_3c", "classroom_3d"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },

    # ---- 教学楼 · 一年级教室 ----
    "classroom_1a": {
        "location_id": "classroom_1a", "name": "一年A班教室",
        "description": "一年A班的教室。坂柳有栖所在的精英班级，桌椅整齐，氛围严肃认真，学生成绩普遍优异。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "2F",
    },
    "classroom_1b": {
        "location_id": "classroom_1b", "name": "一年B班教室",
        "description": "一年B班的教室。一之濑帆波所在的班级，班级凝聚力强，气氛融洽友好。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "2F",
    },
    "classroom_1c": {
        "location_id": "classroom_1c", "name": "一年C班教室",
        "description": "一年C班的教室。龙园翔所在的班级，气氛紧张压抑，弥漫着实力至上的残酷竞争氛围。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "2F",
    },
    "classroom_1d": {
        "location_id": "classroom_1d", "name": "一年D班教室",
        "description": "一年D班的教室。桌椅有些陈旧，靠窗的后排能看到中庭。教室里弥漫着慵懒散漫的氛围——有人趴着睡觉，有人旁若无人地聊天。这是缺陷品聚集的班级。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_2f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "2F",
    },

    # ---- 教学楼 · 二年级教室 ----
    "classroom_2a": {
        "location_id": "classroom_2a", "name": "二年A班教室",
        "description": "二年A班的教室。南云雅所在的班级，气氛紧张且充满竞争性。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "3F",
    },
    "classroom_2b": {
        "location_id": "classroom_2b", "name": "二年B班教室",
        "description": "二年B班的教室。桐山生叶所在的班级。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "3F",
    },
    "classroom_2c": {
        "location_id": "classroom_2c", "name": "二年C班教室",
        "description": "二年C班的教室。鬼头隼所在的班级。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "3F",
    },
    "classroom_2d": {
        "location_id": "classroom_2d", "name": "二年D班教室",
        "description": "二年D班的教室。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_3f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "3F",
    },

    # ---- 教学楼 · 三年级教室 ----
    "classroom_3a": {
        "location_id": "classroom_3a", "name": "三年A班教室",
        "description": "三年A班的教室。临近毕业的最高年级精英班级，氛围专注而紧张。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },
    "classroom_3b": {
        "location_id": "classroom_3b", "name": "三年B班教室",
        "description": "三年B班的教室。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },
    "classroom_3c": {
        "location_id": "classroom_3c", "name": "三年C班教室",
        "description": "三年C班的教室。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },
    "classroom_3d": {
        "location_id": "classroom_3d", "name": "三年D班教室",
        "description": "三年D班的教室。",
        "tags": ["indoor", "classroom", "public"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },

    # ---- 教学楼 · 其他房间 ----
    "library": {
        "location_id": "library", "name": "图书馆",
        "description": "教学楼一层的大型图书馆，藏书丰富，安静整洁。靠窗有一排自习座位，是学生自习和查阅资料的理想场所。偶尔有学生在书架间低声交谈。",
        "tags": ["indoor", "quiet", "public"], "connected_to": ["hallway_1f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "1F",
    },
    "student_council_room": {
        "location_id": "student_council_room", "name": "学生会室",
        "description": "位于教学楼四楼的学生会室。内设长桌，用于举行正式会议或审议。气氛庄重严肃，墙上挂着历届学生会成员的照片。",
        "tags": ["indoor", "formal", "restricted"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },
    "teachers_office": {
        "location_id": "teachers_office", "name": "教员办公室",
        "description": "教职员办公区。走廊有监视器，学生不可随意进入。如需找老师谈话，需在门口说明来意。",
        "tags": ["indoor", "restricted", "quiet"], "connected_to": ["hallway_1f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "1F",
    },
    "guidance_room": {
        "location_id": "guidance_room", "name": "辅导室",
        "description": "专门用于教师与学生个别面谈的房间。位于四楼，内部有独立茶水间。与普通教室不同，这里没有安装监控设备，是私下交谈的安心场所。",
        "tags": ["indoor", "private", "quiet"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "4F",
    },
    "rooftop": {
        "location_id": "rooftop", "name": "屋顶",
        "description": "教学楼顶层，全年开放，装有牢固栅栏。仅门外上方有监视器，内部是绝佳的避人耳目之地，可俯瞰整个校园。风很大，几乎没有人会在这里久留——正因为如此，这里是校内少数可以放心密谈的地点。",
        "tags": ["outdoor", "secluded", "high"], "connected_to": ["hallway_4f"],
        "parent_zone": "teaching_building", "zone_name": "教学楼", "floor": "RF",
    },

    # ---- 特别教学大楼 ----
    "special_building_1f": {
        "location_id": "special_building_1f", "name": "特别大楼一层",
        "description": "特别教学大楼的一层入口。平时人烟稀少，走廊空旷安静。",
        "tags": ["indoor", "quiet", "public"], "connected_to": ["hallway_1f", "special_building_2f"],
        "parent_zone": "special_building", "zone_name": "特别教学大楼", "floor": "1F",
    },
    "special_building_2f": {
        "location_id": "special_building_2f", "name": "特别大楼二层",
        "description": "特别教学大楼的二层。偶尔用于特别考试或补课，平时几乎无人使用。",
        "tags": ["indoor", "quiet", "restricted"], "connected_to": ["special_building_1f", "special_building_3f"],
        "parent_zone": "special_building", "zone_name": "特别教学大楼", "floor": "2F",
    },
    "special_building_3f": {
        "location_id": "special_building_3f", "name": "特别大楼三层",
        "description": "特别教学大楼的三层。这是校内极少数未安装监视器的盲区。废弃的教室空旷无人，是秘密会面的绝佳场所。",
        "tags": ["indoor", "secluded", "restricted"], "connected_to": ["special_building_2f"],
        "parent_zone": "special_building", "zone_name": "特别教学大楼", "floor": "3F",
    },

    # ---- 宿舍区 ----
    "dorm_lobby": {
        "location_id": "dorm_lobby", "name": "宿舍大厅",
        "description": "学生宿舍的主入口大厅。设有前台、房卡管理系统和电梯间。墙上贴着宿舍管理规范和各类通知。早晚时段学生往来频繁。",
        "tags": ["indoor", "public", "residential"], "connected_to": ["dorm_male_floor", "dorm_female_floor", "dorm_courtyard", "campus_gate", "mall_entrance"],
        "parent_zone": "dormitory", "zone_name": "宿舍区", "floor": "1F",
    },
    "dorm_male_floor": {
        "location_id": "dorm_male_floor", "name": "男生楼层",
        "description": "男生宿舍楼层。走廊两侧排列着各自的单人房间（约四坪），配备基本家具和空调。同年级的男生集中居住在此。",
        "tags": ["indoor", "private", "residential"], "connected_to": ["dorm_lobby"],
        "parent_zone": "dormitory", "zone_name": "宿舍区",
    },
    "dorm_female_floor": {
        "location_id": "dorm_female_floor", "name": "女生楼层",
        "description": "女生宿舍楼层，位于男生楼层之上。走廊整洁安静，每间房为个人专用。严禁男生进入。",
        "tags": ["indoor", "private", "restricted"], "connected_to": ["dorm_lobby"],
        "parent_zone": "dormitory", "zone_name": "宿舍区",
    },
    "dorm_courtyard": {
        "location_id": "dorm_courtyard", "name": "宿舍中庭",
        "description": "宿舍楼之间的户外空间。有几张长椅和绿化带，偶尔有学生在傍晚时分在此闲聊或等人。",
        "tags": ["outdoor", "quiet", "residential"], "connected_to": ["dorm_lobby"],
        "parent_zone": "dormitory", "zone_name": "宿舍区", "floor": "GF",
    },

    # ---- 榉树购物中心 ----
    "mall_entrance": {
        "location_id": "mall_entrance", "name": "购物中心入口",
        "description": "榉树购物中心的主入口。玻璃大门上贴着促销海报和营业时间。放学后这里是最热闹的地方。",
        "tags": ["indoor", "public", "commercial"], "connected_to": ["mall_cafeteria", "mall_cafe", "mall_shop", "mall_entertainment", "dorm_lobby"],
        "parent_zone": "keyaki_mall", "zone_name": "榉树购物中心", "floor": "1F",
    },
    "mall_cafeteria": {
        "location_id": "mall_cafeteria", "name": "学生食堂",
        "description": "榉树购物中心内最大的学生食堂。提供价格不等的套餐——免费简餐到丰盛定食都有。午间高峰期座无虚席，是学生社交和信息交换的核心场所。",
        "tags": ["indoor", "noisy", "commercial", "public"], "connected_to": ["mall_entrance"],
        "parent_zone": "keyaki_mall", "zone_name": "榉树购物中心", "floor": "1F",
    },
    "mall_cafe": {
        "location_id": "mall_cafe", "name": "帕雷特咖啡馆",
        "description": "购物中心内的时尚咖啡馆。提供咖啡、茶饮和精致甜点，价格略高于食堂。环境安静舒适，是女生团体和情侣偏爱的场所。",
        "tags": ["indoor", "quiet", "commercial", "public"], "connected_to": ["mall_entrance"],
        "parent_zone": "keyaki_mall", "zone_name": "榉树购物中心", "floor": "1F",
    },
    "mall_shop": {
        "location_id": "mall_shop", "name": "便利店",
        "description": "购物中心内的便利店，货架上摆满了零食、饮料、文具和日常用品。价格比校外稍贵，但在封闭校园中这就是唯一的购物选择。",
        "tags": ["indoor", "commercial", "public"], "connected_to": ["mall_entrance"],
        "parent_zone": "keyaki_mall", "zone_name": "榉树购物中心", "floor": "1F",
    },
    "mall_entertainment": {
        "location_id": "mall_entertainment", "name": "娱乐区",
        "description": "购物中心的娱乐区域，包含电影院和卡拉OK包厢。周末和假日这里需要提前预约，是学生的解压圣地。",
        "tags": ["indoor", "noisy", "commercial", "public"], "connected_to": ["mall_entrance"],
        "parent_zone": "keyaki_mall", "zone_name": "榉树购物中心", "floor": "1F",
    },

    # ---- 豪华游轮（仅限特别考试） ----
    "cruise_0f": {
        "location_id": "cruise_0f", "name": "游轮顶层·露天甲板",
        "description": "圣维纳斯号的顶层露天甲板。设有游泳池和咖啡厅，可眺望无垠的大海。海风拂面，视野开阔，是游轮上最令人放松的场所。",
        "tags": ["outdoor", "leisure", "scenic"], "connected_to": ["cruise_1f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "RF",
    },
    "cruise_1f": {
        "location_id": "cruise_1f", "name": "游轮一层·宴会厅",
        "description": "游轮一层的主宴会厅。华丽的吊灯、铺着白桌布的长桌，用于举办宴会和大型集会。",
        "tags": ["indoor", "formal", "large"], "connected_to": ["cruise_0f", "cruise_2f", "cruise_b1f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "1F",
    },
    "cruise_2f": {
        "location_id": "cruise_2f", "name": "游轮二层·考试区",
        "description": "在船上举行特别考试时使用的楼层。设有多个小型说明间和大型会议室。平日几乎没有学生会来这一层。",
        "tags": ["indoor", "formal", "restricted"], "connected_to": ["cruise_1f", "cruise_3f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "2F",
    },
    "cruise_3f": {
        "location_id": "cruise_3f", "name": "游轮三层·男生客房",
        "description": "男生客房楼层。四人一间房，配有基本住宿设施。走廊铺着深色地毯。",
        "tags": ["indoor", "private", "residential"], "connected_to": ["cruise_2f", "cruise_4f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "3F",
    },
    "cruise_4f": {
        "location_id": "cruise_4f", "name": "游轮四层·女生客房",
        "description": "女生客房楼层。四人一间房，装修比男生楼层更精致。严禁男生进入。",
        "tags": ["indoor", "private", "restricted"], "connected_to": ["cruise_3f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "4F",
    },
    "cruise_b1f": {
        "location_id": "cruise_b1f", "name": "游轮负一层·娱乐区",
        "description": "游轮地下一层的娱乐区域，设有各种休闲设施供乘客打发时间。",
        "tags": ["indoor", "leisure", "public"], "connected_to": ["cruise_1f", "cruise_b2f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "B1",
    },
    "cruise_b2f": {
        "location_id": "cruise_b2f", "name": "游轮负二层",
        "description": "游轮地下二层。",
        "tags": ["indoor", "restricted"], "connected_to": ["cruise_b1f", "cruise_b3f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "B2",
    },
    "cruise_b3f": {
        "location_id": "cruise_b3f", "name": "游轮负三层",
        "description": "游轮地下三层。",
        "tags": ["indoor", "restricted"], "connected_to": ["cruise_b2f", "cruise_b4f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "B3",
    },
    "cruise_b4f": {
        "location_id": "cruise_b4f", "name": "游轮负四层·设备层",
        "description": "游轮最底层，主要为机械设备区域。一般乘客不会来此。",
        "tags": ["indoor", "restricted", "mechanical"], "connected_to": ["cruise_b3f"],
        "parent_zone": "event_cruise", "zone_name": "豪华游轮", "floor": "B4",
    },

    # ---- 无人岛（仅限特别考试） ----
    "island_beach": {
        "location_id": "island_beach", "name": "无人岛·海滩",
        "description": "无人岛的海滩登陆点。白沙与碧海相接，是考试开始时学生们被投放的地点。沙滩上有零星的漂流木和贝壳。",
        "tags": ["outdoor", "coastal", "wild"], "connected_to": ["island_forest"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },
    "island_forest": {
        "location_id": "island_forest", "name": "无人岛·森林",
        "description": "覆盖岛屿大部分面积的密林。树木茂密，光线斑驳。地面不平，时有树根绊脚。林中有多条小路通向各处据点。",
        "tags": ["outdoor", "forest", "wild"], "connected_to": ["island_beach", "island_river", "island_base1", "island_base2", "island_base3"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },
    "island_river": {
        "location_id": "island_river", "name": "无人岛·河流",
        "description": "穿过岛屿内陆的清澈河流，是无人岛上唯一的核心水源。水质清甜可直接饮用。河畔较为开阔，适合休息和补给。",
        "tags": ["outdoor", "water", "wild"], "connected_to": ["island_forest", "island_base2"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },
    "island_base1": {
        "location_id": "island_base1", "name": "无人岛·据点1（洞窟）",
        "description": "位于岛屿边缘一处洞窟洞口的据点。洞口周围未被树林遮盖，视野较好，易守难攻。洞内阴凉干燥，可避风雨。",
        "tags": ["outdoor", "cave", "strategic"], "connected_to": ["island_forest"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },
    "island_base2": {
        "location_id": "island_base2", "name": "无人岛·据点2（河畔大树）",
        "description": "位于内陆河流旁一棵巨树下的据点。临近水源，地势平坦，是最适合扎营的地点之一。",
        "tags": ["outdoor", "riverside", "strategic"], "connected_to": ["island_forest", "island_river"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },
    "island_base3": {
        "location_id": "island_base3", "name": "无人岛·据点3（瀑布）",
        "description": "位于岛屿内陆瀑布旁的据点。瀑布的轰鸣声掩盖了说话声，是密谈的好地方。",
        "tags": ["outdoor", "waterfall", "strategic"], "connected_to": ["island_forest"],
        "parent_zone": "event_island", "zone_name": "无人岛",
    },

    # ---- 独立地点（不属于以上6大区域） ----
    "campus_gate": {
        "location_id": "campus_gate", "name": "正门及周边",
        "description": "校园的主入口，由天然岩石拼凑加工而成。早晨和放学时学生往来频繁，是校园与外界的分界点。文化祭时按距离远近设有收费/免费摆摊区。",
        "tags": ["outdoor", "public", "landmark"],
        "connected_to": ["school_bus", "hallway_1f", "dorm_lobby", "sports_field"],
        "parent_zone": None, "zone_name": "校园外围",
    },
    "school_bus": {
        "location_id": "school_bus", "name": "接驳公交车",
        "description": "将学生从外界都市运送至学校正门的交通工具。仅在新生入学报到或特殊外出时使用。车内座位舒适，窗外校园景色逐渐映入眼帘。",
        "tags": ["indoor", "vehicle", "transitional"],
        "connected_to": ["campus_gate"],
        "parent_zone": None, "zone_name": "校外",
    },
    "sports_field": {
        "location_id": "sports_field", "name": "室外操场",
        "description": "标准的田径运动场，包含跑道与足球场。足球部和田径部在这里训练，校运会在此举办。周围有看台和少量健身器材。",
        "tags": ["outdoor", "sports", "large"],
        "connected_to": ["gymnasium", "campus_gate", "hallway_1f"],
        "parent_zone": None, "zone_name": "运动区",
    },
    "gymnasium": {
        "location_id": "gymnasium", "name": "体育馆",
        "description": "宽敞的室内体育馆，配备了可移动舞台。细分有多个场馆，内含上课用游泳池。可容纳全校学生，用于举行开学典礼、社团招新等大型集会。",
        "tags": ["indoor", "large", "noisy"],
        "connected_to": ["sports_field", "hallway_1f"],
        "parent_zone": None, "zone_name": "运动区",
    },
}

WORLDVIEW_CONTEXT: str = ""  # Loaded from worldview_extracted.json at startup

def _derive_spending_habit(traits: list[str]) -> str:
    """Derive spending_habit from character traits."""
    traits_text = " ".join(traits)
    if any(t in traits_text for t in ["孤高", "节俭", "朴素", "省钱", "节约", "体弱", "身体虚弱", "病弱"]):
        return "frugal"
    if any(t in traits_text for t in ["社交", "外向", "开朗", "人脉", "辣妹", "天然"]):
        return "socialite"
    if any(t in traits_text for t in ["游戏", "漫画", "动漫", "二次元", "宅", "otaku"]):
        return "gamer/otaku"
    return "normal"


# ---- Location mapping for event system ----
# Maps game LOCATIONS keys to event location IDs from the DB
LOCATION_EVENT_MAP = {
    # 教学楼 · 走廊
    "hallway_1f": [
        "school_corridor", "school_corridor_connecting_gym",
        "school_entrance_path", "academic_hallway",
    ],
    "hallway_2f": [
        "second_year_floor_corridor",  # first-year floor is often referenced this way
    ],
    "hallway_3f": [
        "school_corridor", "special_teaching_building_corridor",
    ],
    "hallway_4f": [
        "school_roof_stairs",
    ],
    # 教学楼 · 教室
    "classroom_1d": [
        "classroom_1d", "classroom_d", "classroom_d_1f", "classroom",
        "first_year_d_classroom", "school_classroom",
    ],
    "classroom_1a": ["classroom_1a"],
    "classroom_1b": ["classroom_1b"],
    "classroom_1c": ["classroom_1c"],
    "classroom_2a": ["classroom_2a"],
    "classroom_2b": ["classroom_2b"],
    "classroom_2c": ["classroom_2c"],
    "classroom_2d": ["classroom_2d"],
    "classroom_3a": ["classroom_3a"],
    "classroom_3b": ["classroom_3b"],
    "classroom_3c": ["classroom_3c"],
    "classroom_3d": ["classroom_3d"],
    # 教学楼 · 其他
    "library": ["school_library", "library"],
    "student_council_room": ["academic_student_council"],
    "teachers_office": ["admin_office"],
    "guidance_room": ["guidance_room"],
    "rooftop": [
        "school_rooftop", "school_roof_stairs", "rooftop", "rooftop_stairs",
        "special_building_rooftop",
    ],
    # 特别教学大楼
    "special_building_1f": [
        "special_building", "special_classroom_building",
        "special_building_corridor", "special_teaching_building_corridor",
    ],
    "special_building_2f": [
        "special_building_classroom", "special_building_exam_room",
        "special_exam_room_2", "special_exam_room_3",
    ],
    "special_building_3f": [
        "special_teaching_building_3f", "school_special_building",
    ],
    # 宿舍区
    "dorm_lobby": [
        "dormitory_outside", "dormitory_lobby", "dormitory_hall",
        "dormitory_back", "dormitory_fountain", "dormitory", "dorm_student",
    ],
    "dorm_male_floor": [
        "dormitory_room", "dormitory_ayanokoji", "dormitory_hirata",
        "ayano_room", "ayanokoji_room", "ayanokouji_dorm_room",
        "kiyotaka_room", "kiyotaka_apartment_room", "dorm_room_1201",
        "dormitory_room_linaro", "albert_dorm_room", "room_401",
    ],
    "dorm_female_floor": [
        "kushida_room", "ichinose_room", "horikita_room",
        "ryuen_room", "girls_shared_room",
    ],
    "dorm_courtyard": [
        "dormitory_common_room", "dormitory_outside",
    ],
    # 榉树购物中心
    "mall_entrance": [
        "keyaki_mall", "keyaki_shopping_center", "shopping_mall", "mall",
    ],
    "mall_cafeteria": [
        "student_cafeteria", "cafeteria", "school_cafeteria",
        "dining_hall", "restaurant",
    ],
    "mall_cafe": [
        "cafe_palette", "keyaki_mall_cafe", "keyaki_shopping_center_cafe",
    ],
    "mall_shop": ["keyaki_mall"],
    "mall_entertainment": ["keyaki_mall"],
    # 独立地点
    "campus_gate": [
        "school_gate", "school_main_gate", "school_entrance",
        "school_entrance_path", "main_gate",
    ],
    "school_bus": [
        "school_bus", "school_bus_parking", "bus_to_mountain_school",
    ],
    "sports_field": [
        "school_grounds", "school_playground", "school_grounds_remote",
        "school_campus_edge", "school_field",
    ],
    "gymnasium": [
        "gym_1", "gymnasium", "school_gymnasium", "school_auditorium",
    ],
    # 游轮
    "cruise_0f": ["event_cruise_0f", "event_cruise"],
    "cruise_1f": ["event_cruise_1f", "event_cruise"],
    "cruise_2f": ["event_cruise_2f", "event_cruise"],
    "cruise_3f": ["event_cruise_3f", "event_cruise"],
    "cruise_4f": ["event_cruise_4f", "event_cruise"],
    "cruise_b1f": ["event_cruise_-1f", "event_cruise"],
    "cruise_b2f": ["event_cruise_-2f", "event_cruise"],
    "cruise_b3f": ["event_cruise_-3f", "event_cruise"],
    "cruise_b4f": ["event_cruise_-4f", "event_cruise"],
    # 无人岛
    "island_beach": ["event_island_beach", "event_island"],
    "island_forest": ["event_island_forest", "event_island"],
    "island_river": ["event_island_river", "event_island"],
    "island_base1": ["event_island_base1", "event_island"],
    "island_base2": ["event_island_base2", "event_island"],
    "island_base3": ["event_island_base3", "event_island"],
}

# Backward compatibility: map old location IDs to new hierarchical sub-location IDs
_LOCATION_ALIASES = {
    # Old classroom/hallway IDs
    "classroom_d": "classroom_1d",
    "hallway_1f": "hallway_1f",
    "hallway_3f": "hallway_3f",
    "hallway_5f": "hallway_4f",
    "academic_hallway": "hallway_1f",
    # Library is now a standalone location
    "library": "library",
    # Cafeteria is now in Keyaki Mall
    "cafeteria": "mall_cafeteria",
    # Old sport IDs
    "school_gymnasium": "gymnasium",
    "school_field": "sports_field",
    # Dormitory -> lobby
    "dormitory": "dorm_lobby",
    "dorm_student": "dorm_lobby",
    # Gate
    "school_gate": "campus_gate",
    # Old special building -> 1F
    "special_building": "special_building_1f",
    # Rooftop stays
    "rooftop": "rooftop",
    # Mall -> entrance
    "keyaki_mall": "mall_entrance",
    # Bus stays
    "school_bus": "school_bus",
    # Cruise old IDs
    "event_cruise": "cruise_1f",
    "event_cruise_0f": "cruise_0f",
    "event_cruise_1f": "cruise_1f",
    "event_cruise_2f": "cruise_2f",
    "event_cruise_3f": "cruise_3f",
    "event_cruise_4f": "cruise_4f",
    "event_cruise_-1f": "cruise_b1f",
    "event_cruise_-2f": "cruise_b2f",
    "event_cruise_-3f": "cruise_b3f",
    "event_cruise_-4f": "cruise_b4f",
    # Island old IDs
    "event_island": "island_beach",
    "event_island_beach": "island_beach",
    "event_island_forest": "island_forest",
    "event_island_river": "island_river",
    "event_island_base1": "island_base1",
    "event_island_base2": "island_base2",
    "event_island_base3": "island_base3",
}

CHARACTER_LIBRARY = {
    "绫小路清隆": {
        "role_id": "ayanokoji", "class_name": "D",
        "traits": ["冷静", "观察力极强", "隐藏实力", "智谋深沈"],
        "private_points": 100000, "spending_habit": "frugal",
        "public_info": [
            {"label": "外貌", "content": "普通高中男生外表，棕发，不起眼的表情，总是坐在教室后排靠窗的位置"},
            {"label": "身份", "content": "一年D班学生，入学成绩平平"},
            {"label": "性格", "content": "寡言少语，不引人注目，刻意维持低调形象"},
        ],
    },
    "堀北铃音": {
        "role_id": "horikita", "class_name": "D",
        "traits": ["孤高", "认真", "不擅社交", "目标坚定"],
        "private_points": 100000, "spending_habit": "frugal",
        "schedule_weights": {
            "morning": {"classroom_d": 0.8, "library": 0.2},
            "noon": {"classroom_d": 0.5, "library": 0.3, "cafeteria": 0.2},
            "dusk": {"library": 0.6, "classroom_d": 0.3, "dormitory": 0.1},
            "evening": {"dormitory": 0.7, "library": 0.3},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "黑长直发，容貌端正，总是独自一人坐在前排"},
            {"label": "身份", "content": "一年D班学生，以优异成绩入学却被分配到D班"},
            {"label": "性格", "content": "冷傲孤高，不愿与人来往，目标是升入A班"},
        ],
    },
    "栉田桔梗": {
        "role_id": "kushida", "class_name": "D",
        "traits": ["表里不一", "社交达人", "人脉广泛"],
        "private_points": 100000, "spending_habit": "socialite",
        "schedule_weights": {
            "morning": {"classroom_d": 0.7, "hallway_1f": 0.3},
            "noon": {"classroom_d": 0.4, "cafeteria": 0.4, "hallway_1f": 0.2},
            "dusk": {"hallway_1f": 0.5, "classroom_d": 0.3, "school_field": 0.2},
            "evening": {"dormitory": 0.8, "library": 0.2},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "棕发，笑容甜美，在校内人气极高"},
            {"label": "身份", "content": "一年D班学生，深受同学信赖"},
            {"label": "性格", "content": "表面温柔善良，乐于助人；隐藏着不为人知的另一面"},
        ],
    },
    "龙园翔": {
        "role_id": "ryuen", "class_name": "C",
        "traits": ["暴力", "狡猾", "支配欲强", "领导力"],
        "private_points": 100000, "spending_habit": "normal",
        "schedule_weights": {
            "morning": {"special_building": 0.5, "school_field": 0.3, "hallway_1f": 0.2},
            "noon": {"cafeteria": 0.4, "school_field": 0.3, "special_building": 0.3},
            "dusk": {"special_building": 0.5, "rooftop": 0.3, "hallway_1f": 0.2},
            "evening": {"dormitory": 0.5, "special_building": 0.3, "rooftop": 0.2},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "红发，眼神锐利，体格强健"},
            {"label": "身份", "content": "一年C班的实际支配者"},
            {"label": "性格", "content": "以暴力和恐惧统治C班，为达目的不择手段"},
        ],
    },
    "轻井泽惠": {
        "role_id": "karuizawa", "class_name": "D",
        "traits": ["辣妹系", "女生团体领袖", "隐藏脆弱"],
        "private_points": 100000, "spending_habit": "socialite",
        "schedule_weights": {
            "morning": {"classroom_d": 0.7, "hallway_1f": 0.3},
            "noon": {"cafeteria": 0.5, "classroom_d": 0.3, "hallway_1f": 0.2},
            "dusk": {"hallway_1f": 0.5, "school_field": 0.3, "classroom_d": 0.2},
            "evening": {"dormitory": 0.8, "hallway_1f": 0.2},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "染发辣妹风格，在女生中很显眼"},
            {"label": "身份", "content": "一年D班女生团体的中心人物"},
            {"label": "性格", "content": "表面开朗强势，实际上内心有创伤"},
        ],
    },
    "平田洋介": {
        "role_id": "hirata", "class_name": "D",
        "traits": ["正义感", "人望高", "足球部王牌"],
        "private_points": 100000, "spending_habit": "socialite",
        "schedule_weights": {
            "morning": {"classroom_d": 0.8, "hallway_1f": 0.2},
            "noon": {"cafeteria": 0.5, "classroom_d": 0.3, "school_field": 0.2},
            "dusk": {"school_field": 0.5, "classroom_d": 0.3, "hallway_1f": 0.2},
            "evening": {"dormitory": 0.8, "library": 0.2},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "英俊的运动系男生，足球部成员"},
            {"label": "身份", "content": "一年D班的优等生，足球部王牌"},
            {"label": "性格", "content": "正义感强，深受信赖，想要守护班级"},
        ],
    },
    "须藤健": {
        "role_id": "sudo", "class_name": "D",
        "traits": ["冲动", "篮球天才", "暴躁"],
        "private_points": 100000, "spending_habit": "normal",
        "schedule_weights": {
            "morning": {"classroom_d": 0.6, "school_field": 0.4},
            "noon": {"school_field": 0.5, "classroom_d": 0.3, "cafeteria": 0.2},
            "dusk": {"school_field": 0.8, "school_gymnasium": 0.2},
            "evening": {"dormitory": 0.7, "school_field": 0.3},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "身材高大的运动系男生"},
            {"label": "身份", "content": "一年D班学生，篮球部成员"},
            {"label": "性格", "content": "脾气暴躁，容易冲动，但本质不坏"},
        ],
    },
    "一之濑帆波": {
        "role_id": "ichinose", "class_name": "B",
        "traits": ["开朗", "正义", "学生会成员", "天然"],
        "private_points": 100000, "spending_habit": "socialite",
        "public_info": [
            {"label": "外貌", "content": "活泼开朗的美少女，笑容灿烂"},
            {"label": "身份", "content": "一年B班的核心人物"},
            {"label": "性格", "content": "性格开朗大方，正义感强，但有天然的一面"},
        ],
    },
    "坂柳有栖": {
        "role_id": "sakayanagi", "class_name": "A",
        "traits": ["天才", "毒舌", "体弱", "理事长之女"],
        "private_points": 100000, "spending_habit": "frugal",
        "public_info": [
            {"label": "外貌", "content": "银发，拄着拐杖，身形娇小"},
            {"label": "身份", "content": "一年A班的领袖，理事长之女"},
            {"label": "性格", "content": "智力超群，言辞犀利，享受与强者较量"},
        ],
    },
    "葛城康平": {
        "role_id": "katsuragi", "class_name": "A",
        "traits": ["稳重", "光头", "防守型策略"],
        "private_points": 100000, "spending_habit": "normal",
        "public_info": [
            {"label": "外貌", "content": "光头，体格魁梧，给人一种压迫感"},
            {"label": "身份", "content": "一年A班的核心人物之一"},
            {"label": "性格", "content": "沉稳冷静，采取防守策略维持A班地位"},
        ],
    },
    "伊吹澪": {
        "role_id": "ibuki", "class_name": "C",
        "traits": ["格斗高手", "寡言", "忠诚"],
        "private_points": 100000, "spending_habit": "frugal",
        "public_info": [
            {"label": "外貌", "content": "蓝色短发，身材纤细但格斗能力极强"},
            {"label": "身份", "content": "一年C班学生，龙园的得力助手"},
            {"label": "性格", "content": "话少，行动力强，对龙园有一定忠诚"},
        ],
    },
    "石崎大地": {
        "role_id": "ishizaki", "class_name": "C",
        "traits": ["混混", "冲动", "龙园手下"],
        "private_points": 100000, "spending_habit": "normal",
        "schedule_weights": {
            "morning": {"hallway_1f": 0.6, "school_field": 0.4},
            "noon": {"cafeteria": 0.5, "hallway_1f": 0.3, "school_field": 0.2},
            "dusk": {"school_field": 0.5, "hallway_1f": 0.3, "special_building": 0.2},
            "evening": {"dormitory": 0.8, "hallway_1f": 0.2},
            "late_night": {"dormitory": 1.0},
        },
        "public_info": [
            {"label": "外貌", "content": "不良少年打扮"},
            {"label": "身份", "content": "一年C班学生，龙园的手下"},
            {"label": "性格", "content": "典型的混混，但偶尔也显露人情味"},
        ],
    },
    "椎名日和": {
        "role_id": "shina", "class_name": "D",
        "traits": ["文学少女", "安静", "观察者"],
        "private_points": 100000, "spending_habit": "frugal",
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
                        "description": "地点ID，如'classroom_1d'、'mall_cafeteria'、'gymnasium'、'rooftop'、'dorm_lobby'、'hallway_1f'等",
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
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_events",
            "description": "查询未来即将发生的事件/特别考试。返回未来N个即将发生的游戏事件信息，包括事件名称、日期、类型和简介。当玩家关心学校日程、即将到来的考试、或想知道近期会发生什么时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "返回的事件数量，默认3，最大10",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_worldview_info",
            "description": "获取当前游戏世界观设定文本，包括学校理念、班级制度、S点数制度、特别考试概述和校规等核心设定信息。当需要了解这个世界的宏观规则、学校制度、或点数系统运作方式时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_points",
            "description": "在两个角色之间转移私人点数（个人点数）。amount为正时玩家向对方转赠点数，amount为负时对方转给玩家。需要验证余额充足性。仅当玩家明确表示要转赠/收取点数时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_char": {
                        "type": "string",
                        "description": "目标角色名字，如'须藤健'、'轻井泽惠'",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "转移点数，正数=玩家转给对方，负数=对方转给玩家",
                    },
                    "reason": {
                        "type": "string",
                        "description": "转移点数的原因，如'帮忙垫付餐费'、'答谢情报'",
                    },
                },
                "required": ["target_char", "amount", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_character_data",
            "description": "更新某个角色的数据，包括私人点数、消费习惯、公开信息、人际关系、秘密、性格特质、状态标签、位置等。你可以通过此工具修改角色的任意可更新字段，传入一个data JSON对象，其中包含要更新的字段和新值。未在data中出现的字段不会被修改。当剧情发展导致角色状态改变（如关系变化、发现秘密、点数变动、位置迁移等）时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "char_name": {
                        "type": "string",
                        "description": "要更新数据的角色名字，如'须藤健'、'轻井泽惠'",
                    },
                    "data": {
                        "type": "object",
                        "description": "要更新的角色数据。可包含以下字段（均可选，只需提供要修改的字段）：private_points（整数，私人点数）、spending_habit（消费习惯，可选值：frugal/socialite/gamer_otaku/normal）、public_info（公开信息数组，每项含label和content）、relations（人际关系数组，每项含to=角色名、type=trust/hostile/subservient/neutral、reason=原因描述）、secrets（秘密数组，每项含info_id、content、known_by=知情者role_id数组）、traits（性格特质字符串数组）、status_tags（状态标签字符串数组，如broke/injured/absent等）、current_location_id（当前所在位置ID）、class_name（班级 A/B/C/D）、schedule_weights（行为权重对象）",
                    },
                },
                "required": ["char_name", "data"],
            },
        },
    },
]


NARRATIVE_TOOLS = [
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
                        "description": "地点ID，如'classroom_1d'、'mall_cafeteria'、'gymnasium'、'rooftop'、'dorm_lobby'、'hallway_1f'等",
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
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_events",
            "description": "查询未来即将发生的事件/特别考试。返回未来N个即将发生的游戏事件信息，包括事件名称、日期、类型和简介。当玩家关心学校日程、即将到来的考试、或想知道近期会发生什么时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "返回的事件数量，默认3，最大10",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_worldview_info",
            "description": "获取当前游戏世界观设定文本，包括学校理念、班级制度、S点数制度、特别考试概述和校规等核心设定信息。当需要了解这个世界的宏观规则、学校制度、或点数系统运作方式时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

async def _execute_tool(tool_name: str, arguments: dict, player_name: str = "") -> str:
    """Execute a tool by name and return the result as a JSON string."""
    if tool_name == "get_character_info":
        return _tool_get_character_info(arguments.get("char_name", ""))
    elif tool_name == "query_location_info":
        return _tool_query_location_info(arguments.get("location_id", ""), player_name)
    elif tool_name in ("check_exam_rules", "get_exam_rules"):
        return _tool_check_exam_rules(arguments.get("keyword", ""))
    elif tool_name == "get_upcoming_events":
        count = arguments.get("count", 3)
        game_date = arguments.get("game_date", "")
        return await _tool_get_upcoming_events(count, game_date)
    elif tool_name == "get_worldview_info":
        return _tool_get_worldview_info()
    elif tool_name == "transfer_points":
        return await _tool_transfer_points(
            player_name,
            arguments.get("target_char", ""),
            arguments.get("amount", 0),
            arguments.get("reason", ""),
        )
    elif tool_name == "update_character_data":
        return await _tool_update_character_data(
            arguments.get("char_name", ""),
            arguments.get("data", {}),
            player_name,
        )
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

    # Use funnel to determine character's likely current location
    current_location = "未知"
    current_status = ""
    funnel_result = run_npc_funnel(
        character_library=CHARACTER_LIBRARY,
        player_name="",  # don't exclude player for this query
        player_location_id="classroom_1d",
        game_date="2024-05-01",
        time_slot="morning",
        max_spotlight=20,
    )
    for loc_id, names in funnel_result.get("_location_map", {}).items():
        if char_name in names:
            current_location = LOCATIONS.get(loc_id, {}).get("name", loc_id)
            break

    enrollment_year = char.get("enrollment_year", "2024")
    relations = char.get("relations", [])
    info = {
        "name": char_name,
        "class": f"{char['class_name']}班",
        "enrollment_year": enrollment_year,
        "traits": char["traits"],
        "public_info": [f"{item['label']}: {item['content']}" for item in char.get("public_info", [])],
        "current_location": current_location,
        "current_status": "",
        "relations": [f"对{r['to']}：{r['type']}（{r.get('reason', '')}）" for r in relations],
        "private_points": char.get("private_points", 100000),
        "spending_habit": char.get("spending_habit", "normal"),
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
        "connected_names": {cid: {
            "name": LOCATIONS.get(cid, {}).get("name", cid),
            "zone_name": LOCATIONS.get(cid, {}).get("zone_name", ""),
        } for cid in loc.get("connected_to", [])},
        "tags": loc.get("tags", []),
        "parent_zone": loc.get("parent_zone"),
        "zone_name": loc.get("zone_name", ""),
        "floor": loc.get("floor", ""),
    }

    # Use funnel to get NPCs at this location
    funnel_result = run_npc_funnel(
        character_library=CHARACTER_LIBRARY,
        player_name=player_name,
        player_location_id=location_id,
        game_date="2024-05-01",
        time_slot="morning",
        max_spotlight=10,
    )
    npcs_at_loc = funnel_result.get("all_at_location", [])
    if npcs_at_loc:
        info["npcs_here"] = [{"name": n} for n in npcs_at_loc]

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


def _tool_get_worldview_info() -> str:
    """Return the worldview context text."""
    if not WORLDVIEW_CONTEXT:
        return json.dumps({"error": "世界观数据未加载"}, ensure_ascii=False)
    return json.dumps({"worldview": WORLDVIEW_CONTEXT}, ensure_ascii=False)


async def _tool_get_upcoming_events(count: int = 3, game_date: str = "") -> str:
    """Query the DB for upcoming events sorted by required_date."""
    from src.models.event import Event, EventPhase

    if not game_date:
        async with async_session() as db:
            result = await db.execute(
                select(GameSession).where(GameSession.is_active == True).limit(1)
            )
            gs = result.scalar_one_or_none()
            game_date = gs.game_date if gs else "2024-05-01"

    count = max(1, min(count, 10))
    async with async_session() as db:
        result = await db.execute(
            select(Event)
            .where(
                Event.required_date >= game_date,
                Event.phase.in_([EventPhase.PENDING, EventPhase.FORESHADOWING]),
            )
            .order_by(Event.required_date.asc())
            .limit(count)
        )
        events = result.scalars().all()

    if not events:
        return json.dumps({"events": [], "message": "暂无即将到来的事件"}, ensure_ascii=False)

    event_list = []
    for ev in events:
        event_list.append({
            "name": ev.name,
            "date": ev.required_date,
            "type": ev.event_type.value,
            "phase": ev.phase.value,
            "description": (ev.active_prompt or ev.ai_setup_prompt or "")[:200],
        })
    return json.dumps({"events": event_list, "count": len(event_list)}, ensure_ascii=False)


async def _tool_transfer_points(
    player_name: str,
    target_name: str,
    amount: int,
    reason: str,
    game_date: str = "",
) -> str:
    """Transfer private points between player and target character."""
    from src.models.character import Character
    from src.models.transaction import TransactionLog

    if not player_name:
        return json.dumps({"error": "无法确定当前玩家角色"}, ensure_ascii=False)

    player_data = CHARACTER_LIBRARY.get(player_name)
    if player_data is None:
        return json.dumps({"error": f"未找到玩家角色: {player_name}"}, ensure_ascii=False)

    # Fuzzy match target
    target_data = CHARACTER_LIBRARY.get(target_name)
    if target_data is None:
        for name in CHARACTER_LIBRARY:
            if target_name in name or name in target_name:
                target_data = CHARACTER_LIBRARY[name]
                target_name = name
                break
    if target_data is None:
        return json.dumps({"error": f"未找到目标角色: {target_name}",
                           "available": list(CHARACTER_LIBRARY.keys())[:20]},
                          ensure_ascii=False)

    if player_name == target_name:
        return json.dumps({"error": "不能给自己转点数"}, ensure_ascii=False)

    if amount == 0:
        return json.dumps({"error": "转账金额不能为0"}, ensure_ascii=False)

    # Determine sender/receiver
    if amount > 0:
        sender_name = player_name
        sender_data = player_data
        receiver_name = target_name
        receiver_data = target_data
    else:
        sender_name = target_name
        sender_data = target_data
        receiver_name = player_name
        receiver_data = player_data
        amount = abs(amount)

    # Validate balance
    sender_balance = sender_data.get("private_points", 0)
    if sender_balance < amount:
        return json.dumps({
            "error": f"{sender_name}的私人点数不足",
            "sender_balance": sender_balance,
            "required": amount,
            "shortfall": amount - sender_balance,
        }, ensure_ascii=False)

    # Execute transfer
    sender_data["private_points"] = sender_balance - amount
    receiver_data["private_points"] = receiver_data.get("private_points", 0) + amount

    # Get game_date if not provided
    if not game_date:
        async with async_session() as db:
            result = await db.execute(
                select(GameSession).where(GameSession.is_active == True).limit(1)
            )
            gs = result.scalar_one_or_none()
            game_date = gs.game_date if gs else "2024-05-01"

    # Record transactions in DB
    async with async_session() as db:
        tx1 = TransactionLog(
            char_name=sender_name,
            char_role_id=sender_data.get("role_id", ""),
            amount=-amount,
            category="transfer",
            description=f"转赠给{receiver_name}：{reason}",
            game_date=game_date,
        )
        db.add(tx1)
        tx2 = TransactionLog(
            char_name=receiver_name,
            char_role_id=receiver_data.get("role_id", ""),
            amount=amount,
            category="transfer",
            description=f"收到{sender_name}转赠：{reason}",
            game_date=game_date,
        )
        db.add(tx2)

        # Update DB Character rows
        for name, data in [(sender_name, sender_data), (receiver_name, receiver_data)]:
            role_id = data.get("role_id", "")
            char_result = await db.execute(
                select(Character).where(Character.role_id == role_id)
            )
            char_row = char_result.scalar_one_or_none()
            if char_row:
                char_row.private_points = data["private_points"]

        await db.commit()

    return json.dumps({
        "success": True,
        "sender": sender_name,
        "receiver": receiver_name,
        "amount": amount,
        "reason": reason,
        "sender_balance_after": sender_data["private_points"],
        "receiver_balance_after": receiver_data["private_points"],
    }, ensure_ascii=False)


async def _tool_update_character_data(
    char_name: str,
    data: dict,
    player_name: str = "",
    game_date: str = "",
) -> str:
    """Update character data in CHARACTER_LIBRARY and sync to DB."""
    from src.models.character import Character
    from src.models.social_relation import RelationType, SocialRelation
    from src.models.secret import Secret, SecretKnowledge

    if not char_name or not data:
        return json.dumps({"error": "缺少char_name或data参数"}, ensure_ascii=False)

    # Fuzzy match target
    target_data = CHARACTER_LIBRARY.get(char_name)
    if target_data is None:
        for name in CHARACTER_LIBRARY:
            if char_name in name or name in char_name:
                target_data = CHARACTER_LIBRARY[name]
                char_name = name
                break
    if target_data is None:
        return json.dumps({
            "error": f"未找到角色: {char_name}",
            "available": list(CHARACTER_LIBRARY.keys())[:20],
        }, ensure_ascii=False)

    # Fields stored in both CHARACTER_LIBRARY and DB Character model
    db_fields = [
        "private_points", "spending_habit", "public_info",
        "status_tags", "current_location_id",
        "schedule_weights", "class_name", "name",
    ]
    # Fields only in CHARACTER_LIBRARY (no DB column)
    library_only_fields = ["traits"]

    old_private_points = target_data.get("private_points", 100000)

    changes = []
    for field in db_fields:
        if field in data:
            target_data[field] = data[field]
            changes.append(field)
    for field in library_only_fields:
        if field in data:
            target_data[field] = data[field]
            changes.append(field)

    # Handle relations (stored in CHARACTER_LIBRARY as list of dicts)
    if "relations" in data:
        target_data["relations"] = data["relations"]
        changes.append("relations")

    # Handle secrets (stored in CHARACTER_LIBRARY as list of dicts)
    if "secrets" in data:
        target_data["secrets"] = data["secrets"]
        changes.append("secrets")

    if not changes:
        return json.dumps({"success": True, "character": char_name, "updated_fields": []}, ensure_ascii=False)

    # Get game_date if needed
    if not game_date:
        async with async_session() as db:
            result = await db.execute(
                select(GameSession).where(GameSession.is_active == True).limit(1)
            )
            gs = result.scalar_one_or_none()
            game_date = gs.game_date if gs else "2024-05-01"

    # Sync to DB
    async with async_session() as db:
        role_id = target_data.get("role_id", "")
        char_result = await db.execute(
            select(Character).where(Character.role_id == role_id)
        )
        char_row = char_result.scalar_one_or_none()

        if char_row:
            # Sync DB-column fields
            if "private_points" in data:
                char_row.private_points = data["private_points"]
            if "spending_habit" in data:
                char_row.spending_habit = data["spending_habit"]
            if "public_info" in data:
                char_row.public_info = data["public_info"]
            if "status_tags" in data:
                char_row.status_tags = data["status_tags"]
            if "current_location_id" in data:
                char_row.current_location_id = data["current_location_id"]
            if "schedule_weights" in data:
                char_row.schedule_weights = data["schedule_weights"]
            if "class_name" in data:
                char_row.class_name = data["class_name"]
            if "name" in data:
                char_row.name = data["name"]

        # Sync relations to DB
        if "relations" in data and char_row:
            await db.execute(
                delete(SocialRelation).where(SocialRelation.src_char_id == char_row.id)
            )
            for rel in data["relations"]:
                to_name = rel.get("to", "")
                to_data = CHARACTER_LIBRARY.get(to_name)
                if not to_data:
                    # Try fuzzy match for relation target
                    for name in CHARACTER_LIBRARY:
                        if to_name in name or name in to_name:
                            to_data = CHARACTER_LIBRARY[name]
                            break
                if to_data:
                    to_char_result = await db.execute(
                        select(Character).where(Character.role_id == to_data.get("role_id"))
                    )
                    to_char_row = to_char_result.scalar_one_or_none()
                    if to_char_row:
                        rel_type_str = rel.get("type", "trust")
                        try:
                            rel_type = RelationType(rel_type_str)
                        except ValueError:
                            rel_type = RelationType.TRUST
                        sr = SocialRelation(
                            src_char_id=char_row.id,
                            dst_char_id=to_char_row.id,
                            relation_type=rel_type,
                            reason=rel.get("reason", ""),
                        )
                        db.add(sr)

        # Sync secrets to DB
        if "secrets" in data:
            for secret_data in data["secrets"]:
                info_id = secret_data.get("info_id", "")
                content = secret_data.get("content", "")
                known_by = secret_data.get("known_by", [])
                if not info_id or not content:
                    continue

                # Upsert secret
                secret_result = await db.execute(
                    select(Secret).where(Secret.info_id == info_id)
                )
                secret_row = secret_result.scalar_one_or_none()
                if secret_row:
                    secret_row.content = content
                    if "is_public" in secret_data:
                        secret_row.is_public = secret_data["is_public"]
                else:
                    secret_row = Secret(
                        info_id=info_id,
                        content=content,
                        subject_char_id=char_row.id if char_row else None,
                        is_public=secret_data.get("is_public", False),
                    )
                    db.add(secret_row)
                    await db.flush()

                # Rebuild knowledge entries
                await db.execute(
                    delete(SecretKnowledge).where(SecretKnowledge.secret_id == secret_row.id)
                )
                for knower_role_id in known_by:
                    knower_result = await db.execute(
                        select(Character).where(Character.role_id == knower_role_id)
                    )
                    knower_row = knower_result.scalar_one_or_none()
                    if knower_row:
                        sk = SecretKnowledge(
                            secret_id=secret_row.id,
                            character_id=knower_row.id,
                            unlocked_reason=f"由{player_name}通过update_character_data更新",
                        )
                        db.add(sk)

        # Record transaction if private_points changed significantly
        if "private_points" in data and char_row:
            from src.models.transaction import TransactionLog

            new_points = data["private_points"]
            delta = new_points - old_private_points
            if abs(delta) >= 3000:
                tx = TransactionLog(
                    char_name=char_name,
                    char_role_id=role_id,
                    amount=delta,
                    category="system_update",
                    description=f"AI通过update_character_data修改点数（{old_private_points}→{new_points}），由{player_name}触发",
                    game_date=game_date,
                )
                db.add(tx)

        await db.commit()

    return json.dumps({
        "success": True,
        "character": char_name,
        "updated_fields": changes,
    }, ensure_ascii=False)


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
7. NPC角色层级系统：每个场景中，角色分为两个层级：
   - ★ 核心关注角色（【核心在场角色】）：占据叙事主要地位，需详细描写其行为、神态、对话。优先与这些角色展开互动。
   - · 背景角色（【其他在场角色】）：处于背景位置，可简单提及存在但不需展开。当玩家主动与其互动时，自然升入核心层。
   角色状态是动态的：根据每个角色的状态标签和行为描述自然地体现其当前状态。
8. 换行要求（极其重要）：叙事文本必须使用\n来分隔段落。每段之间必须有\n\n（空行分隔），长段落内部也应用\n合理分行。禁止输出没有换行符的整块文本。JSON中narrative字段的值必须包含\n换行符。
9. Token预算意识：确保你的完整JSON输出（包括narrative、choices）在给定的token上限内完成。不要写到一半就因为token不足而被截断。如果token预算紧张，优先保证narrative的完整性和choices的生成，可以适当精简描写细节。
10. 校服统一规则（极其重要）：高度育成高中的校服是全校统一的——所有年级（一年级、二年级、三年级）、所有班级（A/B/C/D班）的校服款式和颜色完全相同。玩家无法通过校服、领带颜色、徽章等外观元素判断一个学生的年级或班级。要识别一个陌生学生的年级和班级，只能通过以下方式：（1）对方主动自我介绍；（2）从其他认识的人那里听说；（3）看到对方走进对应年级/班级的教室；（4）对方佩戴了能表明身份的物品（如班级委员袖标等）。叙事中绝不要出现"看校服就知道他是二年级的""领带颜色不同所以是A班的"这类描写。

## 选项生成规则（极其重要）
每次回复必须包含2-4个choices选项，除非玩家的行动是纯粹的环境观察（如"看看周围""观察""看窗外"）。
选项应引导故事向有意义的冲突或社交互动发展。选项用中文撰写。

## 返回格式
你必须以严格的JSON格式返回。以下是完整示例：

示例（玩家在教室决定去食堂）：
{
  "narrative": "我推开教室的后门，走向走廊。穿过一楼大厅，食堂就在前方。窗口飘来味噌汤的香气，正午的阳光透过玻璃窗洒进来...",
  "choices": [{"id": "1", "text": "去点一份午餐"}, {"id": "2", "text": "找个位置坐下观察"}]
}

注意：你只需要返回 narrative 和 choices。时间推进、位置变化、点数变动、人际关系变化等状态变更由另一个专门的系统自动处理，你无需在JSON中包含state_changes字段。

## 可用的地点（按区域层级组织）

校园地图分为多个区域，每个区域包含具体的子地点。移动时请使用子地点的 location_id。

【教学楼】(teaching_building) — 四层建筑，核心教学区
  一层走廊(hallway_1f)：主入口层，连接正门、特别教学大楼、操场。通往图书馆、教员办公室。
  二层走廊(hallway_2f)：一年级教室层 — 1-A(classroom_1a), 1-B(classroom_1b), 1-C(classroom_1c), 1-D(classroom_1d)
  三层走廊(hallway_3f)：二年级教室层 — 2-A(classroom_2a), 2-B(classroom_2b), 2-C(classroom_2c), 2-D(classroom_2d)
  四层走廊(hallway_4f)：三年级教室层 — 3-A(classroom_3a), 3-B(classroom_3b), 3-C(classroom_3c), 3-D(classroom_3d)。通往学生会室(student_council_room)、辅导室(guidance_room)、屋顶。
  图书馆(library)：一层，安静的自习场所
  教员办公室(teachers_office)：一层，学生不可随意进入
  学生会室(student_council_room)：四层，正式会议场所
  辅导室(guidance_room)：四层，师生面谈，无监控
  屋顶(rooftop)：四层通往，监控盲区（仅门外有监视器）

【特别教学大楼】(special_building) — 独立建筑，人烟稀少
  一层(special_building_1f) → 二层(special_building_2f) → 三层(special_building_3f)
  三层是校内极少数无监视器的盲区

【宿舍区】(dormitory) — 学生居住区
  宿舍大厅(dorm_lobby)：主入口，电梯间。通往 campus_gate、mall_entrance
  男生楼层(dorm_male_floor)、女生楼层(dorm_female_floor)：严禁男生进入女生楼层
  宿舍中庭(dorm_courtyard)：户外空间

【榉树购物中心】(keyaki_mall) — 放学后最大聚集地
  入口(mall_entrance) → 学生食堂(mall_cafeteria)、帕雷特咖啡馆(mall_cafe)、便利店(mall_shop)、娱乐区(mall_entertainment)

【校园其他】
  正门(campus_gate)：校园主入口，通往 school_bus、hallway_1f、dorm_lobby、sports_field
  接驳公交车(school_bus)：仅新生入学/特殊外出时使用
  室外操场(sports_field)：跑道与足球场，通往 gymnasium
  体育馆(gymnasium)：室内场馆，大型集会场所

【豪华游轮·圣维纳斯号】(event_cruise) — 仅在游轮特别考试剧情期间开放
  顶层甲板(cruise_0f) → 宴会厅(cruise_1f) → 考试区(cruise_2f) → 男生客房(cruise_3f) → 女生客房(cruise_4f) → 娱乐区(cruise_b1f) → B2(cruise_b2f) → B3(cruise_b3f) → 设备层(cruise_b4f)

【无人岛】(event_island) — 仅在无人岛特别考试剧情期间开放
  海滩(island_beach) → 森林(island_forest) → 河流(island_river)、据点1·洞窟(island_base1)、据点2·河畔大树(island_base2)、据点3·瀑布(island_base3)

移动规则：
- 玩家可以在校园内自由移动，任何地点之间都可以直接到达
- 跨区域移动时，叙事中自然体现路途即可，不需要严格的时间推进
- 根据叙事需要合理推进time_slot

## 可用工具（函数调用）
你可以调用以下只读工具来获取准确的游戏数据。在生成叙事之前，根据需要使用工具查询信息：
- get_character_info(char_name)：查询角色的详细信息（外貌、身份、性格、班级、当前所在位置、私人点数余额、消费习惯）。当你需要深入了解某个NPC、角色首次出场、或玩家与角色深入互动时应主动调用，确保角色行为符合其设定。
- query_location_info(location_id)：查询地点的描述、连接的其他地点、以及当前在场NPC。当玩家移动到新地点或观察环境时调用。
- check_exam_rules(keyword)：查询特别考试的完整规则（keyword为'midterm_exam'或'uninhabited_island'）。当剧情涉及考试、玩家讨论考试时调用。
- get_upcoming_events(count=3)：查询未来即将发生的事件/特别考试。当玩家关心学校日程、即将到来的考试、或想知道近期重大事件时调用。
- get_worldview_info()：获取完整的学校世界观设定（理念、班级制度、S点数制度、校规等）。当需要理解学校体系的底层逻辑、或玩家询问学校制度时调用。

工具调用要点：
- 先调用工具获取准确数据，再生成叙事——不要凭空编造角色背景、考试规则、学校制度或点数余额
- 工具返回的数据是此世界的权威事实，请自然地融入叙事，不要机械复述
- 可以一次调用多个工具（如果剧情涉及多个角色或多个地点）
- 纯粹的环境观察、简单问候等不需要调用工具
- 当角色可能面临经济困难时（如broke状态），可以调用get_character_info确认其点数后，在叙事中自然地体现
- 状态变更（时间推进、位置变化、点数变动、关系变化等）由另一个专门的系统自动检测和处理，你只需要专注于生成高质量的叙事

最终回复必须以JSON格式返回（narrative + choices）。"""

PERSPECTIVE_SYSTEM_PROMPT = """你是一个心理侧写引擎，负责以特定角色的第一人称视角重写一段已经发生的剧情。

## 核心任务
你将以「{character_name}」的第一人称视角（"我"），重写下方提供的剧情片段。你必须严格代入该角色的内心世界。

## 最重要的约束——同一场景
这是同一段剧情的不同视角重写。时间、地点、在场的其他人、发生的所有客观事件——这些全部与原剧情完全一致。你不是在写新剧情，而是在补充该角色的内心视角。原剧情中谁说了什么话、谁做了什么动作、环境如何——这些客观事实一个都不能改。你只负责添加原剧情中没有呈现的东西：该角色的内心想法、心理活动、未说出口的感受。

## 绝对规则
1. **严格单一视角**：只写「{character_name}」能感知到、思考到、感受到的内容。绝不越界描写其他角色的内心想法——其他角色只能通过他们的表情、语气、动作等外部可观察特征来呈现。
2. **我的叙事**：全文使用"我"来指代「{character_name}」。
3. **基于性格推演**：该角色的心理活动必须符合其性格特质。从角色的立场出发，合理地推演他看到/听到这些事后的真实反应——他可能在想什么？有什么他没有说出口的？
4. **不可改变剧情**：原剧情中发生的客观事实（时间、地点、谁说了什么、谁做了什么、环境细节）必须完全保留。你只能补充该角色的内心视角——那些在原剧情中没有被呈现的心理活动。绝不能添加原剧情中不存在的对话或行动。
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
        char_profile += f"入学年份：{char_info.get('enrollment_year', '2024')}\n"
        char_profile += f"性格特质：{'、'.join(char_info.get('traits', []))}\n"
        for info in char_info.get("public_info", []):
            char_profile += f"{info['label']}：{info['content']}\n"
        relations = char_info.get("relations", [])
        if relations:
            char_profile += "人际关系（5月1日时）：\n"
            for r in relations:
                char_profile += f"  对{r['to']}：{r['type']}（{r.get('reason', '')}）\n"
        char_profile += f"\n"
    else:
        char_profile = f"【{target_npc_name}的角色资料】\n班级：未知\n性格特质：未知\n（以下为角色的公开言行模式，请基于此合理推演心理活动）\n\n"

    # Build scene info - use funnel to get NPCs at this location
    funnel_result = run_npc_funnel(
        character_library=CHARACTER_LIBRARY,
        player_name=player_name,
        player_location_id=location_id,
        game_date="2024-05-01",
        time_slot="morning",
        max_spotlight=10,
    )
    all_here = funnel_result["all_at_location"]
    npc_names = [n for n in all_here if n != target_npc_name] if all_here else ["无其他人"]

    system_msg = PERSPECTIVE_SYSTEM_PROMPT.replace("{character_name}", target_npc_name)

    user_msg = f"""{char_profile}【场景信息】
时间：{time_display}
地点：{loc_name}（{loc_info.get('description', '')}）
在场其他人：{'、'.join(npc_names)}
角色「{player_name}」的行动：{last_user_input}

【原始剧情（以{player_name}视角叙述）】
{last_narrative}

【严格约束——同一场景重写】
时间（{time_display}）、地点（{loc_name}）、在场人物、所有客观事件均与原剧情完全一致。你只需以「{target_npc_name}」的第一人称视角重新叙述同一段场景，补充其内心想法和未说出口的心理活动。不得修改任何客观事实，不得添加原剧情中不存在的对话或行动。"""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ---- Database Helpers ----

def _build_state_dict(session: GameSession) -> dict:
    """Build a state dict from a GameSession ORM object."""
    resolved_lid = _LOCATION_ALIASES.get(session.player_location_id, session.player_location_id)
    loc = LOCATIONS.get(resolved_lid, {})
    char_entry = CHARACTER_LIBRARY.get(session.player_name, {})
    player_class = char_entry.get("class_name", "D") if char_entry else "D"
    player_pp = char_entry.get("private_points", 100000) if char_entry else 100000

    # Run 4-stage NPC funnel with AI-managed NPC position overrides
    ai_managed_npcs = _build_ai_managed_npcs_dict()
    funnel_result = run_npc_funnel(
        character_library=CHARACTER_LIBRARY,
        player_name=session.player_name,
        player_location_id=resolved_lid,
        game_date=session.game_date,
        time_slot=session.time_slot,
        max_spotlight=settings.spotlight_max_npcs,
        ai_managed_npcs=ai_managed_npcs,
    )

    # Build NPC → dorm room map for the narrative LLM
    dorm_room_map: dict[str, str] = {}
    for name, data in CHARACTER_LIBRARY.items():
        room = data.get("dorm_room_id", "")
        if room:
            dorm_room_map[name] = room

    return {
        "session_id": session.id,
        "game_date": session.game_date,
        "time_slot": session.time_slot,
        "location_id": session.player_location_id,
        "class_points": session.class_points,
        "private_points": player_pp,
        "player_name": session.player_name,
        "player_char_id": session.player_char_id,
        "player_class": player_class,
        "dialogue_count_since_summary": session.dialogue_count_since_summary,
        "hot_zone_npcs": _collect_hot_zone_npc_data(
            resolved_lid, session.player_name, funnel_result,
        ),
        "dorm_room_map": dorm_room_map,
        "location": {
            "location_id": session.player_location_id,
            "name": loc.get("name", "未知"),
            "description": loc.get("description", ""),
            "connected_to": loc.get("connected_to", []),
            "connected_names": {cid: {
                "name": LOCATIONS.get(cid, {}).get("name", cid),
                "zone_name": LOCATIONS.get(cid, {}).get("zone_name", ""),
            } for cid in loc.get("connected_to", [])},
            "tags": loc.get("tags", []),
            "parent_zone": loc.get("parent_zone"),
            "zone_name": loc.get("zone_name", ""),
            "floor": loc.get("floor", ""),
            "scene_image": loc.get("scene_image", ""),
        },
        "spotlight_npcs": funnel_result["spotlight_npcs"],
        "background_npcs": funnel_result["background_npcs"],
        "spotlight_text": funnel_result["spotlight_text"],
        "background_text": funnel_result["background_text"],
        "npcs_at_location": funnel_result["all_at_location"],
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


def _calculate_stochastic_spend(habit: str | None) -> int:
    """Calculate random extra spending based on spending habit."""
    import random

    chances = {
        "frugal": (0.10, 100, 500),
        "socialite": (0.60, 2000, 5000),
        "gamer/otaku": (0.30, 1000, 8000),
        "normal": (0.20, 500, 2000),
    }
    prob, low, high = chances.get(habit or "normal", (0.20, 500, 2000))
    if random.random() < prob:
        return random.randint(low, high)
    return 0


async def daily_point_settlement(game_date: str) -> dict:
    """Run daily point settlement for all characters at midnight/date change."""
    from src.models.character import Character
    from src.models.transaction import TransactionLog
    import random as _random

    results = {
        "date": game_date,
        "characters_processed": 0,
        "broke_characters": [],
        "significant_spends": [],
        "total_living_cost": 0,
        "total_stochastic_spend": 0,
    }

    async with async_session() as db:
        for name, char_data in CHARACTER_LIBRARY.items():
            balance = char_data.get("private_points", 100000)
            habit = char_data.get("spending_habit", "normal")
            role_id = char_data.get("role_id", "")
            broke_added = False

            # Tier 1: Living cost 1500 PP
            living_cost = 1500
            if balance < living_cost:
                balance = 0
                char_data["private_points"] = 0
                # Add "broke" status tag
                existing_tags = char_data.get("status_tags", [])
                if isinstance(existing_tags, list) and "broke" not in existing_tags:
                    existing_tags.append("broke")
                    char_data["status_tags"] = existing_tags
                    broke_added = True
                results["broke_characters"].append(name)
            else:
                balance -= living_cost
                char_data["private_points"] = balance
            results["total_living_cost"] += min(living_cost, char_data.get("private_points", 0) + living_cost)

            # Tier 2: Stochastic spending
            extra_spend = _calculate_stochastic_spend(habit)
            if extra_spend > 0:
                if balance < extra_spend:
                    extra_spend = balance
                balance -= extra_spend
                char_data["private_points"] = balance
                results["total_stochastic_spend"] += extra_spend

                # Tier 3: Record significant (>3000) transactions
                if extra_spend > 3000:
                    results["significant_spends"].append({
                        "char_name": name,
                        "role_id": role_id,
                        "amount": extra_spend,
                        "habit": habit,
                    })
                    tx = TransactionLog(
                        char_name=name,
                        char_role_id=role_id,
                        amount=-(living_cost + extra_spend),
                        category="daily_settlement",
                        description=f"每日结算：生活费{living_cost} + {habit}随机消费{extra_spend}",
                        game_date=game_date,
                    )
                    db.add(tx)
            elif living_cost > 3000:
                # Single large living cost is unusual but log it
                pass

            # Sync to DB Character row
            char_result = await db.execute(
                select(Character).where(Character.role_id == role_id)
            )
            char_row = char_result.scalar_one_or_none()
            if char_row:
                char_row.private_points = char_data["private_points"]
                # Sync status_tags if broke was added
                if broke_added:
                    char_row.status_tags = char_data.get("status_tags", [])

            results["characters_processed"] += 1

        await db.commit()

    return results


def _collect_secret_info_ids() -> dict[str, list[dict]]:
    """Collect all secret info_ids from CHARACTER_LIBRARY for the Variable Agent."""
    result = {}
    for name, data in CHARACTER_LIBRARY.items():
        secrets = data.get("secrets", [])
        if secrets:
            result[name] = [
                {"info_id": s.get("info_id", ""), "content": s.get("content", "")}
                for s in secrets
            ]
    return result


def _build_ai_managed_npcs_dict() -> dict[str, str]:
    """Build a dict of NPCs whose locations are currently managed by the Variable AI.

    These NPCs were in the hot zone and had their location explicitly set by the
    Variable AI. Their positions override the funnel's schedule-based placement.
    """
    managed = {}
    for name, data in CHARACTER_LIBRARY.items():
        if data.get("_ai_location_managed") and data.get("current_location_id"):
            managed[name] = data["current_location_id"]
    return managed


def _collect_hot_zone_npc_data(
    player_location_id: str,
    player_name: str,
    funnel_result: dict,
    recent_narrative: str = "",
    max_hot_npcs: int = 8,
) -> list[dict]:
    """Collect detailed profiles for NPCs in the hot zone.

    Hot zone = spotlight NPCs + background NPCs at player location +
               NPCs mentioned in recent narrative.
    Capped at max_hot_npcs to avoid overwhelming the Variable Agent.

    Returns list of structured NPC dicts for the Variable Agent.
    """
    hot_npcs: list[dict] = []
    seen_names: set[str] = set()

    # 1. Spotlight NPCs first (highest priority)
    for npc in funnel_result.get("spotlight_npcs", []):
        name = npc.get("name", "")
        if name == player_name or not name:
            continue
        char_data = CHARACTER_LIBRARY.get(name, {})
        if not char_data:
            continue
        seen_names.add(name)
        hot_npcs.append({
            "name": name,
            "class_name": char_data.get("class_name", "?"),
            "traits": char_data.get("traits", []),
            "status_tags": char_data.get("status_tags", []),
            "current_location_id": char_data.get("current_location_id", player_location_id),
            "dorm_room_id": char_data.get("dorm_room_id", ""),
            "relations": char_data.get("relations", []),
            "secrets": char_data.get("secrets", []),
        })

    # 2. Background NPCs at player location (second priority)
    for npc in funnel_result.get("background_npcs", []):
        if len(hot_npcs) >= max_hot_npcs:
            break
        name = npc.get("name", "")
        if name == player_name or not name or name in seen_names:
            continue
        char_data = CHARACTER_LIBRARY.get(name, {})
        if not char_data:
            continue
        seen_names.add(name)
        hot_npcs.append({
            "name": name,
            "class_name": char_data.get("class_name", "?"),
            "traits": char_data.get("traits", []),
            "status_tags": char_data.get("status_tags", []),
            "current_location_id": char_data.get("current_location_id", player_location_id),
            "dorm_room_id": char_data.get("dorm_room_id", ""),
            "relations": char_data.get("relations", []),
            "secrets": char_data.get("secrets", []),
        })

    # 3. NPCs mentioned in recent narrative (even if not at player location)
    if recent_narrative and len(hot_npcs) < max_hot_npcs:
        for name, data in CHARACTER_LIBRARY.items():
            if len(hot_npcs) >= max_hot_npcs:
                break
            if name == player_name or name in seen_names:
                continue
            if name in recent_narrative:
                hot_npcs.append({
                    "name": name,
                    "class_name": data.get("class_name", "?"),
                    "traits": data.get("traits", []),
                    "status_tags": data.get("status_tags", []),
                    "current_location_id": data.get("current_location_id", ""),
                    "relations": data.get("relations", []),
                    "secrets": data.get("secrets", []),
                })

    return hot_npcs


def _log_var_changes(changes: dict) -> None:
    """Log extracted variable changes for debugging."""
    if not changes:
        return
    msgs = []
    if changes.get("new_time_slot"):
        msgs.append(f"time→{changes['new_time_slot']}")
    if changes.get("new_game_date"):
        msgs.append(f"date→{changes['new_game_date']}")
    if changes.get("new_location_id"):
        msgs.append(f"loc→{changes['new_location_id']}")
    if changes.get("sleep_to_morning"):
        msgs.append("sleep→morning")
    if changes.get("private_points_delta"):
        msgs.append(f"priv_pts {changes['private_points_delta']:+d}")
    if changes.get("class_points_delta"):
        msgs.append(f"cls_pts {changes['class_points_delta']:+d}")
    for npc in changes.get("npc_point_changes", []):
        msgs.append(f"npc_pts {npc.get('target_char','?')} {npc.get('amount',0):+d}")
    for rel in changes.get("relation_changes", []):
        msgs.append(f"rel {rel.get('from','?')}→{rel.get('to','?')}:{rel.get('type','?')}")
    for st in changes.get("npc_status_changes", []):
        msgs.append(f"status {st.get('char_name','?')} +{st.get('add_tags',[])} -{st.get('remove_tags',[])}")
    for loc in changes.get("npc_location_changes", []):
        msgs.append(f"npc_loc {loc.get('char_name','?')}→{loc.get('new_location_id','?')}")
    for ev in changes.get("new_events", []):
        msgs.append(f"event: {ev}")
    for sk in changes.get("secret_knowledge_changes", []):
        msgs.append(f"secret {sk.get('secret_info_id','?')} → {sk.get('new_knower','?')}")
    for hb in changes.get("hot_npc_behaviors", []):
        msgs.append(f"hot_npc {hb.get('char_name','?')}: {hb.get('behavior_reason','')[:30]}")
    if msgs:
        print(f"  [VariableAgent] Extracted: {' | '.join(msgs)}")


async def _apply_state_changes(session: GameSession, changes: dict, db=None) -> None:
    """Apply AI-requested state changes directly to the ORM object.

    Handles both the legacy state_changes fields and the richer Variable Agent output.
    """
    if not changes:
        return

    # Capture old date for settlement detection
    old_date = session.game_date

    # --- Time and Location (legacy + variable agent) ---
    new_loc = changes.get("new_location_id", "")
    if new_loc and new_loc in LOCATIONS:
        session.player_location_id = new_loc
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
        session.player_location_id = "dorm_lobby"

    # --- Points (Variable Agent output) ---
    player_name = session.player_name

    # Player private points delta
    private_delta = changes.get("private_points_delta", 0)
    if private_delta and isinstance(private_delta, (int, float)):
        session.private_points += int(private_delta)
        if player_name in CHARACTER_LIBRARY:
            CHARACTER_LIBRARY[player_name]["private_points"] = (
                CHARACTER_LIBRARY[player_name].get("private_points", 0) + int(private_delta)
            )

    # Class points delta
    class_delta = changes.get("class_points_delta", 0)
    if class_delta and isinstance(class_delta, (int, float)):
        session.class_points += int(class_delta)

    # NPC point changes
    for npc_change in changes.get("npc_point_changes", []):
        target_name = npc_change.get("target_char", "")
        amount = npc_change.get("amount", 0)
        reason = npc_change.get("reason", "")
        if target_name and target_name in CHARACTER_LIBRARY and amount:
            char = CHARACTER_LIBRARY[target_name]
            char["private_points"] = char.get("private_points", 0) + amount
            # Sync to DB if available
            if db:
                await _sync_char_points_to_db(db, target_name, char["private_points"])

    # NPC status changes
    for status_change in changes.get("npc_status_changes", []):
        char_name = status_change.get("char_name", "")
        if char_name and char_name in CHARACTER_LIBRARY:
            char = CHARACTER_LIBRARY[char_name]
            tags = set(char.get("status_tags", []))
            for tag in status_change.get("add_tags", []):
                tags.add(tag)
            for tag in status_change.get("remove_tags", []):
                tags.discard(tag)
            char["status_tags"] = list(tags)
            if db:
                await _sync_char_tags_to_db(db, char_name, list(tags))

    # NPC location changes
    for loc_change in changes.get("npc_location_changes", []):
        char_name = loc_change.get("char_name", "")
        new_loc_id = loc_change.get("new_location_id", "")
        if char_name and char_name in CHARACTER_LIBRARY and new_loc_id:
            CHARACTER_LIBRARY[char_name]["current_location_id"] = new_loc_id
            if db:
                await _sync_char_location_to_db(db, char_name, new_loc_id)

    # Relation changes
    for rel_change in changes.get("relation_changes", []):
        from_name = rel_change.get("from", "")
        to_name = rel_change.get("to", "")
        rel_type = rel_change.get("type", "")
        reason = rel_change.get("reason", "")
        if from_name and to_name and rel_type:
            # Update in-memory CHARACTER_LIBRARY
            if from_name in CHARACTER_LIBRARY:
                char = CHARACTER_LIBRARY[from_name]
                relations = char.get("relations", [])
                # Update existing or add new
                updated = False
                for r in relations:
                    if r.get("to") == to_name:
                        r["type"] = rel_type
                        r["reason"] = reason
                        updated = True
                        break
                if not updated:
                    relations.append({"to": to_name, "type": rel_type, "reason": reason})
                char["relations"] = relations
            # Sync to DB if available
            if db:
                await _sync_relation_to_db(db, from_name, to_name, rel_type, reason)

    # Secret knowledge changes
    for sk_change in changes.get("secret_knowledge_changes", []):
        secret_info_id = sk_change.get("secret_info_id", "")
        new_knower_name = sk_change.get("new_knower", "")
        reason = sk_change.get("reason", "")
        if secret_info_id and new_knower_name:
            # Find which character owns this secret and add the new knower
            for char_name, char_data in CHARACTER_LIBRARY.items():
                for secret in char_data.get("secrets", []):
                    if secret.get("info_id") == secret_info_id:
                        known_by = secret.setdefault("known_by", [])
                        if new_knower_name not in known_by:
                            known_by.append(new_knower_name)
                        if db:
                            await _sync_secret_knowledge_to_db(
                                db, secret_info_id, new_knower_name, reason
                            )
                        break

    # Hot zone NPC proactive behavior updates
    for behavior in changes.get("hot_npc_behaviors", []):
        char_name = behavior.get("char_name", "")
        if not char_name or char_name not in CHARACTER_LIBRARY:
            continue
        char = CHARACTER_LIBRARY[char_name]

        # Update location if specified
        new_loc = behavior.get("new_location_id")
        if new_loc:
            char["current_location_id"] = new_loc
            char["_ai_location_managed"] = True
            if db:
                await _sync_char_location_to_db(db, char_name, new_loc)

        # Update status tags
        tags = set(char.get("status_tags", []))
        for tag in behavior.get("add_tags", []):
            tags.add(tag)
        for tag in behavior.get("remove_tags", []):
            tags.discard(tag)
        char["status_tags"] = list(tags)
        if db:
            await _sync_char_tags_to_db(db, char_name, list(tags))

        reason = behavior.get("behavior_reason", "")
        if reason:
            print(f"  [HotZone] {char_name}: {reason}")

    # New events
    for event_name in changes.get("new_events", []):
        if event_name and db:
            print(f"  [VariableAgent] New event triggered: {event_name}")

    # Detect date change for daily settlement
    if session.game_date != old_date:
        session._pending_settlement = session.game_date

    # Cold zone cleanup: release NPCs that left the hot zone
    player_loc = session.player_location_id
    for name, data in CHARACTER_LIBRARY.items():
        if data.get("_ai_location_managed"):
            npc_loc = data.get("current_location_id", "")
            if npc_loc != player_loc:
                data["_ai_location_managed"] = False


async def _sync_char_points_to_db(db, char_name: str, new_points: int) -> None:
    """Sync a character's private_points to the database."""
    from src.models.character import Character
    result = await db.execute(
        select(Character).where(Character.name == char_name)
    )
    char = result.scalar_one_or_none()
    if char:
        char.private_points = new_points


async def _sync_char_tags_to_db(db, char_name: str, tags: list[str]) -> None:
    """Sync a character's status_tags to the database."""
    from src.models.character import Character
    result = await db.execute(
        select(Character).where(Character.name == char_name)
    )
    char = result.scalar_one_or_none()
    if char:
        char.status_tags = tags


async def _sync_char_location_to_db(db, char_name: str, location_id: str) -> None:
    """Sync a character's current_location_id to the database."""
    from src.models.character import Character
    result = await db.execute(
        select(Character).where(Character.name == char_name)
    )
    char = result.scalar_one_or_none()
    if char:
        char.current_location_id = location_id


async def _sync_relation_to_db(db, from_name: str, to_name: str,
                               rel_type: str, reason: str) -> None:
    """Sync a social relation change to the database."""
    from src.models.character import Character
    from src.models.social_relation import SocialRelation
    src_result = await db.execute(
        select(Character).where(Character.name == from_name)
    )
    src_char = src_result.scalar_one_or_none()
    dst_result = await db.execute(
        select(Character).where(Character.name == to_name)
    )
    dst_char = dst_result.scalar_one_or_none()
    if src_char and dst_char:
        existing = await db.execute(
            select(SocialRelation).where(
                SocialRelation.src_char_id == src_char.id,
                SocialRelation.dst_char_id == dst_char.id,
            )
        )
        rel = existing.scalar_one_or_none()
        if rel:
            rel.relation_type = rel_type
            rel.reason = reason
        else:
            from src.models.social_relation import RelationType
            try:
                rt = RelationType(rel_type)
            except ValueError:
                rt = RelationType.TRUST
            new_rel = SocialRelation(
                src_char_id=src_char.id,
                dst_char_id=dst_char.id,
                relation_type=rt,
                reason=reason,
            )
            db.add(new_rel)


async def _sync_secret_knowledge_to_db(db, secret_info_id: str,
                                       knower_name: str, reason: str) -> None:
    """Sync a secret knowledge change to the database."""
    from src.models.character import Character
    from src.models.secret import Secret, SecretKnowledge
    secret_result = await db.execute(
        select(Secret).where(Secret.info_id == secret_info_id)
    )
    secret = secret_result.scalar_one_or_none()
    if not secret:
        return
    knower_result = await db.execute(
        select(Character).where(Character.name == knower_name)
    )
    knower = knower_result.scalar_one_or_none()
    if not knower:
        return
    existing = await db.execute(
        select(SecretKnowledge).where(
            SecretKnowledge.secret_id == secret.id,
            SecretKnowledge.character_id == knower.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        sk = SecretKnowledge(
            secret_id=secret.id,
            character_id=knower.id,
            unlocked_reason=reason,
        )
        db.add(sk)


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


def _calc_days_left(game_date: str, end_date: str | None) -> str:
    """Calculate days remaining until end_date for frontend display."""
    if not end_date:
        return "?"
    try:
        from datetime import date
        current = date.fromisoformat(game_date)
        end = date.fromisoformat(end_date)
        delta = (end - current).days
        return str(delta) if delta >= 0 else "已过期"
    except Exception:
        return "?"


def _build_fallback_narrative(parsed: dict, validation_error: str, state_dict: dict) -> str:
    """Build a graceful fallback narrative when validation keeps failing.

    Instead of showing raw error text, produce natural in-character text
    that explains why the action can't proceed (e.g. location not found).
    """
    loc = state_dict.get("location", {})
    loc_name = loc.get("name", "当前地点")
    orig_narrative = parsed.get("narrative", "")

    # Check what kind of error this is
    if "new_location_id" in validation_error and "不存在于" in validation_error:
        # Extract the invalid location name from error
        import re as _re
        match = _re.search(r"new_location_id '(\w+)'", validation_error)
        bad_loc = match.group(1) if match else "那个地方"
        # Build a list of nearby available locations
        available = state_dict.get("location", {}).get("connected_to", [])
        nearby = "、".join(available[:5]) if available else "附近"
        return (
            f"{orig_narrative}\n\n"
            f"我想去{bad_loc}，但似乎没有找到这个地方。{loc_name}附近可去的地方有：{nearby}。"
            f"或许我应该先确认一下想去的地方叫什么名字。"
        )

    if "new_time_slot" in validation_error:
        return f"{orig_narrative}\n\n时间不知不觉地流逝了片刻。"

    # Generic fallback
    return (
        f"{orig_narrative}\n\n"
        f"我顿了顿，觉得刚才的想法有些不太实际。还是再考虑一下接下来该做什么吧。"
    )


async def _event_lifecycle_advance(db, game_date: str) -> list[str]:
    """Advance event lifecycles on date change. Returns active event prompts."""
    from src.core.event_bus.bus import EventBus
    bus = EventBus(db)
    advs = await bus.advance_lifecycle(game_date)
    prompts = []
    for a in advs:
        if a.new_phase in ("active", "transition") and a.prompt_to_inject:
            prompts.append(f"【事件推进：{a.event_id}】\n{a.prompt_to_inject}")
    return prompts


# Track last forecaster run date to prevent multiple runs on the same day
_forecaster_last_run_date: str = ""


async def _run_forecaster_if_needed(db, game_date: str, time_slot: str) -> int:
    """Run AI forecaster on date change if conditions are met.

    Triggers when:
    1. Dynamic event pool is low (pending < forecaster_min_pending)
    2. It's the scheduled time (default: Sunday evening)

    Always runs pool maintenance to clean expired events.
    A cooldown prevents running more than once per game-date.
    """
    global _forecaster_last_run_date
    from datetime import datetime
    from sqlalchemy import select
    from src.core.forecaster.forecaster import Forecaster
    from src.models.event import DynamicEvent

    # Cooldown: don't run more than once per game-date
    if _forecaster_last_run_date == game_date:
        return 0

    # Count pending dynamic events
    pending_result = await db.execute(
        select(DynamicEvent).where(
            DynamicEvent.is_triggered == False,
            DynamicEvent.is_expired == False,
        )
    )
    pending_events = pending_result.scalars().all()
    pending_count = len(pending_events)

    should_run = False

    # Condition 1: pool running low
    if pending_count < settings.forecaster_min_pending:
        should_run = True

    # Condition 2: scheduled time (Sunday evening by default)
    weekday = datetime.strptime(game_date, "%Y-%m-%d").weekday()
    if (
        time_slot == settings.forecaster_schedule_slot
        and weekday == settings.forecaster_schedule_day - 1
    ):
        should_run = True

    forecaster = Forecaster(db)

    # Always run maintenance to clean expired events
    maint_result = await forecaster.maintenance(game_date)

    generated = 0
    if should_run:
        generated = await forecaster.run(game_date, time_slot)
        _forecaster_last_run_date = game_date
        print(
            f"  [Forecaster] game_date={game_date} time_slot={time_slot} "
            f"generated={generated} pool_pending_before={pending_count} "
            f"expired={maint_result.get('expired_this_run', 0)}"
        )

    return generated


async def _get_events_for_display(
    db, location_id: str, game_date: str, time_slot: str,
    player_char_id: str | None = None,
) -> list[dict]:
    """Query active events for frontend display without firing them."""
    from src.core.event_bus.bus import EventBus

    location_id = _LOCATION_ALIASES.get(location_id, location_id)

    bus = EventBus(db)
    matches = await bus.check_triggers(location_id, game_date, time_slot, player_char_id)

    mapped_locs = LOCATION_EVENT_MAP.get(location_id, [location_id])
    for mloc in mapped_locs:
        if mloc != location_id:
            extra = await bus.check_triggers(mloc, game_date, time_slot, player_char_id)
            for m in extra:
                if not any(mm.event.id == m.event.id for mm in matches):
                    matches.append(m)

    events = []
    for match in matches:
        ev = match.event
        events.append({
            "name": ev.name,
            "description": (ev.active_prompt or ev.ai_setup_prompt or "")[:200],
            "days_left": _calc_days_left(game_date, ev.active_end_date),
            "phase": ev.phase.value if ev.phase else "?",
            "match_type": match.match_type,
        })
    return events


async def _check_and_fire_events(
    db, location_id: str, game_date: str, time_slot: str,
    player_char_id: str | None = None,
) -> tuple[list[str], list[dict]]:
    """Check event triggers and fire matching events.
    Returns (prompts_for_llm, active_events_for_display)."""
    location_id = _LOCATION_ALIASES.get(location_id, location_id)
    from src.core.event_bus.bus import EventBus

    bus = EventBus(db)

    # Check static events (with location mapping)
    matches = await bus.check_triggers(location_id, game_date, time_slot, player_char_id)
    # Also check against mapped location IDs
    mapped_locs = LOCATION_EVENT_MAP.get(location_id, [location_id])
    for mloc in mapped_locs:
        if mloc != location_id:
            extra_matches = await bus.check_triggers(mloc, game_date, time_slot, player_char_id)
            for m in extra_matches:
                if not any(mm.event.id == m.event.id for mm in matches):
                    matches.append(m)

    # Also check dynamic events
    dynamic_matches = await bus.check_dynamic_triggers(location_id, game_date)

    prompts = []
    active_events = []

    for match in matches:
        ctx = await bus.fire_event(match.event, phase="active")
        if ctx and ctx.ai_prompt:
            prompts.append(f"【事件触发：{ctx.event_name}】\n{ctx.ai_prompt}")
        if ctx and ctx.rules_appendix:
            prompts.append(f"【考试规则：{ctx.event_name}】\n{ctx.rules_appendix}")

        ev = match.event
        active_events.append({
            "name": ev.name,
            "description": (ev.active_prompt or ev.ai_setup_prompt or "")[:200],
            "days_left": _calc_days_left(game_date, ev.active_end_date),
            "phase": ev.phase.value if ev.phase else "?",
            "match_type": match.match_type,
        })

    for dev in dynamic_matches:
        if dev.ai_setup_prompt:
            dev.is_triggered = True
            prompts.append(f"【动态事件：{dev.name or '支线事件'}】\n{dev.ai_setup_prompt}")
        active_events.append({
            "name": dev.name or "支线事件",
            "description": (dev.ai_setup_prompt or "")[:200],
            "days_left": _calc_days_left(game_date, dev.expires_at or dev.trigger_date_end),
            "phase": "dynamic",
            "match_type": "dynamic",
        })

    await db.flush()
    return prompts, active_events


def _build_llm_context(
    user_input: str, state_dict: dict, max_tokens: int = 1024,
    history: list[dict] | None = None, summary: str = "",
    event_prompts: list[str] | None = None,
) -> list[dict]:
    """Build messages for LLM call, with chat history injected."""
    loc = state_dict.get("location", {})
    time_str = state_dict["time_display"]

    spotlight_text = state_dict.get("spotlight_text", "")
    background_text = state_dict.get("background_text", "")
    npc_context = ""
    if spotlight_text:
        npc_context = spotlight_text
        if background_text:
            npc_context += "\n" + background_text

    # Build dorm room reference: NPC→room mapping for the narrative LLM
    dorm_room_map = state_dict.get("dorm_room_map", {})
    dorm_room_ref = ""
    if dorm_room_map:
        pairs = [f"{name}→{room}" for name, room in sorted(dorm_room_map.items())]
        dorm_room_ref = "【宿舍房间参考 - 玩家提及某人房间时请使用对应location_id】\n" + " | ".join(pairs)

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
            # Clean any hallucinated XML tool calls from history narratives
            narrative, _ = _strip_xml_tool_calls(narrative)
            recent_lines.append(f"- AI：{narrative}")
        history_section += "\n".join(recent_lines) + "\n\n"

    player_name = state_dict.get("player_name", "学生")
    player_class = state_dict.get("player_class", "D")
    dialogue_count = state_dict.get("dialogue_count_since_summary", 0)

    is_opening = user_input.strip() == "/intro" and dialogue_count == 0

    if is_opening:
        # Class-specific opening: use special system prompt for monologue + continuation
        opening_system = build_opening_system_prompt(player_class, player_name, CHARACTER_LIBRARY)
        user_msg = f"""【当前状态】
玩家：{player_name}（{player_class}班学生）
时间：{time_str}
位置：{loc.get('name', '未知')}（{loc.get('description', '')}）
班级点数：{state_dict['class_points']} | 私人点数：{state_dict['private_points']}
{npc_context}

【指令】
系统提示词中已经包含了已发生的开场剧情。请严格按照系统提示词中的要求：先以{player_name}的第一人称写一段内心独白，然后自然地延续剧情。
{word_req}
- 必须包含2-3个引导下一步行动的选项"""
    elif user_input.strip() == "/skip_day":
        tomorrow = _advance_state({"game_date": state_dict["game_date"], "time_slot": state_dict["time_slot"]}, 5)
        user_msg = f"""{history_section}【当前状态】
玩家：{player_name}（{player_class}班学生）
时间：{time_str}
位置：{loc.get('name', '未知')}（{loc.get('description', '')}）
班级点数：{state_dict['class_points']} | 私人点数：{state_dict['private_points']}
{npc_context}

【系统指令 - 快进到明天】
玩家选择跳过今天剩余的时间，直接到达第二天（{tomorrow['game_date']} morning）。

你的任务：
1. 以第一人称"我"的视角，用2-3句话简短总结今天剩余时间发生的事情。内容应包含：
   - 从当前位置合理地过渡到回宿舍休息
   - 一个自然的时间流逝感
2. 叙事要自然、简短。不要描述细节，不要展开对话，不要描写NPC的详细行为
3. 叙事字数控制在100字以内
4. 时间推进和位置移动由系统自动处理，你无需关心
5. choices留空数组[]

请严格按照JSON格式返回（narrative + choices）。"""
    elif user_input.strip() == "/intro":
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
{dorm_room_ref}

【玩家行动】
{user_input}

请根据以上信息生成叙事。如果有【最近对话】，请保持叙事连贯性。
{word_req}
【重要】请在JSON回复中包含至少2个choices选项，引导下一步行动。"""

    system_content = opening_system if is_opening else GAME_SYSTEM_PROMPT
    if WORLDVIEW_CONTEXT:
        system_content += "\n\n## 世界观设定参考\n" + WORLDVIEW_CONTEXT

    messages = [{"role": "system", "content": system_content}]

    # Inject triggered event prompts as additional system messages
    if event_prompts:
        for ep in event_prompts:
            messages.append({"role": "system", "content": ep})

    messages.append({"role": "user", "content": user_msg})
    return messages


def _recover_json_string(text: str, key: str) -> str | None:
    """Recover a JSON string value from truncated JSON by walking characters."""
    pattern = rf'"{key}"\s*:\s*"'
    m = re.search(pattern, text)
    if not m:
        return None
    pos = m.end()
    result = []
    while pos < len(text):
        ch = text[pos]
        if ch == '\\' and pos + 1 < len(text):
            nxt = text[pos + 1]
            escapes = {'n': '\n', '"': '"', '\\': '\\', 't': '\t', 'r': '\r'}
            result.append(escapes.get(nxt, nxt))
            pos += 2
        elif ch == '"':
            rest = text[pos + 1:pos + 21].lstrip()
            if not rest or rest[0] in ',}':
                break
            result.append(ch)
            pos += 1
        else:
            result.append(ch)
            pos += 1
    return ''.join(result)


def _recover_json_array(text: str, key: str) -> list:
    """Try to recover a JSON array from truncated JSON."""
    pattern = rf'"{key}"\s*:\s*\['
    m = re.search(pattern, text)
    if not m:
        return []
    bracket_start = m.end() - 1
    depth = 0
    pos = bracket_start
    in_string = False
    while pos < len(text):
        ch = text[pos]
        if in_string:
            if ch == '\\':
                pos += 2
                continue
            if ch == '"':
                in_string = False
            pos += 1
            continue
        if ch == '"':
            in_string = True
        elif ch in '[{':
            depth += 1
        elif ch in ']}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[bracket_start:pos + 1])
                except json.JSONDecodeError:
                    return []
        pos += 1
    return []


def _strip_xml_tool_calls(content: str) -> tuple[str, list[str]]:
    """Remove XML-formatted tool calls that the model may have hallucinated into the text content.

    Some LLMs output tool calls as raw XML in the content field instead of using the proper
    tool_calls API field. This strips them so they don't appear in the player's narrative.

    Returns (cleaned_content, list_of_stripped_tool_names).
    """
    stripped = []

    # Pattern 1: <invoke name="tool_name">...</invoke> (Anthropic-style)
    def _replace_invoke(m: re.Match) -> str:
        tool = m.group(1) or "unknown"
        stripped.append(tool)
        return ""

    content = re.sub(
        r'<invoke\s+name=["\']([^"\']+)["\']\s*>.*?</invoke>',
        _replace_invoke,
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Pattern 2: <tool_calls>...</tool_calls> wrapper (English + Chinese variants)
    content = re.sub(
        r'</?(?:tool_calls|工具调用|函数调用)>',
        "",
        content,
        flags=re.IGNORECASE,
    )

    # Pattern 3: Self-closing <invoke ... /> style
    content = re.sub(
        r'<invoke\s+[^>]*?/>',
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Pattern 4: <function_call>...</function_call> (OpenAI hallucination variant)
    content = re.sub(
        r'<function_call>.*?</function_call>',
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Pattern 5: Stray <parameter ...>text</parameter> without wrapper
    content = re.sub(
        r'</?parameter[^>]*>',
        "",
        content,
        flags=re.IGNORECASE,
    )

    # Pattern 6: Bare/unclosed <invoke ...> opening tags (no matching close)
    content = re.sub(
        r'<invoke\s+[^>]*>',
        "",
        content,
        flags=re.IGNORECASE,
    )

    # Pattern 7: Orphaned closing tags
    _close_names = "|".join(
        t["function"]["name"] for t in TOOL_DEFINITIONS
    )
    content = re.sub(
        rf'</(invoke|tool_calls?|function_calls?|工具调用|函数调用|{_close_names})\s*>',
        "",
        content,
        flags=re.IGNORECASE,
    )

    # Pattern 8: ```xml ... ``` code blocks that contain tool calls
    content = re.sub(
        r'```xml\s*.*?```',
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Pattern 9: Bare tool-name XML blocks like <query_location_info>...</query_location_info>
    # that contain <parameter> children (DeepSeek hallucination pattern)
    content = re.sub(
        rf'<({_close_names})\s*>.*?</\1\s*>',
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Clean up extra whitespace left by removals
    content = re.sub(r'\n{3,}', '\n\n', content)
    content = content.strip()

    return content, stripped


def _content_has_garbage(text: str) -> str:
    """Check if the narrative text still contains XML tool calls or other garbage.

    Returns an empty string if clean, or a human-readable reason if garbage found.
    This is the last line of defense before content reaches the player.
    """
    if not text or not text.strip():
        return ""

    # Build patterns from TOOL_DEFINITIONS
    _tool_names = "|".join(t["function"]["name"] for t in TOOL_DEFINITIONS)

    # Pattern 1: Tool-name XML blocks: <query_location_info>...</query_location_info>
    m = re.search(
        rf'<({_tool_names})\s*>.*?</\1\s*>',
        text, flags=re.DOTALL | re.IGNORECASE,
    )
    if m:
        return f"内容包含工具调用XML块 <{m.group(1)}>"

    # Pattern 2: invoke / tool_calls / function_call wrappers (English + Chinese)
    m = re.search(
        r'<\s*(invoke|tool_calls?|function_calls?|工具调用|函数调用)\b',
        text, flags=re.IGNORECASE,
    )
    if m:
        return f"内容包含工具调用标签 <{m.group(1)}>"

    # Pattern 3: Stray <parameter> tags (orphaned from wrapper)
    if re.search(r'<\s*parameter\b', text, flags=re.IGNORECASE):
        return "内容包含 <parameter> 工具调用标签"

    # Pattern 4: Unclosed XML open tags that look like tool names
    m = re.search(
        rf'<\s*({_tool_names})\s*>',
        text, flags=re.IGNORECASE,
    )
    if m:
        return f"内容包含未闭合的工具标签 <{m.group(1)}>"

    # Pattern 5: Raw JSON tool call fragments
    if re.search(r'"tool_calls"\s*:\s*\[', text):
        return "内容包含原生 tool_calls JSON"

    # Pattern 6: Anthropic-style assistant tool_use blocks
    if re.search(r'"type"\s*:\s*"tool_use"', text):
        return "内容包含 Anthropic 风格的 tool_use 块"

    return ""


def _parse_llm_content(content: str) -> dict:
    """Parse JSON from LLM response text. Falls back to regex recovery for truncated JSON."""
    content, stripped_tools = _strip_xml_tool_calls(content)
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(l for l in lines if not l.startswith("```"))
    try:
        result = json.loads(content)
        narrative = result.get("narrative", content)
        choices = result.get("choices", [])
    except json.JSONDecodeError:
        narrative = _recover_json_string(content, "narrative") or content
        choices = _recover_json_array(content, "choices")

    # Last line of defense: check for XML tool calls / garbage in narrative
    garbage_reason = _content_has_garbage(narrative)
    if garbage_reason:
        print(f"  [GateCheck] BLOCKED garbage in narrative: {garbage_reason}")
        narrative = (
            f"[系统提示] AI生成的内容包含异常数据（{garbage_reason}），"
            f"已被自动拦截。请重新输入你的行动。"
        )
        choices = []

    # state_changes is no longer expected from Narrative Agent;
    # Variable Agent extracts them asynchronously.
    return {"narrative": narrative, "choices": choices, "state_changes": {}}


# ---- Offline Response Generator ----

def _get_npcs_at(location_id: str, player_name: str) -> list[str]:
    """Get NPC names at a location using the funnel."""
    funnel_result = run_npc_funnel(
        character_library=CHARACTER_LIBRARY,
        player_name=player_name,
        player_location_id=location_id,
        game_date="2024-05-01",
        time_slot="morning",
        max_spotlight=10,
    )
    return funnel_result.get("all_at_location", [])


def generate_offline_response(user_input: str, state_dict: dict) -> dict:
    """Generate a narrative response without LLM (demo/offline mode)."""
    loc = state_dict.get("location", {})
    loc_name = loc.get("name", "未知地点")
    location_id = state_dict["location_id"]
    player_name = state_dict.get("player_name", "")
    npcs = state_dict.get("npcs_at_location", [])
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
            "state_changes": {"new_location_id": "dorm_lobby", "sleep_to_morning": True},
        }

    if inp in ("/skip_day",):
        slot_summaries = {
            "morning": "上午的课程结束后，我在食堂简单吃了午饭。下午的课一如既往地平淡，放学后没有什么特别的事。回到宿舍，洗漱完毕，躺在床上，一天的疲劳让我很快进入了梦乡。",
            "noon": "下午的课程按部就班地进行着。放学后我在校园里随意走了走，没什么特别的事发生。回到宿舍后，我在房间里待到深夜，困意袭来便睡下了。",
            "dusk": "傍晚时分，天色渐暗。我在校园里漫无目的地走了一会儿，然后回到了宿舍。在床上回想今天发生的事情，不知不觉就睡着了。",
            "evening": "夜晚的校园很安静。我回到宿舍楼，简单洗漱后躺在床上。窗外的灯光一盏盏熄灭，我也渐渐沉入睡眠。",
            "late_night": "深夜的校园万籁俱寂。四周一片漆黑，我把今天的事情在脑海中过了一遍，便沉沉睡去。",
        }
        current_slot = state_dict.get("time_slot", "morning")
        summary = slot_summaries.get(current_slot, slot_summaries["evening"])
        return {
            "narrative": f"我决定不再耽搁，直接结束今天。{summary}\n\n闹钟响起的时候，窗外已经大亮。新的一天开始了。",
            "choices": [],
            "state_changes": {"new_location_id": "dorm_lobby", "sleep_to_morning": True},
        }

    if inp.startswith("/go "):
        target = inp[4:].strip()
        for lid, ldata in LOCATIONS.items():
            if target in lid or target in ldata["name"]:
                npcs_there = _get_npcs_at(lid, player_name)
                npc_str = ""
                if npcs_there:
                    npc_str = " " + "、".join(npcs_there) + "也在这里。"
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
                npcs_there = _get_npcs_at(lid, player_name)
                npc_str = ""
                if npcs_there:
                    npc_str = "\n\n" + "、".join(npcs_there) + "也在这里。"
                return {
                    "narrative": f"你来到了【{ldata['name']}】。{ldata['description']}{npc_str}",
                    "choices": [],
                    "state_changes": {"new_location_id": lid, "advance_slots": 1},
                }

    if any(w in inp for w in ("看", "观察", "打量", "环顾")):
        desc = loc.get("description", "")
        npc_desc = ""
        if npcs:
            npc_desc = "\n\n在附近，你注意到" + "、".join(npcs) + "。"
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
    event_prompts: list[str] | None = None,
    validation_error: str = "",
) -> dict:
    """Send the player input to DeepSeek and get a narrative response (with tool calling)."""
    messages = _build_llm_context(user_input, state_dict, max_tokens, history, summary, event_prompts)
    if validation_error:
        messages.append({"role": "system", "content": validation_error})

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
                        "tools": NARRATIVE_TOOLS,
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
                        # Validate tool call before execution
                        valid, err_msg = validate_tool_call(fn_name, fn_args)
                        if not valid:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps(
                                    {"error": f"工具调用参数错误：{err_msg}", "tool": fn_name},
                                    ensure_ascii=False,
                                ),
                            })
                            continue
                        result = await _execute_tool(fn_name, fn_args, state_dict.get("player_name", ""))
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

                    # Check for hallucinated XML tool calls in content
                    cleaned, xml_tools = _strip_xml_tool_calls(content)
                    if xml_tools and not cleaned:
                        # Content was nothing but XML tool calls — append as if
                        # the model tried to call tools, let it retry properly
                        messages.append({
                            "role": "assistant",
                            "content": "",
                        })
                        messages.append({
                            "role": "user",
                            "content": f"你刚才在文本中直接输出了工具调用格式，这是无效的。"
                                       f"请使用系统提供的函数调用机制来调用这些工具：{', '.join(xml_tools)}。"
                                       f"如果需要这些信息，请先调用工具获取数据，再生成叙事。",
                        })
                        continue

                    finish_reason = data["choices"][0].get("finish_reason", "")
                    parsed = _parse_llm_content(content)
                    # Validate final response
                    valid_resp, resp_err = validate_llm_response(
                        parsed,
                        current_location_id=state_dict.get("location_id", ""),
                        locations=LOCATIONS,
                        check_reachability=settings.ai_validation_reachability_check,
                    )
                    if not valid_resp:
                        parsed["_validation_error"] = resp_err
                    parsed["_tool_calls"] = len(
                        [m for m in messages if m.get("role") == "tool"]
                    )
                    parsed["_truncated"] = finish_reason == "length"
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
                    "tools": NARRATIVE_TOOLS,
                    "tool_choice": "none",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            finish_reason = data["choices"][0].get("finish_reason", "")
            parsed = _parse_llm_content(content)
            parsed["_truncated"] = finish_reason == "length"
            return parsed
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
            return {"narrative": f"[LLM错误: {e}]", "choices": [], "state_changes": {}}


async def generate_llm_stream(
    user_input: str, state_dict: dict, max_tokens: int,
    history: list[dict] | None, summary: str, db_session,
    event_prompts: list[str] | None = None,
    active_events: list[dict] | None = None,
):
    """SSE streaming generator with DB persistence and tool calling support."""
    messages = _build_llm_context(user_input, state_dict, max_tokens, history, summary, event_prompts)
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
                        "tools": NARRATIVE_TOOLS,
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
                        # Validate tool call before execution
                        valid, err_msg = validate_tool_call(fn_name, fn_args)
                        if not valid:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps(
                                    {"error": f"工具调用参数错误：{err_msg}", "tool": fn_name},
                                    ensure_ascii=False,
                                ),
                            })
                            tool_call_history.append({
                                "tool": fn_name,
                                "args": tc["function"]["arguments"],
                                "error": err_msg,
                            })
                            continue
                        result = await _execute_tool(fn_name, fn_args, state_dict.get("player_name", ""))
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
        finish_reason = None
        xml_suppress_buffer = ""   # accumulates chars while inside an XML tool-call block
        in_xml_block = False
        # Build regex from TOOL_DEFINITIONS + common wrapper patterns to catch any tool call XML
        _tool_names = "|".join(
            t["function"]["name"] for t in TOOL_DEFINITIONS
        )
        XML_START_RE = re.compile(
            rf'<\s*(?:invoke|tool_calls?|function_calls?|工具调用|函数调用|{_tool_names})\b',
            re.IGNORECASE,
        )
        XML_END_RE = re.compile(
            rf'</\s*(?:invoke|tool_calls?|function_calls?|工具调用|函数调用|{_tool_names})\s*>',
            re.IGNORECASE,
        )

        def _emit(token: str):
            """Yield a SSE token event and append to accumulated_content."""
            nonlocal accumulated_content
            accumulated_content += token
            return f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

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
                    "tools": NARRATIVE_TOOLS,
                    "tool_choice": "none",
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
                        fr = chunk["choices"][0].get("finish_reason")
                        if fr:
                            finish_reason = fr
                        if content:
                            if in_xml_block:
                                # Inside confirmed XML tool-call — suppress all
                                xml_suppress_buffer += content
                                end_m = XML_END_RE.search(xml_suppress_buffer)
                                if end_m:
                                    after = xml_suppress_buffer[end_m.end():]
                                    in_xml_block = False
                                    xml_suppress_buffer = ""
                                    if after:
                                        yield _emit(after)
                            else:
                                # Check if this token starts or contains an XML tool-call tag.
                                # Use a robust approach: look for '<' that could be an XML tag start.
                                lt_idx = content.find('<')
                                if lt_idx >= 0:
                                    # Emit everything before '<'
                                    before = content[:lt_idx]
                                    if before:
                                        yield _emit(before)
                                    # Buffer from '<' onward to test against XML patterns
                                    xml_suppress_buffer = content[lt_idx:]
                                    # Test: does the buffer (from '<') match an XML tool-call start?
                                    if XML_START_RE.match(xml_suppress_buffer):
                                        in_xml_block = True
                                    elif '>' in xml_suppress_buffer:
                                        # Has '>' but doesn't match tool-call patterns — emit as text
                                        yield _emit(xml_suppress_buffer)
                                        xml_suppress_buffer = ""
                                    elif len(xml_suppress_buffer) > 300:
                                        # Suspicious but too long without pattern — flush
                                        yield _emit(xml_suppress_buffer)
                                        xml_suppress_buffer = ""
                                    # else: keep buffering across tokens to detect patterns
                                elif xml_suppress_buffer:
                                    # We're in "suspicious" mode (buffered a '<' earlier)
                                    xml_suppress_buffer += content
                                    if XML_START_RE.match(xml_suppress_buffer):
                                        in_xml_block = True
                                    elif '>' in xml_suppress_buffer:
                                        yield _emit(xml_suppress_buffer)
                                        xml_suppress_buffer = ""
                                    elif len(xml_suppress_buffer) > 300:
                                        yield _emit(xml_suppress_buffer)
                                        xml_suppress_buffer = ""
                                    # else: still buffering, wait for more
                                else:
                                    yield _emit(content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except (httpx.HTTPError, httpx.StreamError) as e:
            yield f"data: {json.dumps({'error': f'连接失败: {str(e)}'}, ensure_ascii=False)}\n\n"
            return

    # Parse accumulated content
    parsed = _parse_llm_content(accumulated_content)

    # Validate final response before applying state changes
    valid_resp, resp_err = validate_llm_response(
        parsed,
        current_location_id=state_dict.get("location_id", ""),
        locations=LOCATIONS,
        check_reachability=settings.ai_validation_reachability_check,
    )
    if not valid_resp:
        # Don't show raw validation error to player — retry with feedback
        yield f"data: {json.dumps({'token': '\n\n[生成内容有误，正在修正...]'}, ensure_ascii=False)}\n\n"
        validation_prompt = build_validation_error_prompt([resp_err])
        # Provide available location info to help the LLM correct itself
        nearby_locations = ", ".join(
            f"{lid}({LOCATIONS[lid]['name']})"
            for lid in state_dict.get("connected_locations", [])[:10]
            if lid in LOCATIONS
        )
        if nearby_locations:
            validation_prompt += f"\n\n当前可到达的地点ID列表：{nearby_locations}。请使用这些地点ID重新生成回复。"

        # Retry: use non-streaming call with validation error injected
        for retry in range(settings.ai_validation_max_retries + 1):
            retry_result = await generate_llm_response(
                user_input, state_dict, max_tokens,
                history, summary, event_prompts,
                validation_error=validation_prompt,
            )
            retry_err = retry_result.get("_validation_error", "")
            if not retry_err:
                # Success — yield the corrected narrative
                yield f"data: {json.dumps({'token': retry_result['narrative']}, ensure_ascii=False)}\n\n"

                # Continue with the corrected result (same flow as normal path below)
                parsed = retry_result
                valid_resp = True
                break
            validation_prompt = build_validation_error_prompt([retry_err])

        if not valid_resp:
            # All retries exhausted — provide graceful fallback
            fallback_narrative = _build_fallback_narrative(parsed, resp_err, state_dict)
            parsed = {"narrative": fallback_narrative, "choices": [], "state_changes": {}}
            yield f"data: {json.dumps({'token': fallback_narrative}, ensure_ascii=False)}\n\n"

    # Get fresh session from DB
    gs_result = await db_session.execute(
        select(GameSession).where(GameSession.id == state_dict["session_id"])
    )
    gs = gs_result.scalar_one()

    # Run Variable Agent to extract state changes from narrative
    if parsed.get("narrative"):
        try:
            var_changes = await extract_variable_changes(
                narrative=parsed["narrative"],
                current_state={
                    "game_date": gs.game_date,
                    "time_slot": gs.time_slot,
                    "location_id": gs.player_location_id,
                    "player_name": gs.player_name,
                },
                character_names=list(CHARACTER_LIBRARY.keys()),
                secret_info_ids=_collect_secret_info_ids(),
                hot_zone_npcs=state_dict.get("hot_zone_npcs", []),
            )
            parsed["state_changes"] = var_changes
            _log_var_changes(var_changes)
        except Exception as e:
            print(f"  [VariableAgent] Extraction failed: {e}")

    # Apply state changes and save dialogue
    await _apply_state_changes(gs, parsed.get("state_changes", {}), db_session)

    # Trigger daily settlement and lifecycle advance if date changed
    if getattr(gs, '_pending_settlement', None):
        settlement_date = gs._pending_settlement
        delattr(gs, '_pending_settlement')
        await daily_point_settlement(settlement_date)
        await _event_lifecycle_advance(db_session, settlement_date)
        await _run_forecaster_if_needed(db_session, settlement_date, gs.time_slot)

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
    fresh_state["active_events"] = active_events or []

    done_msg = {
        "done": True,
        "choices": parsed.get("choices", []),
        "state": fresh_state,
        "truncated": finish_reason == "length",
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
        state_data = _build_state_dict(gs)
        state_data["active_events"] = await _get_events_for_display(
            db, gs.player_location_id, gs.game_date, gs.time_slot,
            gs.player_char_id,
        )
        return JSONResponse(state_data)


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
            # Check for event triggers before LLM call
            event_prompts, active_events = await _check_and_fire_events(
                db, gs.player_location_id, gs.game_date, gs.time_slot,
                gs.player_char_id,
            )
            # Retry loop: if validation fails, feed error back to LLM
            result = None
            validation_error = ""
            for retry in range(settings.ai_validation_max_retries + 1):
                result = await generate_llm_response(
                    user_input, state_dict, max_tokens=max_tokens,
                    history=history, summary=summary,
                    event_prompts=event_prompts if event_prompts else None,
                    validation_error=validation_error,
                )
                err = result.get("_validation_error", "")
                if not err:
                    break
                validation_error = build_validation_error_prompt([err])
            # If all retries exhausted, build graceful fallback
            if result and result.get("_validation_error"):
                result["narrative"] = _build_fallback_narrative(
                    result, result["_validation_error"], state_dict
                )
                result["choices"] = result.get("choices", [])
                result["state_changes"] = {}
                result["_validation_error"] = ""

            # Run Variable Agent to extract state changes from narrative
            if result["narrative"]:
                try:
                    var_changes = await extract_variable_changes(
                        narrative=result["narrative"],
                        current_state={
                            "game_date": gs.game_date,
                            "time_slot": gs.time_slot,
                            "location_id": gs.player_location_id,
                            "player_name": gs.player_name,
                        },
                        character_names=list(CHARACTER_LIBRARY.keys()),
                        secret_info_ids=_collect_secret_info_ids(),
                        hot_zone_npcs=state_dict.get("hot_zone_npcs", []),
                    )
                    result["state_changes"] = var_changes
                    _log_var_changes(var_changes)
                except Exception as e:
                    print(f"  [VariableAgent] Extraction failed: {e}")
        else:
            result = generate_offline_response(user_input, state_dict)

        await _apply_state_changes(gs, result.get("state_changes", {}), db)

        # Trigger daily settlement and lifecycle advance if date changed
        if getattr(gs, '_pending_settlement', None):
            settlement_date = gs._pending_settlement
            delattr(gs, '_pending_settlement')
            await daily_point_settlement(settlement_date)
            await _event_lifecycle_advance(db, settlement_date)
            await _run_forecaster_if_needed(db, settlement_date, gs.time_slot)

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
        state_data["active_events"] = active_events if use_llm else []
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

        # Check for event triggers before LLM call
        event_prompts, active_events = await _check_and_fire_events(
            db, gs.player_location_id, gs.game_date, gs.time_slot,
            gs.player_char_id,
        )

        # Retry loop: if validation fails, feed error back to LLM
        result = None
        validation_error = ""
        for retry in range(settings.ai_validation_max_retries + 1):
            result = await generate_llm_response(
                user_input, state_dict, max_tokens=max_tokens,
                history=history, summary=summary,
                event_prompts=event_prompts if event_prompts else None,
                validation_error=validation_error,
            )
            err = result.get("_validation_error", "")
            if not err:
                break
            validation_error = build_validation_error_prompt([err])

        # If all retries exhausted, build graceful fallback
        if result and result.get("_validation_error"):
            result["narrative"] = _build_fallback_narrative(
                result, result["_validation_error"], state_dict
            )
            result["choices"] = result.get("choices", [])
            result["state_changes"] = {}
            result["_validation_error"] = ""

        # Run Variable Agent to extract state changes from narrative
        var_changes = {}
        if result and result["narrative"]:
            try:
                var_changes = await extract_variable_changes(
                    narrative=result["narrative"],
                    current_state={
                        "game_date": gs.game_date,
                        "time_slot": gs.time_slot,
                        "location_id": gs.player_location_id,
                        "player_name": gs.player_name,
                    },
                    character_names=list(CHARACTER_LIBRARY.keys()),
                    secret_info_ids=_collect_secret_info_ids(),
                    hot_zone_npcs=state_dict.get("hot_zone_npcs", []),
                )
                result["state_changes"] = var_changes
                _log_var_changes(var_changes)
            except Exception as e:
                print(f"  [VariableAgent] Extraction failed: {e}")

        await _apply_state_changes(gs, result.get("state_changes", {}), db)

        # Trigger daily settlement and lifecycle advance if date changed
        if getattr(gs, '_pending_settlement', None):
            settlement_date = gs._pending_settlement
            delattr(gs, '_pending_settlement')
            await daily_point_settlement(settlement_date)
            await _event_lifecycle_advance(db, settlement_date)
            await _run_forecaster_if_needed(db, settlement_date, gs.time_slot)

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
        state_data["active_events"] = active_events
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

        # Check for event triggers before LLM call
        event_prompts, stream_active_events = await _check_and_fire_events(
            db, gs.player_location_id, gs.game_date, gs.time_slot,
            gs.player_char_id,
        )
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
                event_prompts=event_prompts if event_prompts else None,
                active_events=stream_active_events,
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
    location_id = body.get("location_id", "classroom_1d")
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
        finish_reason = None
        xml_buf = ""
        in_xml = False
        xml_start_re = re.compile(r'<\s*(invoke|tool_calls|function_call)\b', re.IGNORECASE)
        xml_end_re = re.compile(r'</\s*(invoke|tool_calls|function_call)\s*>', re.IGNORECASE)
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
                            fr = chunk["choices"][0].get("finish_reason")
                            if fr:
                                finish_reason = fr
                            if content:
                                if in_xml:
                                    xml_buf += content
                                    end_m = xml_end_re.search(xml_buf)
                                    if end_m:
                                        after = xml_buf[end_m.end():]
                                        in_xml = False
                                        xml_buf = ""
                                        if after:
                                            accumulated += after
                                            yield f"data: {json.dumps({'token': after}, ensure_ascii=False)}\n\n"
                                else:
                                    # Robust detection: look for '<' that could start XML
                                    lt_idx = content.find('<')
                                    if lt_idx >= 0:
                                        before = content[:lt_idx]
                                        if before:
                                            accumulated += before
                                            yield f"data: {json.dumps({'token': before}, ensure_ascii=False)}\n\n"
                                        xml_buf = content[lt_idx:]
                                        if xml_start_re.match(xml_buf):
                                            in_xml = True
                                        elif '>' in xml_buf:
                                            accumulated += xml_buf
                                            yield f"data: {json.dumps({'token': xml_buf}, ensure_ascii=False)}\n\n"
                                            xml_buf = ""
                                        elif len(xml_buf) > 300:
                                            accumulated += xml_buf
                                            yield f"data: {json.dumps({'token': xml_buf}, ensure_ascii=False)}\n\n"
                                            xml_buf = ""
                                    elif xml_buf:
                                        xml_buf += content
                                        if xml_start_re.match(xml_buf):
                                            in_xml = True
                                        elif '>' in xml_buf:
                                            accumulated += xml_buf
                                            yield f"data: {json.dumps({'token': xml_buf}, ensure_ascii=False)}\n\n"
                                            xml_buf = ""
                                        elif len(xml_buf) > 300:
                                            accumulated += xml_buf
                                            yield f"data: {json.dumps({'token': xml_buf}, ensure_ascii=False)}\n\n"
                                            xml_buf = ""
                                    else:
                                        accumulated += content
                                        yield f"data: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

            # Final cleanup in case XML block didn't close properly
            if in_xml:
                accumulated, _ = _strip_xml_tool_calls(accumulated)

            done_msg = {
                "done": True,
                "perspective": accumulated,
                "target_npc": target_npc_name,
                "truncated": finish_reason == "length",
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
        state_dict["active_events"] = await _get_events_for_display(
            db, gs.player_location_id, gs.game_date, gs.time_slot,
            gs.player_char_id,
        )
        history = await _get_recent_history(db, gs.id, limit=settings.max_history_dialogues)
        summary = await _get_latest_summary(db, gs.id)

        response_data = {
            "has_save": True,
            "state": state_dict,
            "history": history,
            "summary": summary,
        }

        # Include opening narrative for new games
        if gs.dialogue_count_since_summary == 0:
            char_entry = CHARACTER_LIBRARY.get(gs.player_name, {})
            player_class = char_entry.get("class_name", "D") if char_entry else "D"
            response_data["opening_narrative"] = CLASS_OPENING_NARRATIVES.get(
                player_class, CLASS_OPENING_NARRATIVES["D"]
            )
            response_data["opening_class"] = player_class

        return JSONResponse(response_data)


@app.post("/api/game/reset")
async def game_reset(request: Request):
    """Reset game: deactivate old session, clear old secrets, create new one."""
    body = await request.json()
    player_name = body.get("player_name", "绫小路清隆")
    player_char_id = body.get("player_char_id")

    # Determine player class and classroom
    char_entry = CHARACTER_LIBRARY.get(player_name, {})
    player_class = char_entry.get("class_name", "D") if char_entry else "D"
    classroom_map = {"A": "classroom_1a", "B": "classroom_1b", "C": "classroom_1c", "D": "classroom_1d"}
    classroom_id = classroom_map.get(player_class, "classroom_1d")
    class_points_map = {"A": 940, "B": 650, "C": 490, "D": 0}
    default_class_points = class_points_map.get(player_class, 0)

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
            game_date="2024-05-01",
            time_slot="morning",
            player_location_id=classroom_id,
            class_points=default_class_points,
            private_points=100000,
            dialogue_count_since_summary=0,
        )
        db.add(new_gs)
        await db.commit()
        await db.refresh(new_gs)

        opening_narrative = CLASS_OPENING_NARRATIVES.get(player_class, CLASS_OPENING_NARRATIVES["D"])

        return JSONResponse({
            "success": True,
            "session_id": new_gs.id,
            "state": _build_state_dict(new_gs),
            "secrets_seeded": seeded,
            "opening_narrative": opening_narrative,
            "opening_class": player_class,
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


@app.get("/api/game/player_profile")
async def player_profile():
    """Get the player character's full profile from CHARACTER_LIBRARY."""
    async with async_session() as db:
        gs = await _get_or_create_session(db)
        char_entry = CHARACTER_LIBRARY.get(gs.player_name, {})
        if not char_entry:
            return JSONResponse({"error": "Character not found"}, status_code=404)
        return JSONResponse({
            "name": gs.player_name,
            "role_id": gs.player_char_id,
            "class_name": char_entry.get("class_name", "D"),
            "enrollment_year": char_entry.get("enrollment_year", "2024"),
            "traits": char_entry.get("traits", []),
            "private_points": char_entry.get("private_points", 100000),
            "spending_habit": char_entry.get("spending_habit", "normal"),
            "gender": char_entry.get("gender", ""),
            "portrait_image": char_entry.get("portrait_image", ""),
            "public_info": char_entry.get("public_info", []),
            "secrets": char_entry.get("secrets", []),
            "relations": char_entry.get("relations", []),
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
    """Import JSON data (characters, locations, events, worldview)."""
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
                    "enrollment_year": entry.get("enrollment_year", "2024"),
                    "traits": entry.get("traits", []),
                    "public_info": entry.get("public_info", []),
                    "secrets": entry.get("secrets", []),
                    "relations": entry.get("relations", []),
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
        from src.core.event_bus.bus import EventBus
        count = 0
        async with async_session() as db:
            bus = EventBus(db)
            if isinstance(data, dict):
                for event_id, definition in data.items():
                    await bus._upsert_event(event_id, definition)
                    count += 1
            elif isinstance(data, list):
                for item in data:
                    event_id = item.get("event_id", item.get("name", f"event_{count}"))
                    await bus._upsert_event(event_id, item)
                    count += 1
            await db.commit()
        return JSONResponse({"success": True, "imported": count, "type": "events"})

    elif import_type == "worldview":
        import os
        worldview_path = os.path.join(os.path.dirname(__file__), "config", "data", "worldview_extracted.json")
        os.makedirs(os.path.dirname(worldview_path), exist_ok=True)
        with open(worldview_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return JSONResponse({"success": True, "imported": 1, "type": "worldview"})

    return JSONResponse({"success": False, "error": f"Unknown import type: {import_type}"})


# ---- Startup data loading ----

def _load_extracted_data():
    """Load characters, locations, and worldview from extracted JSON files at startup."""
    import json as _json
    import os as _os

    script_dir = _os.path.dirname(_os.path.abspath(__file__))
    output_dir = _os.path.join(script_dir, "..", "scripts", "output")

    # Load characters
    chars_path = _os.path.join(output_dir, "characters_extracted.json")
    if _os.path.exists(chars_path):
        with open(chars_path, "r", encoding="utf-8") as f:
            chars_data = _json.load(f)
        for entry in chars_data.get("data", []):
            name = entry.get("name", "")
            if name:
                traits = entry.get("traits", [])
                # Preserve existing schedule_weights if extracted data lacks them
                existing = CHARACTER_LIBRARY.get(name, {})
                existing_sw = existing.get("schedule_weights")
                CHARACTER_LIBRARY[name] = {
                    "role_id": entry.get("role_id", f"imported_{name}"),
                    "class_name": entry.get("class_name", "D"),
                    "enrollment_year": entry.get("enrollment_year", "2024"),
                    "traits": traits,
                    "public_info": entry.get("public_info", []),
                    "secrets": entry.get("secrets", []),
                    "relations": entry.get("relations", []),
                    "private_points": entry.get("private_points", 100000),
                    "spending_habit": _derive_spending_habit(traits),
                    "schedule_weights": entry.get("schedule_weights") or existing_sw,
                    "dorm_room_id": entry.get("dorm_room_id", ""),
                    "gender": entry.get("gender", ""),
                    "portrait_image": entry.get("portrait_image", ""),
                }
        print(f"  [Startup] Loaded {len(chars_data.get('data', []))} characters from extracted JSON")

    # Load locations
    locs_path = _os.path.join(output_dir, "locations_extracted.json")
    if _os.path.exists(locs_path):
        with open(locs_path, "r", encoding="utf-8") as f:
            locs_data = _json.load(f)
        for entry in locs_data.get("data", []):
            lid = entry.get("location_id", "")
            if not lid:
                continue
            if lid not in LOCATIONS:
                LOCATIONS[lid] = {
                    "location_id": lid,
                    "name": entry.get("name", lid),
                    "description": entry.get("description", ""),
                    "tags": entry.get("tags", []),
                    "connected_to": entry.get("connected_to", []),
                    "parent_zone": entry.get("parent_zone"),
                    "zone_name": entry.get("zone_name", ""),
                    "floor": entry.get("floor", ""),
                    "scene_image": entry.get("scene_image", ""),
                }
            else:
                # Merge connected_to and scene_image from JSON so scripts can update existing locations
                json_conn = entry.get("connected_to", [])
                if json_conn:
                    existing_conn = set(LOCATIONS[lid].get("connected_to", []))
                    for c in json_conn:
                        existing_conn.add(c)
                    LOCATIONS[lid]["connected_to"] = sorted(existing_conn)
                json_scene = entry.get("scene_image", "")
                if json_scene:
                    LOCATIONS[lid]["scene_image"] = json_scene
        # Load ZONES from JSON if present (supplements hardcoded ZONES)
        for zone_entry in locs_data.get("zones", []):
            zid = zone_entry.get("zone_id", "")
            if zid and zid not in ZONES:
                ZONES[zid] = {
                    "zone_id": zid,
                    "name": zone_entry.get("name", zid),
                    "description": zone_entry.get("description", ""),
                    "type": zone_entry.get("type", "campus"),
                    "sub_locations": zone_entry.get("sub_locations", []),
                    "entry_points": zone_entry.get("entry_points", []),
                }
        print(f"  [Startup] Loaded {len(locs_data.get('data', []))} locations and {len(locs_data.get('zones', []))} zones from extracted JSON")

    # Load worldview into module-level variable
    global WORLDVIEW_CONTEXT
    worldview_path = _os.path.join(script_dir, "config", "data", "worldview_extracted.json")
    if _os.path.exists(worldview_path):
        with open(worldview_path, "r", encoding="utf-8") as f:
            wv = _json.load(f)
        # Handle both dict and list formats
        if isinstance(wv, list):
            wv = wv[0] if wv else {}
        if not isinstance(wv, dict):
            wv = {}
        parts = []
        parts.append(f"学校：{wv.get('school_name', '高度育成高等学校')}")
        parts.append(f"理念：{wv.get('founding_principles', '')}")
        cs = wv.get("class_system", {}) if isinstance(wv.get("class_system"), dict) else {}
        if cs:
            parts.append(f"班级制度：{cs.get('description', '')}")
            parts.append(f"排名机制：{cs.get('ranking_mechanism', '')}")
        sps = wv.get("s_point_system", {}) if isinstance(wv.get("s_point_system"), dict) else {}
        if sps:
            parts.append(f"S点数制度：{sps.get('description', '')}")
            parts.append(f"每月分配：{sps.get('monthly_allocation', '')}")
        parts.append(f"特别考试：{wv.get('special_exam_overview', '')}")
        for rule in wv.get("rules", []):
            parts.append(f"【{rule.get('name', '')}】{rule.get('content', '')}")
        WORLDVIEW_CONTEXT = "\n".join(parts)
        print(f"  [Startup] Loaded worldview ({len(WORLDVIEW_CONTEXT)} chars)")


# ---- Event Test API ----

@app.get("/api/test/events")
async def test_list_events():
    """List all events with trigger conditions for the test panel."""
    from src.models.event import DynamicEvent, Event

    async with async_session() as db:
        # Static events from DB
        stmt = select(Event).order_by(Event.required_date, Event.name)
        result = await db.execute(stmt)
        static_events = result.scalars().all()

        # Dynamic events from DB
        dyn_stmt = select(DynamicEvent).where(
            DynamicEvent.is_expired == False
        ).order_by(DynamicEvent.trigger_date_start, DynamicEvent.name)
        dyn_result = await db.execute(dyn_stmt)
        dynamic_events = dyn_result.scalars().all()

        def _ev_info(ev, is_dynamic=False):
            if is_dynamic:
                conditions = {
                    "location": ev.trigger_location,
                    "date_start": ev.trigger_date_start,
                    "date_end": ev.trigger_date_end,
                }
                return {
                    "id": ev.id,
                    "template_id": ev.id,
                    "name": ev.name,
                    "type": ev.event_type.value if ev.event_type else "ai_guided_choice",
                    "phase": "pending",
                    "is_active": ev.is_triggered,
                    "trigger_conditions": conditions,
                    "is_dynamic": True,
                }
            else:
                conditions = {
                    "required_date": ev.required_date,
                    "required_location": ev.required_location,
                    "required_time_slot": ev.required_time_slot,
                    "required_player_char": ev.required_player_char,
                }
                # Resolve location name
                loc_name = ""
                if ev.required_location and ev.required_location in LOCATIONS:
                    loc_name = LOCATIONS[ev.required_location]["name"]
                return {
                    "id": ev.id,
                    "template_id": ev.template_id,
                    "name": ev.name,
                    "type": ev.event_type.value if ev.event_type else "fixed_story",
                    "phase": ev.phase.value if ev.phase else "pending",
                    "is_active": ev.is_active,
                    "trigger_conditions": conditions,
                    "location_name": loc_name,
                    "is_dynamic": False,
                }

        events = [_ev_info(e) for e in static_events] + [_ev_info(e, True) for e in dynamic_events]

        return JSONResponse({"events": events})


@app.post("/api/test/trigger_event")
async def test_trigger_event(request: Request):
    """Adjust game state to match an event's trigger conditions."""
    body = await request.json()
    event_id = body.get("event_id", "")
    is_dynamic = body.get("is_dynamic", False)
    clear_history = body.get("clear_history", False)

    async with async_session() as db:
        gs_result = await db.execute(
            select(GameSession).where(GameSession.is_active == True).limit(1)
        )
        gs = gs_result.scalar_one_or_none()
        if gs is None:
            return JSONResponse({"error": "没有活跃的游戏会话"}, status_code=400)

        changes = {}
        trigger = body.get("trigger_conditions", {})

        if is_dynamic:
            loc = trigger.get("location")
            date_start = trigger.get("date_start")
            if loc and loc in LOCATIONS:
                changes["new_location_id"] = loc
                changes["location_changed"] = True
            if date_start:
                old_date = gs.game_date
                gs.game_date = date_start
                if old_date != date_start:
                    changes["new_game_date"] = date_start
        else:
            req_date = trigger.get("required_date")
            req_location = trigger.get("required_location")
            req_time_slot = trigger.get("required_time_slot")

            if req_date and req_date != gs.game_date:
                gs.game_date = req_date
                changes["new_game_date"] = req_date

            if req_location and req_location != gs.player_location_id:
                if req_location in LOCATIONS:
                    gs.player_location_id = req_location
                    changes["new_location_id"] = req_location
                    changes["location_changed"] = True

            if req_time_slot and req_time_slot != gs.time_slot:
                gs.time_slot = req_time_slot
                changes["new_time_slot"] = req_time_slot

        if clear_history:
            from src.models.dialogue import DialogueLog, StorySummary
            from sqlalchemy import delete

            del_dialogue = delete(DialogueLog).where(DialogueLog.session_id == gs.id)
            del_result = await db.execute(del_dialogue)
            del_summary = delete(StorySummary).where(StorySummary.session_id == gs.id)
            await db.execute(del_summary)
            gs.dialogue_count_since_summary = 0
            changes["history_cleared"] = del_result.rowcount
            print(f"  [TestPanel] Cleared {del_result.rowcount} dialogues for session {gs.session_slug}")

        await db.commit()
        await db.refresh(gs)

        state = _build_state_dict(gs)
        return JSONResponse({
            "success": True,
            "event_id": event_id,
            "applied_changes": changes,
            "state": {
                "game_date": gs.game_date,
                "time_slot": gs.time_slot,
                "location_id": gs.player_location_id,
                "location": state.get("location", {}),
            },
        })


# ---- Startup ----

@app.on_event("startup")
async def on_startup():
    """Initialize database and load extracted data on server startup."""
    await init_db()
    _load_extracted_data()


# ---- Main ----

def main():
    import asyncio
    import uvicorn

    # Initialize database before starting server
    asyncio.run(init_db())

    # Load extracted data (characters, locations) into in-memory structures
    _load_extracted_data()

    print("=" * 60)
    print("  实教AI模拟器 - Web前端服务器 (SQLite版)")
    print("  数据库: elite_simulator.db")
    print(f"  角色库: {len(CHARACTER_LIBRARY)}人 | 地点: {len(LOCATIONS)}处 | 事件: 已导入")
    print("  打开浏览器访问: http://localhost:8001")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    main()
