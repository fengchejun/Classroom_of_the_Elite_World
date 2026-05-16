"""
Clean up events: remove events with high randomness and low plot impact.
Keep: special exams, major story beats, critical character developments.
Remove: minor daily interactions, random encounters, minigames.
"""
import json
from pathlib import Path
import shutil

INPUT = Path(__file__).resolve().parent / "output" / "events_extracted.json"
BACKUP = Path(__file__).resolve().parent / "output" / "events_extracted_backup.json"
OUTPUT = INPUT

# ================================================================
# Events to KEEP explicitly (event IDs with high plot relevance)
# These are identified by: rules_appendix, special exam, major plot
# ================================================================

# Keywords in event NAME that indicate the event SHOULD BE KEPT
KEEP_NAME_KEYWORDS = [
    # Core anchor events
    "入学日", "点数归零", "辅导室", "社团说明会",
    # Special exams (all types)
    "特别考试", "无人岛", "期中考试", "期末考试", "期末考",
    "Paper Shuffle", "体育祭", "文化祭", "合宿", "教育旅行",
    "选拔项目", "全场一致", "班级投票",
    # Major plot events
    "须藤打架", "审议", "茶柱", "威胁绫小路",
    "父亲来访", "真相", "坂柳", "南云",
    # Key character moments
    "栉田", "龙园", "一之濑", "堀北学", "轻井泽",
    "平田", "铃音", "佐仓",
    # System events
    "班级点数", "退学", "考试范围",
    # Graduation/system
    "毕业", "学年末",
]

# Keywords in event NAME that indicate LOW PLOT IMPACT (should be REMOVED)
REMOVE_NAME_KEYWORDS = [
    # Minigames and trivial activities
    "虚拟游戏", "料理对决", "自带盒饭", "排球赛", "游泳课",
    "澡堂", "尺寸", "枕头大战", "卡拉OK", "KTV",
    "打雪仗", "拔河", "抽鬼牌", "赌博",
    # Minor daily interactions
    "便利店", "超市偶遇", "水壶卡手", "占卜师",
    "优格机", "拍照", "料理考验", "生日礼物",
    # Random social events
    "双重约会", "圣诞礼物", "圣诞节约会", "情人节巧克力",
    "女生慰劳会", "游泳池聚会", "庆功宴",
    # Minor conversations without plot weight
    "走廊对话", "偶遇", "闲聊", "探望",
    "船尾对话", "甲板对话", "澡堂对话",
    # Non-essential side stories
    "暑假开幕", "暑假旅行前", "寒假", "暑假尾声",
    "女仆装", "健身房", "委托",
]

# Specific event IDs to REMOVE (low-impact, random events)
REMOVE_EVENT_IDS = {
    # Minigames / trivial activities
    "swimming_class",                     # 游泳课与男生赌局
    "bathroom_size_contest",              # 澡堂男性尺寸比赛
    "0173_虚拟游戏体验",                   # 虚拟游戏体验
    "0171_自带盒饭日与料理对决",           # 自带盒饭日与料理对决
    "D班_vs_B班_排球赛",                   # 泳池排球对抗赛
    "education_trip_day4_snowball_fight",  # 打雪仗比赛
    "evening_card_game_with_nagumo",      # 抽鬼牌游戏
    "day5_tug_of_war_koenji",            # 拔河对决
    "event_hotel_arrival_and_pillow_fight", # 枕头大战

    # Minor daily life / random encounters
    "event_0051_water_bottle_incident",   # 水壶卡手事件
    "event_0050_gekou_birthday_gift",     # 葛城的生日礼物
    "event_0050_gekou_sister_gift",       # 葛城为妹妹送礼
    "event_0050_sudou_mail_delivery",     # 须藤寄送礼物
    "event_0048_0049_summer_vacation_ending", # 暑假尾声与占卜师
    "christmas_day_yogurt_machine_failure", # 圣诞节抢购优格机失败
    "christmas_tree_photo_session",       # 圣诞树前的拍照活动
    "christmas_eve_flu_outbreak",         # 平安夜流感爆发
    "convenience_store_encounter_2025_02_05", # 便利商店的偶遇

    # Social hangouts without plot consequence
    "christmas_double_date",              # 圣诞节双重约会
    "airi_christmas_gift",                # 佐仓爱里的圣诞礼物
    "celebration_party",                  # 庆功宴
    "0246_一之濑班女生慰劳会",             # 女生慰劳会
    "0246_姬野船尾对话",                   # 船尾甲板交谈
    "0246_桐山约见游泳池",                 # 游泳池约见
    "0248_私人游泳池聚会",                 # 私人游泳池聚会
    "0248_轻井泽与佐藤交谈",               # 轻井泽与佐藤报告恋情
    "0412_C班的校园生活",                  # C班卡拉OK聚会
    "day5_evening_with_hamaguchi",        # 与滨口组共进晚餐

    # Minor conversations without narrative weight
    "0206_koenji_conversation",           # 与高圆寺走廊对话
    "0247_坂柳与绫小路甲板对话",           # 坂柳与绫小路甲板对话
    "event_6",                            # 超市偶遇
    "event_hot_bath_conversation",        # 大浴场女生对话

    # Cooking/minor tests
    "cooking_test_with_tenzawa",          # 天泽料理考验
    "encounter_with_tenzawa_ichika",      # 天泽料理考验执行

    # Trivial side events
    "0423_shu_luo",                       # 岛崎商谈
    "hasebe_special_01_watching_idol_show", # 观看偶像节目
    "gym_teacher_request",               # 真嶋老师私人委托

    # Summer vacation non-plot events
    "0244_暑假开幕",                       # 愉快暑假开幕
    "0170_暑假旅行前的早晨",               # 暑假旅行前的早晨

    # Non-essential love/social stuff
    "event_0127_01",                      # 王美雨恋爱咨询
    "event_0129_01",                      # 情人节巧克力
    "event_0130_01",                      # 桥本跟踪试探

    # Duplicate/near-duplicate events
    "first_month_zero_points",            # 与 first_month_end 重复

    # Removed from explicit remove list — these are actually important:
    # "first_meeting_and_bus_seat" — key character introduction
}

# Events to KEEP even if they would be caught by REMOVE filters
KEEP_EVENT_IDS = {
    # Core anchor events (May 1st timeframe)
    "guidance_room_meeting",
    "may_first_revelation",
    "first_day_of_school",
    "club_introduction_meeting",
    "class_d_assignment",
    "attempt_to_befriend_horikita",
    "first_meeting_and_bus_seat",

    # Important plot events that might get caught by filters
    "midterm_exam_announcement",           # 期中考试通知
    "event_4",                             # 绫小路与月城决战
    "c_d_alliance_decision_to_avoid_battle",  # CD同盟避战决策
    "c_d_alliance_formation",              # CD同盟结成
    "cd_alliance_formation",               # CD同盟正式结成
    "exam_range_change",                   # 考试范围变更通知
    "0248_葛城与时任争执",                  # 葛城分歧（C班内部重要事件）

    # Major character development moments
    "ayanokoji_karuizawa_incident",        # 绫小路与轻井泽交易
    "chabashira_satoru_confession",        # 茶柱告解
    "ayanokoji_confession_to_keisei",      # 告白（重要关系转折）
    "ayanokoji_confrontation_with_moonlight", # 与月城对峙
    "event_1",                             # 一之濑告白与警告
    "event_2",                             # 绫小路与南云对峙
    "event_3",                             # 堀北与天泽战斗

    # Anime-original / side stories that are part of core narrative
    "0424_ping_jing_de_kao_shi",           # 平静的考试
    "0425_liao_jie_dui_fang",             # 了解对方
    "0426_zhi_shi_de_tan_qiu",            # 知识的探求
    "0427_shan_cun_de_yong_qi",           # 山村的勇气
    "0428_huo_xi_fu_yi_fu_huo_xi_fu",    # 祸兮福所倚
    "0422_qiluan_yi_du_ba",               # 七濑的独白

    # Key strategic/class events
    "c_class_spy_investigation_2024_10",   # 龙园揪出间谍
    "hashimoto_ryuuen_midnight_meeting",   # 桥本龙园密会
    "hashimoto_betrayal_details_revealed", # 桥本背叛详情
    "ayanokoji_learns_he_is_target",       # 绫小路得知被选为退学目标

    # Important class dynamics
    "class_policy_meeting",                # D班体育祭方针讨论
    "final_exam_results",                  # 期末考结果公布
    "haruka_revenge_plan",                 # 长谷部复仇计划
    "haruka_hasebe_confrontation",         # 长谷部对峙
    "hasebe_and_miyake_return",           # 长谷部三宅回归

    # Year 2 major events
    "0204_ayanokouji_group_reconciliation", # 绫小路组和解
    "0204_math_full_score_revelation",     # 数学满分引发质疑
    "0205_horimi_joins_student_council",   # 堀北加入学生会
    "0205_keisei_room_date_interrupted",   # 轻井泽房间被打断
    "0205_sudou_confrontation",           # 须藤质问认可

    # Year 3 major events
    "ayano_keisei_breakup",               # 分手（重要转折）
    "b_class_surprise_attack",            # 龙园奇袭C班
    "c_class_defeat_at_g11",              # C班败北

    # Education trip important moments
    "education_trip_day3_dinner_confrontation",  # 龙园栉田对峙
    "education_trip_day3_evening_talk",          # 绫小路堀北谈话
    "education_trip_day4_evening_ichinose_crisis", # 一之濑崩溃
    "education_trip_day4_evening_meeting",        # 绫小路坂柳神崎会面

    # Important silent events
    "first_month_end",                     # 四月结束点数归零
    "class_points_update_after_exam",      # 班级点数更新
    "0245_八月班级点数公布",               # 八月班级点数
    "0206_sakayanagi_ichinose_alliance",  # 坂柳一之濑秘密同盟

    # Important conversations on ships/decks (plot-relevant)
    "0247_坂柳与绫小路甲板对话",           # White Room关键对话
    "0247_坂柳与天泽接触",                 # 天泽身份揭露

    # Important minor events that are part of larger arcs
    "event_0130_02",                       # 绫小路探望生病的一之濑
    "event_0127_03",                       # 深夜匿名电话（谣言事件线）
    "0233_fight_against_loneliness",       # 伊吹冲突（无人岛考试）
    "event_0130_03",                       # C班讨论区谣言事件
    "event_0130_04",                       # A班D班冲突
    "event_0130_05",                       # 一之濑公开忏悔
    "event_0130_06",                       # 坂柳绫小路对决约定
    "event_0128_02",                       # 神室背叛与坦白

    # Additional Year 2 important events
    "0245_无人岛考试结果公开",             # 考试结果公开
    "0245_石崎邀约看结果",                 # 石崎邀约
    "0245_池告白与探望小宫",               # 池告白

    # Day 5-7 island exam events (part of major exam arc)
    "day5_meeting_ryuen_katsuragi",        # 龙园葛城会面
    "day5_meeting_sakurako",               # 坂柳会面
    "day6_climbing_cliff",                 # 攀越悬崖
    "day6_first_year_meeting",             # 一年级代表集会
    "day7_ichinose_overhearing",           # 一之濑偷听
    "day7_kushida_stalking",               # 栉田尾随
    "day7_sevena_confrontation",           # 七濑摊牌
    "day7_sevena_surrender",               # 七濑投降

    # Exchange meeting important events
    "exchange_meeting_day3_archery",       # 射箭比赛
    "exchange_meeting_day3_shogi",         # 将棋比赛
    "exchange_meeting_end_nagumo_conversation", # 南云对话

    # Other important events
    "ayanokoji_self_reflection_after_departure", # 绫小路自我反思
}


def should_keep_event(event_id: str, edef: dict) -> bool:
    """Determine if an event should be kept based on plot relevance."""
    name = edef.get("name", "")
    etype = edef.get("type", "")
    rules = edef.get("rules_appendix", "")
    prompt = edef.get("active_prompt", "") or ""
    foreshadow = edef.get("foreshadow_prompt", "") or ""

    # Explicitly keep
    if event_id in KEEP_EVENT_IDS:
        return True

    # Explicitly remove
    if event_id in REMOVE_EVENT_IDS:
        return False

    # All events with rules_appendix are special exams or major events -> KEEP
    if rules:
        return True

    # Check REMOVE name keywords first
    for kw in REMOVE_NAME_KEYWORDS:
        if kw in name:
            return False

    # Check KEEP name keywords
    for kw in KEEP_NAME_KEYWORDS:
        if kw in name:
            return True

    # ai_guided_choice events with no rules and short prompts are usually
    # minor random interactions — remove them
    if etype == "ai_guided_choice":
        prompt_len = len(prompt)
        # Very short prompts suggest low-effort random events
        if prompt_len < 40:
            return False
        # ai_guided_choice without any KEEP keyword... evaluate further
        # If the prompt doesn't mention key plot elements, remove
        key_plot_words = ["退学", "班级", "考试", "点数", "A班", "B班", "C班", "D班",
                          "学生会", "White Room", "白屋", "月城", "坂柳", "南云",
                          "龙园", "堀北", "绫小路", "一之濑"]
        if not any(w in prompt for w in key_plot_words):
            return False

    # silent_fixed events with no rules are usually background flavor
    if etype == "silent_fixed" and not rules:
        # Keep only if it mentions class points, exams, or major events
        key_words = ["点数", "退学", "考试", "A班", "B班", "C班", "D班", "同盟",
                     "结盟", "间谍", "背叛"]
        if not any(w in prompt or w in name for w in key_words):
            return False

    return True


def main():
    # Backup
    if not BACKUP.exists():
        shutil.copy2(INPUT, BACKUP)
        print(f"Backup created: {BACKUP}")

    with open(INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data["data"]
    total_before = len(events)

    kept = {}
    removed = []

    for eid, edef in events.items():
        if should_keep_event(eid, edef):
            kept[eid] = edef
        else:
            removed.append((eid, edef.get("name", "")))

    data["data"] = kept
    total_after = len(kept)

    # Report
    print(f"Events before: {total_before}")
    print(f"Events after:  {total_after}")
    print(f"Removed:       {total_before - total_after}")
    print(f"\n--- Removed events ---")
    for eid, name in sorted(removed, key=lambda x: x[1]):
        print(f"  [{eid}] {name}")

    # Save
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()
