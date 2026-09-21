"""Regression coverage for the MCP version embedded by the AEKO backend."""

import inspect

from aeko_mcp.server import mcp


PACKAGE_TOOL_NAMES = {
    "aeko_list_brand_documents",
    "aeko_get_document_package",
    "aeko_read_document_file",
    "aeko_get_active_brand_package",
    "aeko_get_brand_package_version",
    "aeko_read_brand_package_file",
    "aeko_get_brand_wiki_chapters",
    "aeko_list_brand_wiki_pages",
    "aeko_get_brand_wiki_page",
}

STRUCTURED_TOOL_NAMES = {
    "aeko_get_active_brand_package",
    "aeko_get_brand_package_version",
    "aeko_read_brand_package_file",
    "aeko_get_product_description",
    "aeko_update_product_page",
    "aeko_list_store_writes",
}


def test_versioned_package_tools_register_with_runtime_annotations_and_schemas():
    """MCP 1.12.4 must import the complete server and build every new schema.

    FastMCP 1.12.x calls ``issubclass`` on each raw parameter annotation while
    registering a tool. A string annotation therefore crashes the whole AEKO
    API at import time, before any request can be served.
    """
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    assert PACKAGE_TOOL_NAMES <= registered.keys()
    for name in PACKAGE_TOOL_NAMES:
        tool = registered[name]
        assert tool.parameters["type"] == "object"
        assert isinstance(tool.parameters["properties"], dict)
        assert "domain_id" in tool.parameters["properties"]
        for parameter in inspect.signature(tool.fn).parameters.values():
            assert not isinstance(parameter.annotation, str), (
                f"{name}.{parameter.name} has a postponed annotation that "
                "MCP 1.12.x cannot register"
            )


def test_structured_tools_build_semantic_output_schemas_at_runtime():
    """Each migrated tool must publish its model fields, not ``{result: str}``."""
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    assert STRUCTURED_TOOL_NAMES <= registered.keys()
    for name in STRUCTURED_TOOL_NAMES:
        tool = registered[name]
        signature = inspect.signature(tool.fn)
        assert not isinstance(signature.return_annotation, str), name
        for parameter in signature.parameters.values():
            assert not isinstance(parameter.annotation, str), f"{name}.{parameter.name}"
        schema = tool.fn_metadata.output_schema
        assert schema is not None, name
        assert tool.fn_metadata.wrap_output is False, name
        assert set(schema["properties"]) - {"result"}, name
