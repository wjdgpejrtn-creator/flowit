from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from toolset.adapters.tools.file.file_read_tool import FileReadTool
from toolset.adapters.tools.file.file_transform_tool import FileTransformTool
from toolset.adapters.tools.file.file_write_tool import FileWriteTool
from toolset.domain.exceptions import ToolExecutionError


# ── FileReadTool ──────────────────────────────────────────────────────────────

class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_text_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")

        result = await FileReadTool().execute({"path": str(f)})

        assert result["content"] == "hello world"
        assert result["size_bytes"] == 11
        assert result["path"] == str(f)

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(ToolExecutionError):
            await FileReadTool().execute({"path": str(tmp_path / "nope.txt")})

    @pytest.mark.asyncio
    async def test_directory_path_raises(self, tmp_path):
        with pytest.raises(ToolExecutionError):
            await FileReadTool().execute({"path": str(tmp_path)})

    @pytest.mark.asyncio
    async def test_binary_mode_returns_hex(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02")

        result = await FileReadTool().execute({"path": str(f), "binary": True})

        assert result["content"] == "000102"


# ── FileWriteTool ─────────────────────────────────────────────────────────────

class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path):
        target = tmp_path / "out.txt"

        result = await FileWriteTool().execute({"path": str(target), "content": "test content"})

        assert result["success"] is True
        assert target.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_append_mode(self, tmp_path):
        target = tmp_path / "log.txt"
        target.write_text("line1\n")

        await FileWriteTool().execute({"path": str(target), "content": "line2\n", "mode": "a"})

        assert target.read_text() == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_directory_path_raises(self, tmp_path):
        with pytest.raises(ToolExecutionError):
            await FileWriteTool().execute({"path": str(tmp_path), "content": "x"})

    @pytest.mark.asyncio
    async def test_create_parents(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.txt"

        result = await FileWriteTool().execute({"path": str(target), "content": "deep", "create_parents": True})

        assert result["success"] is True
        assert target.read_text() == "deep"


# ── FileTransformTool ─────────────────────────────────────────────────────────

class TestFileTransformTool:
    @pytest.mark.asyncio
    async def test_csv_to_json(self, tmp_path):
        src = tmp_path / "data.csv"
        src.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
        dst = tmp_path / "data.json"

        result = await FileTransformTool().execute({
            "source_path": str(src),
            "target_path": str(dst),
            "source_format": "csv",
            "target_format": "json",
        })

        assert result["rows_processed"] == 2
        data = json.loads(dst.read_text())
        assert data[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_json_to_csv(self, tmp_path):
        src = tmp_path / "data.json"
        src.write_text(json.dumps([{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]))
        dst = tmp_path / "data.csv"

        result = await FileTransformTool().execute({
            "source_path": str(src),
            "target_path": str(dst),
            "source_format": "json",
            "target_format": "csv",
        })

        assert result["rows_processed"] == 2
        content = dst.read_text()
        assert "name" in content
        assert "Alice" in content

    @pytest.mark.asyncio
    async def test_source_not_found_raises(self, tmp_path):
        with pytest.raises(ToolExecutionError):
            await FileTransformTool().execute({
                "source_path": str(tmp_path / "missing.csv"),
                "target_path": str(tmp_path / "out.json"),
                "source_format": "csv",
                "target_format": "json",
            })
