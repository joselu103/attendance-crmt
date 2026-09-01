"""Safe verification of an already-pulled immutable container image."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Literal, Never

from pydantic import BaseModel, ConfigDict

_IMAGE_REFERENCE_PATTERN = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")
_SOURCE_REVISION_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


class ContainerArtifactVerificationError(Exception):
    """A verifier failure whose CLI representation is deliberately non-diagnostic."""


class ContainerArtifactEvidence(BaseModel):
    """The intentionally minimal immutable-container verification evidence."""

    model_config = ConfigDict(frozen=True)

    image: str
    source_revision: str
    verified: Literal[True] = True


Inspector = Callable[[str], object]


def inspect_pulled_image(image: str) -> object:
    """Return Docker's metadata for an image that is already available locally."""
    try:
        completed = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            check=True,
            text=True,
        )
        return json.loads(completed.stdout)
    except OSError, subprocess.CalledProcessError, TypeError, json.JSONDecodeError:
        raise ContainerArtifactVerificationError from None


def verify_container_artifact(
    image: str,
    source_revision: str,
    *,
    inspector: Inspector = inspect_pulled_image,
) -> ContainerArtifactEvidence:
    """Verify a digest reference and its image metadata without exposing diagnostics."""
    if (
        _IMAGE_REFERENCE_PATTERN.fullmatch(image) is None
        or _SOURCE_REVISION_PATTERN.fullmatch(source_revision) is None
    ):
        raise ContainerArtifactVerificationError
    try:
        metadata = inspector(image)
        if not isinstance(metadata, list) or len(metadata) != 1:
            raise ContainerArtifactVerificationError
        image_metadata = metadata[0]
        if not isinstance(image_metadata, dict):
            raise ContainerArtifactVerificationError
        repo_digests = image_metadata.get("RepoDigests")
        labels = image_metadata.get("Config", {}).get("Labels")
        if (
            not isinstance(repo_digests, list)
            or image not in repo_digests
            or not isinstance(labels, dict)
            or labels.get("org.opencontainers.image.revision") != source_revision
        ):
            raise ContainerArtifactVerificationError
    except ContainerArtifactVerificationError:
        raise
    except Exception:  # noqa: BLE001
        raise ContainerArtifactVerificationError from None
    return ContainerArtifactEvidence(
        image=image,
        source_revision=source_revision,
        verified=True,
    )


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ContainerArtifactVerificationError


def main(
    argv: Sequence[str] | None = None,
    *,
    inspector: Inspector = inspect_pulled_image,
) -> int:
    """Emit immutable-container evidence or one stable non-diagnostic failure."""
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source-revision", required=True)
    try:
        arguments = parser.parse_args(argv)
        evidence = verify_container_artifact(
            arguments.image,
            arguments.source_revision,
            inspector=inspector,
        )
    except Exception:  # noqa: BLE001
        print(json.dumps({"status": "container_artifact_unverified"}), file=sys.stderr)
        return 1
    print(json.dumps(evidence.model_dump(mode="json"), sort_keys=True))
    return 0
