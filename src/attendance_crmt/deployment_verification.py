"""Safe, transport-independent evidence for non-production MCP acceptance checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from attendance_crmt.attendance.contracts import MyAttendanceEventQuery
from attendance_crmt.audit import AuditEvent
from attendance_crmt.http_contract import (
    ATTENDANCE_MCP_CONTRACT_VERSION,
    CONTRACT_VERSION_HEADER,
    CORRELATION_ID_HEADER,
    MCP_PATH,
)

_REQUIRED_TOOL = "list_my_attendance_events"
_TOKEN_ENVIRONMENT_VARIABLE = "ATTENDANCE_MCP_VERIFICATION_TOKEN"
_SEMVER_PATTERN = re.compile(r"^(?P<major>0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")


class DeploymentVerificationError(Exception):
    """A safe verifier failure suitable for stable CLI classification."""


class EndpointValidationError(DeploymentVerificationError):
    """The supplied endpoint is outside the safe verifier boundary."""


class ContractVersionError(DeploymentVerificationError):
    """The endpoint omitted or changed the required MCP contract major version."""


class PublicBoundaryEvidence(BaseModel):
    """Non-sensitive confirmation of the unauthenticated MCP boundary."""

    model_config = ConfigDict(frozen=True)

    endpoint: str
    contract_version: str
    authentication_status: str


class AuthenticatedBoundaryEvidence(BaseModel):
    """Non-sensitive confirmation of one requester-scoped MCP tool call."""

    model_config = ConfigDict(frozen=True)

    endpoint: str
    contract_version: str
    tool_name: str
    correlation_id: UUID


class AuditEvidence(BaseModel):
    """Non-sensitive correlation result from the local audit database."""

    model_config = ConfigDict(frozen=True)

    found: bool
    tool_name: str
    outcome: str | None
    error_code: str | None


def validate_endpoint(endpoint: str, *, allow_loopback_http: bool = False) -> str:
    """Accept only an exact MCP path over HTTPS or explicitly enabled loopback HTTP."""
    parsed = urlparse(endpoint)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.path != MCP_PATH
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise EndpointValidationError
    if parsed.scheme == "http" and not (
        allow_loopback_http
        and parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    ):
        raise EndpointValidationError
    return endpoint


def build_query(start_date: str, end_date: str) -> MyAttendanceEventQuery:
    """Apply the server's requester-scoped inclusive date bounds and pagination."""
    return MyAttendanceEventQuery.model_validate(
        {"start_date": start_date, "end_date": end_date, "limit": 50, "offset": 0}
    )


def _compatible_contract_version(response: httpx.Response) -> str:
    version = response.headers.get(CONTRACT_VERSION_HEADER)
    expected_match = _SEMVER_PATTERN.fullmatch(ATTENDANCE_MCP_CONTRACT_VERSION)
    actual_match = _SEMVER_PATTERN.fullmatch(version or "")
    if (
        expected_match is None
        or actual_match is None
        or actual_match["major"] != expected_match["major"]
    ):
        raise ContractVersionError
    return version


async def verify_public_boundary(
    endpoint: str,
    *,
    allow_loopback_http: bool = False,
    client: httpx.AsyncClient | None = None,
) -> PublicBoundaryEvidence:
    """Check the public endpoint returns the expected unauthenticated boundary."""
    endpoint = validate_endpoint(endpoint, allow_loopback_http=allow_loopback_http)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient()
    try:
        response = await client.post(endpoint, json={})
        if response.status_code != 401:
            raise DeploymentVerificationError
        contract_version = _compatible_contract_version(response)
        try:
            response_json = response.json()
        except json.JSONDecodeError, UnicodeDecodeError:
            raise DeploymentVerificationError from None
        if (
            not isinstance(response_json, dict)
            or response_json.get("code") != "AUTHENTICATION_REQUIRED"
        ):
            raise DeploymentVerificationError
        return PublicBoundaryEvidence(
            endpoint=endpoint,
            contract_version=contract_version,
            authentication_status="authentication_required",
        )
    except (
        httpx.HTTPError,
        ContractVersionError,
        DeploymentVerificationError,
    ):
        raise
    except Exception:  # noqa: BLE001
        raise DeploymentVerificationError from None
    finally:
        if owns_client:
            await client.aclose()


async def verify_authenticated_boundary(
    endpoint: str,
    *,
    token: str,
    query: MyAttendanceEventQuery,
    allow_loopback_http: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AuthenticatedBoundaryEvidence:
    """Use the official MCP client without retaining response contents or token data."""
    endpoint = validate_endpoint(endpoint, allow_loopback_http=allow_loopback_http)
    correlation_id = uuid4()

    contract_version: str | None = None

    async def check_contract_version(response: httpx.Response) -> None:
        nonlocal contract_version
        contract_version = _compatible_contract_version(response)

    async with httpx.AsyncClient(
        transport=transport,
        headers={
            "Authorization": f"Bearer {token}",
            CORRELATION_ID_HEADER: str(correlation_id),
        },
        event_hooks={"response": [check_contract_version]},
    ) as client:
        try:
            async with streamable_http_client(  # noqa: SIM117
                endpoint, http_client=client
            ) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    if _REQUIRED_TOOL not in {tool.name for tool in tools.tools}:
                        raise DeploymentVerificationError
                    result = await session.call_tool(
                        _REQUIRED_TOOL,
                        {
                            "start_date": query.start_date.isoformat(),
                            "end_date": query.end_date.isoformat(),
                            "limit": query.limit,
                            "offset": query.offset,
                        },
                    )
                    if result.isError:
                        raise DeploymentVerificationError
        except (
            httpx.HTTPError,
            ContractVersionError,
            DeploymentVerificationError,
        ):
            raise
        except Exception:  # noqa: BLE001
            raise DeploymentVerificationError from None
    return AuthenticatedBoundaryEvidence(
        endpoint=endpoint,
        contract_version=contract_version or ATTENDANCE_MCP_CONTRACT_VERSION,
        tool_name=_REQUIRED_TOOL,
        correlation_id=correlation_id,
    )


def verify_audit_event(
    *, audit_database_path: Path, correlation_id: UUID
) -> AuditEvidence:
    """Look up only safe outcome fields for the required requester-scoped tool."""
    if not audit_database_path.is_file():
        raise DeploymentVerificationError
    database_path = audit_database_path.resolve()
    engine = create_engine(
        URL.create(
            "sqlite+pysqlite",
            database=f"file:{database_path}",
            query={"mode": "ro", "uri": "true"},
        )
    )
    try:
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        with session_factory() as session:
            result = session.execute(
                select(AuditEvent.outcome, AuditEvent.error_code)
                .where(AuditEvent.correlation_id == str(correlation_id))
                .where(AuditEvent.tool_name == _REQUIRED_TOOL)
                .order_by(AuditEvent.event_id.desc())
            ).first()
    except Exception:  # noqa: BLE001
        raise DeploymentVerificationError from None
    finally:
        engine.dispose()
    if result is None:
        return AuditEvidence(
            found=False, tool_name=_REQUIRED_TOOL, outcome=None, error_code=None
        )
    return AuditEvidence(
        found=True,
        tool_name=_REQUIRED_TOOL,
        outcome=result.outcome,
        error_code=result.error_code,
    )


def _write_safe_json(stream: Any, payload: dict[str, Any]) -> None:
    print(json.dumps(payload, sort_keys=True, default=str), file=stream)


def main(argv: Sequence[str] | None = None) -> int:
    """Run public then authenticated deployment checks with environment-only token input."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--allow-loopback-http", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        public_evidence = asyncio.run(
            verify_public_boundary(
                arguments.endpoint,
                allow_loopback_http=arguments.allow_loopback_http,
            )
        )
    except Exception:  # noqa: BLE001
        _write_safe_json(sys.stderr, {"status": "verification_failed"})
        return 1
    token = os.environ.get(_TOKEN_ENVIRONMENT_VARIABLE)
    if not token:
        _write_safe_json(
            sys.stderr,
            {
                "public": public_evidence.model_dump(mode="json"),
                "authenticated_stage": "blocked",
            },
        )
        return 2
    try:
        query = build_query(arguments.start_date, arguments.end_date)
        authenticated_evidence = asyncio.run(
            verify_authenticated_boundary(
                arguments.endpoint,
                token=token,
                query=query,
                allow_loopback_http=arguments.allow_loopback_http,
            )
        )
    except Exception:  # noqa: BLE001
        _write_safe_json(
            sys.stderr,
            {
                "public": public_evidence.model_dump(mode="json"),
                "authenticated_stage": "failed",
            },
        )
        return 3
    _write_safe_json(
        sys.stdout,
        {
            "public": public_evidence.model_dump(mode="json"),
            "authenticated": authenticated_evidence.model_dump(mode="json"),
        },
    )
    return 0


def audit_main(argv: Sequence[str] | None = None) -> int:
    """Emit one safe local audit correlation result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-database-path", required=True)
    parser.add_argument("--correlation-id", required=True, type=UUID)
    arguments = parser.parse_args(argv)
    try:
        evidence = verify_audit_event(
            audit_database_path=Path(arguments.audit_database_path),
            correlation_id=arguments.correlation_id,
        )
    except Exception:  # noqa: BLE001
        _write_safe_json(sys.stderr, {"status": "audit_unavailable"})
        return 1
    _write_safe_json(sys.stdout, evidence.model_dump(mode="json"))
    return 0 if evidence.found else 2
