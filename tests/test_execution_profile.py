import pytest
from sst.processor import LocalProcessor
from sst.config import Config

class MockDB:
    pass

@pytest.fixture
def base_config():
    return Config(
        steam_install_path="/tmp",
        llm_album_tier_small_max_tracks=50,
        llm_album_tier_medium_max_tracks=100,
        llm_ollama_num_ctx_small=8192,
        llm_ollama_num_ctx_medium=16384,
        llm_ollama_num_ctx_large=32768,
        llm_request_parallelism_max_workers_small=3,
        llm_request_parallelism_max_workers_medium=2,
        llm_request_parallelism_max_workers_large=1,
    )

def test_profile_small_tier(base_config):
    processor = LocalProcessor(base_config, MockDB())
    profile = processor._build_album_execution_profile(30)
    
    assert profile.tier_name == "Small"
    assert profile.num_ctx_cap == 8192
    assert profile.phase2_parallel_workers == 3
    assert not profile.prefer_one_shot

def test_profile_medium_tier(base_config):
    processor = LocalProcessor(base_config, MockDB())
    profile = processor._build_album_execution_profile(75)
    
    assert profile.tier_name == "Medium"
    assert profile.num_ctx_cap == 16384
    assert profile.phase2_parallel_workers == 2
    assert profile.prefer_one_shot

def test_profile_large_tier(base_config):
    processor = LocalProcessor(base_config, MockDB())
    profile = processor._build_album_execution_profile(120)
    
    assert profile.tier_name == "Large"
    assert profile.num_ctx_cap == 32768
    assert profile.phase2_parallel_workers == 1
    assert profile.prefer_one_shot

def test_profile_edge_cases(base_config):
    processor = LocalProcessor(base_config, MockDB())
    
    # Exactly 50 -> Small
    p_50 = processor._build_album_execution_profile(50)
    assert p_50.tier_name == "Small"
    
    # Exactly 100 -> Medium
    p_100 = processor._build_album_execution_profile(100)
    assert p_100.tier_name == "Medium"
    
    # 101 -> Large
    p_101 = processor._build_album_execution_profile(101)
    assert p_101.tier_name == "Large"
