from __future__ import annotations

from uuid import uuid4

import pytest
from common_schemas import NodeContext

from nodes_graph.domain.catalog.data.base64_decode import Base64DecodeInput, Base64DecodeNode
from nodes_graph.domain.catalog.data.base64_encode import Base64EncodeInput, Base64EncodeNode
from nodes_graph.domain.catalog.data.csv_build import CsvBuildInput, CsvBuildNode
from nodes_graph.domain.catalog.data.csv_parse import CsvParseInput, CsvParseNode
from nodes_graph.domain.catalog.data.date_format import DateFormatInput, DateFormatNode
from nodes_graph.domain.catalog.data.json_extract import JsonExtractInput, JsonExtractNode
from nodes_graph.domain.catalog.data.json_merge import JsonMergeInput, JsonMergeNode
from nodes_graph.domain.catalog.data.list_filter import ListFilterInput, ListFilterNode
from nodes_graph.domain.catalog.data.list_map import ListMapInput, ListMapNode
from nodes_graph.domain.catalog.data.number_calc import NumberCalcInput, NumberCalcNode
from nodes_graph.domain.catalog.data.regex_extract import RegexExtractInput, RegexExtractNode
from nodes_graph.domain.catalog.data.regex_replace import RegexReplaceInput, RegexReplaceNode
from nodes_graph.domain.catalog.data.string_template import StringTemplateInput, StringTemplateNode
from nodes_graph.domain.catalog.data.text_transform import TextTransformInput, TextTransformNode

NODE_CTX = NodeContext(execution_id=uuid4(), user_id=uuid4())


@pytest.mark.asyncio
async def test_text_transform_upper():
    node = TextTransformNode()
    out = await node.process(TextTransformInput(text="hello", operation="upper"), NODE_CTX)
    assert out.result == "HELLO"


@pytest.mark.asyncio
async def test_text_transform_lower():
    node = TextTransformNode()
    out = await node.process(TextTransformInput(text="WORLD", operation="lower"), NODE_CTX)
    assert out.result == "world"


@pytest.mark.asyncio
async def test_text_transform_reverse():
    node = TextTransformNode()
    out = await node.process(TextTransformInput(text="abc", operation="reverse"), NODE_CTX)
    assert out.result == "cba"


@pytest.mark.asyncio
async def test_json_extract_found():
    node = JsonExtractNode()
    out = await node.process(JsonExtractInput(data={"user": {"name": "아름"}}, path="user.name"), NODE_CTX)
    assert out.value == "아름"
    assert out.found is True


@pytest.mark.asyncio
async def test_json_extract_not_found():
    node = JsonExtractNode()
    out = await node.process(JsonExtractInput(data={"user": {}}, path="user.age"), NODE_CTX)
    assert out.found is False


@pytest.mark.asyncio
async def test_json_extract_list_index():
    node = JsonExtractNode()
    out = await node.process(JsonExtractInput(data={"items": ["a", "b", "c"]}, path="items.1"), NODE_CTX)
    assert out.value == "b"


@pytest.mark.asyncio
async def test_json_merge_shallow():
    node = JsonMergeNode()
    out = await node.process(JsonMergeInput(base={"a": 1, "b": 2}, overlay={"b": 99, "c": 3}), NODE_CTX)
    assert out.result == {"a": 1, "b": 99, "c": 3}


@pytest.mark.asyncio
async def test_json_merge_deep():
    node = JsonMergeNode()
    out = await node.process(JsonMergeInput(
        base={"x": {"a": 1, "b": 2}},
        overlay={"x": {"b": 99}},
        deep=True,
    ), NODE_CTX)
    assert out.result == {"x": {"a": 1, "b": 99}}


@pytest.mark.asyncio
async def test_csv_parse():
    node = CsvParseNode()
    out = await node.process(CsvParseInput(csv_string="name,age\n아름,30\n지현,25"), NODE_CTX)
    assert out.row_count == 2
    assert out.rows[0]["name"] == "아름"
    assert out.headers == ["name", "age"]


@pytest.mark.asyncio
async def test_csv_build():
    node = CsvBuildNode()
    out = await node.process(
        CsvBuildInput(rows=[{"name": "아름", "age": "30"}, {"name": "지현", "age": "25"}]), NODE_CTX
    )
    assert out.row_count == 2
    assert "아름" in out.csv_string
    assert "name,age" in out.csv_string


@pytest.mark.asyncio
async def test_number_calc_add():
    node = NumberCalcNode()
    out = await node.process(NumberCalcInput(operation="add", operands=[1.0, 2.0, 3.0]), NODE_CTX)
    assert out.result == 6.0


@pytest.mark.asyncio
async def test_number_calc_div():
    node = NumberCalcNode()
    out = await node.process(NumberCalcInput(operation="div", operands=[10.0, 4.0]), NODE_CTX)
    assert out.result == 2.5


@pytest.mark.asyncio
async def test_number_calc_sqrt():
    node = NumberCalcNode()
    out = await node.process(NumberCalcInput(operation="sqrt", operands=[9.0]), NODE_CTX)
    assert out.result == 3.0


@pytest.mark.asyncio
async def test_date_format():
    node = DateFormatNode()
    out = await node.process(DateFormatInput(
        date_str="2026-05-08 09:00:00",
        output_format="%Y/%m/%d",
    ), NODE_CTX)
    assert out.result == "2026/05/08"


@pytest.mark.asyncio
async def test_date_format_add_days():
    node = DateFormatNode()
    out = await node.process(DateFormatInput(
        date_str="2026-05-08 00:00:00",
        output_format="%Y-%m-%d",
        add_days=3,
    ), NODE_CTX)
    assert out.result == "2026-05-11"


@pytest.mark.asyncio
async def test_list_filter_sort():
    node = ListFilterNode()
    out = await node.process(ListFilterInput(items=[3, 1, 2], operation="sort"), NODE_CTX)
    assert out.result == [1, 2, 3]


@pytest.mark.asyncio
async def test_list_filter_deduplicate():
    node = ListFilterNode()
    out = await node.process(ListFilterInput(items=[1, 2, 2, 3, 1], operation="deduplicate"), NODE_CTX)
    assert out.result == [1, 2, 3]


@pytest.mark.asyncio
async def test_list_filter_take():
    node = ListFilterNode()
    out = await node.process(ListFilterInput(items=[1, 2, 3, 4, 5], operation="take", n=3), NODE_CTX)
    assert out.result == [1, 2, 3]


@pytest.mark.asyncio
async def test_list_map_extract_field():
    node = ListMapNode()
    out = await node.process(ListMapInput(
        items=[{"name": "아름"}, {"name": "지현"}],
        operation="extract_field",
        field="name",
    ), NODE_CTX)
    assert out.result == ["아름", "지현"]


@pytest.mark.asyncio
async def test_list_map_to_str():
    node = ListMapNode()
    out = await node.process(ListMapInput(items=[1, 2, 3], operation="to_str"), NODE_CTX)
    assert out.result == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_string_template():
    node = StringTemplateNode()
    out = await node.process(StringTemplateInput(
        template="안녕하세요, ${name}님!",
        variables={"name": "아름"},
    ), NODE_CTX)
    assert out.result == "안녕하세요, 아름님!"


@pytest.mark.asyncio
async def test_regex_extract():
    node = RegexExtractNode()
    out = await node.process(RegexExtractInput(text="연락처: 010-1234-5678", pattern=r"\d{3}-\d{4}-\d{4}"), NODE_CTX)
    assert out.count == 1
    assert out.first_match == "010-1234-5678"


@pytest.mark.asyncio
async def test_regex_replace():
    node = RegexReplaceNode()
    out = await node.process(RegexReplaceInput(text="hello world", pattern=r"o", replacement="0"), NODE_CTX)
    assert out.result == "hell0 w0rld"
    assert out.replacements_made == 2


@pytest.mark.asyncio
async def test_base64_encode_decode_roundtrip():
    encode_node = Base64EncodeNode()
    decode_node = Base64DecodeNode()
    original = "안녕하세요 Workflow!"
    encoded = await encode_node.process(Base64EncodeInput(data=original), NODE_CTX)
    decoded = await decode_node.process(Base64DecodeInput(data=encoded.result), NODE_CTX)
    assert decoded.result == original
