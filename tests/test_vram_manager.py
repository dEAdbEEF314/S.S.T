from sst.vram_manager import VramResourceManager


def _build_manager(bytes_per_token: int = 1024, budget_bytes: int = 1024 * 1024) -> VramResourceManager:
    manager = VramResourceManager.__new__(VramResourceManager)
    manager.base_url = "http://localhost:11434"
    manager.model = "test-model"
    manager.bytes_per_token = bytes_per_token
    manager.kv_budget_bytes = budget_bytes
    return manager


def test_calculate_max_workers_uses_fixed_context_slots():
    manager = _build_manager(bytes_per_token=1024, budget_bytes=4 * 1000 * 1024)

    workers = manager.calculate_max_workers(fixed_num_ctx=1000, default_workers=4)

    assert workers == 4


def test_calculate_max_workers_keeps_at_least_one_slot():
    manager = _build_manager(bytes_per_token=1024, budget_bytes=4096)

    workers = manager.calculate_max_workers(fixed_num_ctx=10000, default_workers=4)

    assert workers == 1


def test_effective_parallel_slots_are_capped_by_server_limit():
    manager = _build_manager(bytes_per_token=1024, budget_bytes=8 * 1000 * 1024)

    vram_workers = manager.calculate_max_workers(fixed_num_ctx=1000, default_workers=8)
    server_slots = 4

    assert min(vram_workers, server_slots) == 4