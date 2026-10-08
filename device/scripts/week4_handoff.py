"""Device entry point for the shared immutable Week 4 authentication policy."""
from pathlib import Path
import subprocess  # Keep the existing fixture patch target for fixed Git reads.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from week4_handoff_auth import (  # Re-export the established device API.
    WEEK4_MANIFEST, R4_MANIFEST, ALL_SPLIT_MANIFEST, PACKAGE, R3, R4,
    SOURCE_COMMITS, SOURCE_ANCHORS, PR22_SOURCE_COMMIT, PR22_MERGE_COMMIT,
    PR22_R4_SOURCE_HASHES, ACCEPTED_R3_REPORT_SHA256, ACCEPTED_R3_REPORT_LF_SHA256,
    ACCEPTED_R3_REPORT_HASHES, sha256, authenticated_json, bound_path, check_file,
    source_hash, check_sources, check_payload_parity, authenticate_handoff,
    accepted_r3_provenance,
)
