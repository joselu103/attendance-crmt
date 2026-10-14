"""Shared test configuration."""

import os

os.environ["ENVIRONMENT"] = "development"
os.environ["ATTENDANCE_DATABASE_URL"] = "sqlite://"
os.environ["ATTENDANCE_AUDIT_DATABASE_PATH"] = (
    "/tmp/attendance-crmt-tests/audit.sqlite3"
)
os.environ["ATTENDANCE_ENTRA_TENANT_ID"] = "11111111-1111-1111-1111-111111111111"
os.environ["ATTENDANCE_ENTRA_AUDIENCE"] = "api://attendance-crmt-test"
os.environ["ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS"] = (
    '["22222222-2222-2222-2222-222222222222"]'
)
