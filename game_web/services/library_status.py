from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DetailNextStepView:
    key: Literal["upload", "run_queue", "view_job", "search", "settings", "fix_config"]
    href: str
    label: str


@dataclass(frozen=True)
class LibraryStatusView:
    state: Literal["Needs setup", "Needs dataset", "Queued", "Building", "Failed", "Searchable"]
    message: str
    detail_next_step: DetailNextStepView


_DETAIL_NEXT_STEPS: dict[str, DetailNextStepView] = {
    "upload": DetailNextStepView("upload", "#dataset-build", "Upload dataset"),
    "run_queue": DetailNextStepView("run_queue", "/jobs", "Run next queued job"),
    "view_job": DetailNextStepView("view_job", "#recent-build", "View recent build"),
    "search": DetailNextStepView("search", "/search", "Search library"),
    "settings": DetailNextStepView("settings", "/settings", "Open settings"),
    "fix_config": DetailNextStepView("fix_config", "#search-configuration", "Fix configuration"),
}


def derive_library_status(
    *,
    meili_state: str,
    has_dataset: bool,
    config_valid: bool,
    latest_relevant_job_status: str | None,
) -> LibraryStatusView:
    """Apply the frozen-spec readiness precedence for one library."""
    if meili_state != "reachable":
        return LibraryStatusView(
            state="Needs setup",
            message="Open settings to save a working Meilisearch connection.",
            detail_next_step=_DETAIL_NEXT_STEPS["settings"],
        )

    if not has_dataset:
        return LibraryStatusView(
            state="Needs dataset",
            message="No dataset uploaded yet.",
            detail_next_step=_DETAIL_NEXT_STEPS["upload"],
        )

    if not config_valid:
        return LibraryStatusView(
            state="Failed",
            message="Fix the search configuration and queue a new build.",
            detail_next_step=_DETAIL_NEXT_STEPS["fix_config"],
        )

    if latest_relevant_job_status == "queued":
        return LibraryStatusView(
            state="Queued",
            message="A build is queued for the latest dataset.",
            detail_next_step=_DETAIL_NEXT_STEPS["run_queue"],
        )

    if latest_relevant_job_status == "running":
        return LibraryStatusView(
            state="Building",
            message="A build is running for the latest dataset.",
            detail_next_step=_DETAIL_NEXT_STEPS["view_job"],
        )

    if latest_relevant_job_status == "failed":
        return LibraryStatusView(
            state="Failed",
            message="The latest build failed.",
            detail_next_step=_DETAIL_NEXT_STEPS["view_job"],
        )

    if latest_relevant_job_status == "done":
        return LibraryStatusView(
            state="Searchable",
            message="The latest dataset is ready for search.",
            detail_next_step=_DETAIL_NEXT_STEPS["search"],
        )

    return LibraryStatusView(
        state="Failed",
        message="Run a build for the latest dataset before searching.",
        detail_next_step=_DETAIL_NEXT_STEPS["run_queue"],
    )
