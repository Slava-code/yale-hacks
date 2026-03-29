import json
from pathlib import Path

import pytest

from backend.graph import load_graph

ROOT = Path(__file__).resolve().parent.parent
STUB_GRAPH_PATH = ROOT / "data" / "stub" / "graph.json"
PATIENTS_DIR = ROOT / "data" / "patients"

DEMO_PROFILE_IDS = ["patient_001", "patient_006"]


@pytest.fixture
def stub_graph():
    """Load the stub knowledge graph."""
    return load_graph(str(STUB_GRAPH_PATH))


@pytest.fixture
def patient_profiles_dir():
    """Path to the patient profiles directory."""
    return PATIENTS_DIR


@pytest.fixture
def demo_profiles(patient_profiles_dir):
    """Load all demo patient profile JSON files."""
    profiles = []
    for pid in DEMO_PROFILE_IDS:
        path = patient_profiles_dir / f"{pid}.json"
        with open(path) as f:
            profiles.append(json.load(f))
    return profiles


@pytest.fixture
def all_profiles(patient_profiles_dir):
    """Load all patient profile JSON files."""
    profiles = []
    for path in sorted(patient_profiles_dir.glob("patient_*.json")):
        with open(path) as f:
            profiles.append(json.load(f))
    return profiles


@pytest.fixture
def built_graph(demo_profiles):
    """Build a graph from demo profiles using the graph builder."""
    from scripts.build_graph import build_graph
    return build_graph(demo_profiles)
