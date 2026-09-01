import json
import subprocess

import pytest
from pydantic import ValidationError

from attendance_crmt.container_artifact_verification import (
    ContainerArtifactEvidence,
    ContainerArtifactVerificationError,
    inspect_pulled_image,
    main,
    verify_container_artifact,
)

IMAGE = "registry.example/attendance-crmt@sha256:" + "a" * 64
OTHER_IMAGE = "registry.example/attendance-crmt@sha256:" + "c" * 64
REVISION = "b" * 40
OTHER_REVISION = "d" * 40


def _matching_metadata() -> list[object]:
    return [
        {
            "RepoDigests": [IMAGE],
            "Config": {"Labels": {"org.opencontainers.image.revision": REVISION}},
        }
    ]


def test_default_inspector_hides_docker_command_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise subprocess.CalledProcessError(1, ["docker", "image", "inspect"])

    monkeypatch.setattr(
        "attendance_crmt.container_artifact_verification.subprocess.run", fail
    )

    with pytest.raises(ContainerArtifactVerificationError):
        inspect_pulled_image(IMAGE)


def test_verifier_returns_only_immutable_evidence_for_matching_image() -> None:
    def inspector(image: str) -> object:
        assert image == IMAGE
        return _matching_metadata()

    evidence = verify_container_artifact(IMAGE, REVISION, inspector=inspector)

    assert evidence.model_dump() == {
        "image": IMAGE,
        "source_revision": REVISION,
        "verified": True,
    }
    assert json.loads(evidence.model_dump_json()) == evidence.model_dump()
    with pytest.raises(ValidationError):
        evidence.verified = False
    with pytest.raises(ValidationError):
        ContainerArtifactEvidence.model_validate(
            {"image": IMAGE, "source_revision": REVISION, "verified": False}
        )


def test_verifier_rejects_tag_only_image_reference() -> None:
    with pytest.raises(ContainerArtifactVerificationError):
        verify_container_artifact(
            "registry.example/attendance-crmt:latest",
            REVISION,
            inspector=lambda _image: _matching_metadata(),
        )


def test_verifier_rejects_requested_digest_missing_from_repo_digests() -> None:
    with pytest.raises(ContainerArtifactVerificationError):
        verify_container_artifact(
            IMAGE,
            REVISION,
            inspector=lambda _image: [
                {
                    "RepoDigests": [OTHER_IMAGE],
                    "Config": {
                        "Labels": {"org.opencontainers.image.revision": REVISION}
                    },
                }
            ],
        )


def test_verifier_rejects_revision_label_mismatch() -> None:
    with pytest.raises(ContainerArtifactVerificationError):
        verify_container_artifact(
            IMAGE,
            REVISION,
            inspector=lambda _image: [
                {
                    "RepoDigests": [IMAGE],
                    "Config": {
                        "Labels": {"org.opencontainers.image.revision": OTHER_REVISION}
                    },
                }
            ],
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        [],
        [{"RepoDigests": IMAGE, "Config": {"Labels": {}}}],
        [{"RepoDigests": [IMAGE], "Config": "not-an-object"}],
        [{"RepoDigests": [IMAGE], "Config": {"Labels": []}}],
    ],
)
def test_verifier_rejects_malformed_inspection_metadata(metadata: object) -> None:
    with pytest.raises(ContainerArtifactVerificationError):
        verify_container_artifact(IMAGE, REVISION, inspector=lambda _image: metadata)


def test_cli_emits_evidence_on_success_and_safe_stderr_on_every_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            ["--image", IMAGE, "--source-revision", REVISION],
            inspector=lambda _image: _matching_metadata(),
        )
        == 0
    )
    successful = capsys.readouterr()
    assert json.loads(successful.out) == {
        "image": IMAGE,
        "source_revision": REVISION,
        "verified": True,
    }
    assert successful.err == ""

    def failing_inspector(_image: str) -> object:
        raise RuntimeError("sensitive Docker daemon diagnostic")

    assert (
        main(
            ["--image", IMAGE, "--source-revision", REVISION],
            inspector=failing_inspector,
        )
        == 1
    )
    failed = capsys.readouterr()
    assert failed.out == ""
    assert json.loads(failed.err) == {"status": "container_artifact_unverified"}
    assert "sensitive Docker daemon diagnostic" not in failed.err

    assert (
        main(
            [
                "--image",
                "registry.example/attendance-crmt:latest",
                "--source-revision",
                REVISION,
            ],
            inspector=lambda _image: _matching_metadata(),
        )
        == 1
    )
    invalid = capsys.readouterr()
    assert invalid.out == ""
    assert json.loads(invalid.err) == {"status": "container_artifact_unverified"}
