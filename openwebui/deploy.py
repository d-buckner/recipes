#!/usr/bin/env python3
"""
Deploy recipe_tool.py to an Open WebUI instance.

Usage:
    uv run openwebui/deploy.py

Environment variables:
    OPENWEBUI_URL      Base URL of your Open WebUI instance (e.g. http://localhost:3000)
    OPENWEBUI_API_KEY  API key from your Open WebUI profile settings
    OPENWEBUI_TOOL_ID  Tool ID to update (optional — will search by name if omitted)

If no existing tool is found by ID or name, a new tool is created.
"""

import os
import sys
from pathlib import Path

import requests

TOOL_FILE = Path(__file__).parent / "recipe_tool.py"
TOOL_NAME = "Recipe Search"
TOOL_ID = "recipe_search"
TOOL_DESCRIPTION = "Search your personal recipe database and render recipes in markdown."


def api(base_url: str, api_key: str) -> "ApiClient":
    return ApiClient(base_url.rstrip("/"), api_key)


class ApiClient:
    def __init__(self, base_url: str, api_key: str):
        self.base = f"{base_url}/api/v1/tools"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def list_tools(self) -> list[dict]:
        resp = requests.get(f"{self.base}/", headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_tool(self, tool_id: str) -> dict | None:
        resp = requests.get(f"{self.base}/id/{tool_id}", headers=self.headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def create_tool(self, tool_id: str, name: str, content: str, description: str) -> dict:
        payload = {
            "id": tool_id,
            "name": name,
            "content": content,
            "meta": {"description": description, "manifest": {}},
        }
        resp = requests.post(f"{self.base}/create", headers=self.headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def update_tool(self, tool_id: str, name: str, content: str, description: str) -> dict:
        payload = {
            "name": name,
            "content": content,
            "meta": {"description": description, "manifest": {}},
        }
        resp = requests.post(f"{self.base}/id/{tool_id}/update", headers=self.headers, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()


def main() -> None:
    base_url = os.environ.get("OPENWEBUI_URL", "").strip()
    api_key = os.environ.get("OPENWEBUI_API_KEY", "").strip()
    tool_id_override = os.environ.get("OPENWEBUI_TOOL_ID", "").strip()

    if not base_url:
        sys.exit("Error: OPENWEBUI_URL environment variable is required.")
    if not api_key:
        sys.exit("Error: OPENWEBUI_API_KEY environment variable is required.")

    content = TOOL_FILE.read_text()
    client = api(base_url, api_key)

    # Resolve the tool ID to use
    target_id = tool_id_override or TOOL_ID
    existing = client.get_tool(target_id)

    # If not found by ID, fall back to searching by name
    if existing is None and not tool_id_override:
        tools = client.list_tools()
        match = next((t for t in tools if t.get("name") == TOOL_NAME), None)
        if match:
            target_id = match["id"]
            existing = match

    if existing:
        print(f"Updating existing tool '{existing.get('name')}' (id: {target_id}) ...")
        result = client.update_tool(target_id, TOOL_NAME, content, TOOL_DESCRIPTION)
        print(f"Updated: {result.get('name')} (id: {result.get('id')})")
    else:
        print(f"No existing tool found — creating '{TOOL_NAME}' (id: {target_id}) ...")
        result = client.create_tool(target_id, TOOL_NAME, content, TOOL_DESCRIPTION)
        print(f"Created: {result.get('name')} (id: {result.get('id')})")


if __name__ == "__main__":
    main()
