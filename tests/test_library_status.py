import pytest

from game_web.services.library_status import derive_library_status


def test_library_status_prefers_needs_setup_over_done_job():
    status = derive_library_status(
        meili_state="connection_failed",
        has_dataset=True,
        config_valid=True,
        latest_relevant_job_status="done",
    )

    assert status.state == "Needs setup"
    assert status.detail_next_step.key == "settings"


def test_library_status_returns_needs_dataset_without_dataset():
    status = derive_library_status(
        meili_state="reachable",
        has_dataset=False,
        config_valid=False,
        latest_relevant_job_status="done",
    )

    assert status.state == "Needs dataset"
    assert status.detail_next_step.key == "upload"


def test_library_status_maps_failed_for_invalid_config_with_dataset():
    status = derive_library_status(
        meili_state="reachable",
        has_dataset=True,
        config_valid=False,
        latest_relevant_job_status=None,
    )

    assert status.state == "Failed"
    assert status.detail_next_step.key == "fix_config"


@pytest.mark.parametrize(
    ("job_status", "state", "next_step_key"),
    [
        ("queued", "Queued", "run_queue"),
        ("running", "Building", "view_job"),
        ("failed", "Failed", "view_job"),
        ("done", "Searchable", "search"),
    ],
)
def test_library_status_maps_relevant_job_states(job_status, state, next_step_key):
    status = derive_library_status(
        meili_state="reachable",
        has_dataset=True,
        config_valid=True,
        latest_relevant_job_status=job_status,
    )

    assert status.state == state
    assert status.detail_next_step.key == next_step_key
