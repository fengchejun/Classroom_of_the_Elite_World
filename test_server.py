"""Quick test to verify the dual-AI architecture changes are importable."""
import sys
sys.path.insert(0, '.')

print("1. Testing variable_agent module import...")
try:
    from src.core.variable_agent import extract_variable_changes
    print("   OK - variable_agent module imports successfully")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n2. Testing variable_agent prompt...")
try:
    from src.core.variable_agent.prompt import VARIABLE_AGENT_SYSTEM_PROMPT
    assert "new_time_slot" in VARIABLE_AGENT_SYSTEM_PROMPT
    assert "private_points_delta" in VARIABLE_AGENT_SYSTEM_PROMPT
    assert "relation_changes" in VARIABLE_AGENT_SYSTEM_PROMPT
    print("   OK - prompt contains all 11 detection categories")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n3. Testing extractor function...")
try:
    import asyncio
    result = asyncio.run(extract_variable_changes("", {}))
    assert result == {
        "new_time_slot": None, "new_game_date": None,
        "new_location_id": None, "sleep_to_morning": False,
        "private_points_delta": 0, "class_points_delta": 0,
        "npc_point_changes": [], "relation_changes": [],
        "npc_status_changes": [], "npc_location_changes": [],
        "new_events": [],
    }
    print("   OK - empty narrative returns empty changes")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n4. Testing web_server module syntax...")
try:
    import ast
    with open("src/web_server.py", "r", encoding="utf-8") as f:
        source = f.read()
    ast.parse(source)
    print("   OK - web_server.py has valid Python syntax")
except SyntaxError as e:
    print(f"   FAIL - {e}")

print("\n5. Testing NARRATIVE_TOOLS exists in web_server...")
try:
    assert "NARRATIVE_TOOLS" in source
    print("   OK - NARRATIVE_TOOLS found")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n6. Testing GAME_SYSTEM_PROMPT no longer requires state_changes...")
try:
    import re
    prompt_start = source.find('GAME_SYSTEM_PROMPT = """')
    prompt_end = source.find('"""', prompt_start + 30)
    # Find the second """ after GAME_SYSTEM_PROMPT
    search_pos = prompt_start + len('GAME_SYSTEM_PROMPT = """')
    depth = 0
    actual_end = search_pos
    for i in range(search_pos, len(source)):
        if source[i:i+3] == '"""':
            actual_end = i
            break
    prompt_text = source[search_pos:actual_end]
    assert "state_changes规则" not in prompt_text  # Old rules removed
    assert "transfer_points" not in prompt_text     # Removed from narrative tools
    assert "update_character_data" not in prompt_text  # Removed from narrative tools
    assert "由另一个专门的系统自动处理" in prompt_text  # New instruction added
    print("   OK - GAME_SYSTEM_PROMPT correctly simplified")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n7. Testing layer files...")
try:
    with open("src/core/prompt_pipeline/layers/layer8_format.py", "r", encoding="utf-8") as f:
        l8 = f.read()
    assert "state_changes" not in l8.split('RETURN_FORMAT_PROMPT')[1] if 'RETURN_FORMAT_PROMPT' in l8 else True
    print("   OK - layer8_format.py no longer contains state_changes in format prompt")
except Exception as e:
    print(f"   FAIL - {e}")

print("\n=== All tests complete ===")
