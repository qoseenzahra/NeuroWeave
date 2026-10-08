from __future__ import annotations

from pathlib import Path

import pytest

from app.access.filesystem import (
    DirectoryGrant, FileProposal, FilesystemAuthorizationError,
    FilesystemAuthorizer, GrantScope,
)


def test_read_and_write_require_explicit_project_grant(tmp_path):
    root = tmp_path / "project"
    child = root / "dataset"
    child.mkdir(parents=True)
    auth = FilesystemAuthorizer([
        DirectoryGrant("u1", "p1", root, GrantScope.READ),
        DirectoryGrant("u1", "p1", root, GrantScope.WRITE),
    ])
    auth.require_read("u1", "p1", child)
    auth.require_write("u1", "p1", child)
    with pytest.raises(FilesystemAuthorizationError):
        auth.require_read("u2", "p1", child)


def test_registration_rejects_parent_child_overlap(tmp_path):
    root = tmp_path / "root"
    child = root / "child"
    with pytest.raises(FilesystemAuthorizationError):
        FilesystemAuthorizer.ensure_no_parent_child_overlap([root], child)


def test_confirmation_rejects_other_user_and_revoked_grant(tmp_path):
    proposal = FileProposal("op1", "u1", "p1", "delete", tmp_path / "x", 3, 7)
    with pytest.raises(FilesystemAuthorizationError):
        FilesystemAuthorizer.require_proposal_initiator(proposal, "u2", "p1", 3, 7)
    with pytest.raises(FilesystemAuthorizationError):
        FilesystemAuthorizer.require_proposal_initiator(proposal, "u1", "p1", 4, 7)
    with pytest.raises(FilesystemAuthorizationError):
        FilesystemAuthorizer.require_proposal_initiator(proposal, "u1", "p1", 3, 8)
