"""Read-only API for TimBot Custom GPT Actions."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException


app = FastAPI(
    title="TimBot Fantasy Football API",
    version="1.0.0",
    description=(
        "Read-only access to generated GOATs/DOATs "
        "fantasy-football agent context."
    ),
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_ROOT = (
    PROJECT_ROOT
    / "data"
)


VALID_STAGES = {
    "baseline",
    "sunday",
    "final",
}


def require_api_key(
    authorization: str | None = Header(
        default=None
    ),
) -> None:
    """Require the configured bearer token."""

    expected_key = os.environ.get(
        "TIMBOT_API_KEY"
    )

    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Server API key is not configured."
            ),
        )

    expected_header = (
        f"Bearer {expected_key}"
    )

    if authorization != expected_header:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )


def _candidate_context_paths(
    season: str,
    week: int,
    stage: str,
) -> list[Path]:
    """Return supported agent-context filename candidates."""

    week_2 = (
        f"week_{week:02d}"
    )

    week_plain = (
        f"week_{week}"
    )

    return [
        DATA_ROOT
        / season
        / "agent_context"
        / f"{week_2}_{stage}.json",

        DATA_ROOT
        / season
        / "agent_context"
        / f"{week_plain}_{stage}.json",

        DATA_ROOT
        / season
        / f"{week_2}_{stage}_context.json",

        DATA_ROOT
        / season
        / f"{week_plain}_{stage}_context.json",
    ]


def _display_source_path(
    path: Path,
) -> str:
    """Return a safe display path for an agent-context file.

    Production files normally live under PROJECT_ROOT.

    Tests may deliberately replace DATA_ROOT with a temporary directory,
    so the fallback uses DATA_ROOT rather than assuming every path is
    physically inside the repository.
    """

    try:
        return str(
            path.relative_to(
                PROJECT_ROOT
            )
        )

    except ValueError:
        try:
            relative_data_path = (
                path.relative_to(
                    DATA_ROOT
                )
            )

        except ValueError:
            return path.name

        return str(
            Path("data")
            / relative_data_path
        )


def _load_context(
    season: str,
    week: int,
    stage: str,
) -> tuple[
    Path,
    dict[str, Any],
]:
    """Load one generated agent-context JSON file."""

    if stage not in VALID_STAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                "stage must be one of: "
                "baseline, sunday, final"
            ),
        )

    if (
        not season.isdigit()
        or len(
            season
        )
        != 4
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "season must be a "
                "four-digit year"
            ),
        )

    if (
        week < 1
        or week > 18
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "week must be between 1 and 18"
            ),
        )

    for path in (
        _candidate_context_paths(
            season,
            week,
            stage,
        )
    ):
        if not path.exists():
            continue

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                payload = json.load(
                    file
                )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Context file could not "
                    "be read."
                ),
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise HTTPException(
                status_code=500,
                detail=(
                    "Context file must "
                    "contain a JSON object."
                ),
            )

        return (
            path,
            payload,
        )

    raise HTTPException(
        status_code=404,
        detail=(
            f"No {stage} context found "
            f"for {season} Week {week}."
        ),
    )


@app.get(
    "/api/health",
    operation_id="healthCheck",
    summary="Check API status",
)
def health() -> dict[str, str]:
    """Unauthenticated health check."""

    return {
        "status": "ok",
        "service": (
            "timbot-fantasy-api"
        ),
    }


@app.get(
    "/api/context/{season}/{week}/{stage}",
    operation_id="getFantasyContext",
    summary=(
        "Get TimBot fantasy context "
        "for one season, week, and stage"
    ),
    dependencies=[
        Depends(
            require_api_key
        )
    ],
)
def get_context(
    season: str,
    week: int,
    stage: str,
) -> dict[str, Any]:
    """Return generated fantasy context."""

    (
        path,
        payload,
    ) = _load_context(
        season,
        week,
        stage,
    )

    return {
        "season": season,
        "week": week,
        "stage": stage,
        "source_file": (
            _display_source_path(
                path
            )
        ),
        "context": payload,
    }