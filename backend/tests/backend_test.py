from agents.mcp_tools import safe_project_path
from config import valid_fernet_key


def test_safe_project_path_accepts_relative_files():
    assert safe_project_path("src/app.js") == "src/app.js"


def test_safe_project_path_rejects_traversal():
    try:
        safe_project_path("../secret.txt")
    except ValueError as exc:
        assert "traversal" in str(exc)
    else:
        raise AssertionError("path traversal was accepted")


def test_fernet_key_validation():
    assert valid_fernet_key("YW1hcmt0YWktZGV2LWZlcm5ldC1rZXktMzItYnl0ZSE=")
