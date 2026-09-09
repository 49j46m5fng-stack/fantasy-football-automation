import json

from fastapi.testclient import TestClient

from api.index import app


client = TestClient(
    app
)


def test_health() -> None:
    response = client.get(
        "/api/health"
    )

    assert (
        response.status_code
        == 200
    )

    assert (
        response.json()[
            "status"
        ]
        == "ok"
    )


def test_context_requires_auth(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "TIMBOT_API_KEY",
        "secret",
    )

    response = client.get(
        "/api/context/2026/1/baseline"
    )

    assert (
        response.status_code
        == 401
    )


def test_context_reads_generated_file(
    monkeypatch,
    tmp_path,
) -> None:
    import api.index as api_module

    monkeypatch.setenv(
        "TIMBOT_API_KEY",
        "secret",
    )

    data_root = (
        tmp_path
        / "data"
    )

    target = (
        data_root
        / "2026"
        / "agent_context"
        / "week_01_baseline.json"
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_text(
        json.dumps(
            {
                "hello": "TimBot"
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        api_module,
        "DATA_ROOT",
        data_root,
    )

    response = client.get(
        "/api/context/2026/1/baseline",
        headers={
            "Authorization": (
                "Bearer secret"
            ),
        },
    )

    assert (
        response.status_code
        == 200
    )

    assert (
        response.json()[
            "context"
        ][
            "hello"
        ]
        == "TimBot"
    )