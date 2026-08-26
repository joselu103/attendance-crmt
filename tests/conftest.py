"""Shared test configuration."""

import os

os.environ.setdefault("ATTENDANCE_DATABASE_URL", "sqlite://")
os.environ.setdefault("ATTENDANCE_MCP_BASE_URL", "http://localhost:8000")
os.environ.setdefault(
    "ATTENDANCE_ENTRA_TENANT_ID", "11111111-1111-1111-1111-111111111111"
)
os.environ.setdefault(
    "ATTENDANCE_ENTRA_ISSUER",
    "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0",
)
os.environ.setdefault(
    "ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL",
    "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/"
    "v2.0/.well-known/openid-configuration",
)
os.environ.setdefault("ATTENDANCE_ENTRA_AUDIENCE", "api://attendance-crmt-test")
os.environ.setdefault(
    "ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS",
    '["22222222-2222-2222-2222-222222222222"]',
)
