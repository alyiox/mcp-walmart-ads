from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_walmart_ads import discovery, specs
from mcp_walmart_ads.discovery import MANAGED_HEADERS, Operation
from mcp_walmart_ads.platforms import UnknownPlatform
from mcp_walmart_ads.specs import SpecError

# ── indexing ──────────────────────────────────────────────────────────────────


def test_every_surface_api_indexes_at_least_one_operation():
    rows = {r["api"]: r["operations"] for r in discovery.list_apis()}
    assert set(rows) == set(specs.API_IDS)
    assert all(count > 0 for count in rows.values())


def test_api_rows_carry_platform_and_environments():
    rows = {r["api"]: r for r in discovery.list_apis()}
    assert rows["connect:search"]["platform"] == "connect"
    assert rows["connect:search"]["environments"] == "from config"
    assert rows["marketplace:simulations-api"]["environments"] == ["sandbox"]


def test_auxiliary_specs_are_absent_from_the_api_namespace():
    assert "connect:ad-id-token-generation" not in {r["api"] for r in discovery.list_apis()}


def test_operations_without_a_declared_id_fall_back_to_method_and_path():
    ids = [r["operation_id"] for r in discovery.list_endpoints()]
    assert any(" /" in i for i in ids)


# ── filtering ─────────────────────────────────────────────────────────────────


def test_endpoints_are_listed_across_every_platform():
    all_rows = discovery.list_endpoints()
    per_platform = sum(
        len(discovery.list_endpoints(platform=p)) for p in ("connect", "samsclub", "marketplace")
    )
    assert len(all_rows) == per_platform


def test_api_filter_narrows_to_one_spec():
    rows = discovery.list_endpoints(api="samsclub:sponsored")
    assert rows
    assert {r["api"] for r in rows} == {"samsclub:sponsored"}


def test_query_matches_id_path_or_summary_case_insensitively():
    assert discovery.list_endpoints(query="ORDERS") == discovery.list_endpoints(query="orders")
    assert discovery.list_endpoints(query="orders")


def test_method_filter_is_applied():
    rows = discovery.list_endpoints(api="marketplace:order-management", method="post")
    assert rows
    assert {r["method"] for r in rows} == {"POST"}


def test_tag_filter_is_applied():
    tagged = [r for r in discovery.list_endpoints(api="connect:search") if r["tags"]]
    tag = tagged[0]["tags"][0]
    assert all(tag in r["tags"] for r in discovery.list_endpoints(api="connect:search", tag=tag))


def test_filters_compose():
    rows = discovery.list_endpoints(platform="marketplace", method="get", query="order")
    assert rows
    assert all(r["method"] == "GET" for r in rows)
    assert all(r["api"].startswith("marketplace:") for r in rows)


def test_results_are_sorted_by_api_then_path_then_method():
    rows = discovery.list_endpoints(platform="connect")
    keys = [(r["api"], r["path"], r["method"]) for r in rows]
    assert keys == sorted(keys)


def test_unknown_api_and_unknown_platform_filters_raise():
    with pytest.raises(SpecError):
        discovery.list_endpoints(api="marketplace:nope")
    with pytest.raises(UnknownPlatform):
        discovery.list_endpoints(platform="target")


# ── addressing ────────────────────────────────────────────────────────────────


def test_an_operation_resolves_by_api_plus_bare_id():
    op = discovery.get_operation("getAllOrders", api="marketplace:order-management")
    assert (op.api, op.method, op.path) == ("marketplace:order-management", "get", "/v3/orders")


def test_an_operation_resolves_by_qualified_id():
    op = discovery.get_operation("marketplace:order-management:getAllOrders")
    assert op.qualified_id == "marketplace:order-management:getAllOrders"


def test_a_qualified_id_is_accepted_even_when_api_is_also_given():
    op = discovery.get_operation(
        "marketplace:order-management:getAllOrders", api="marketplace:order-management"
    )
    assert op.operation_id == "getAllOrders"


def test_a_unique_bare_id_resolves_on_its_own():
    assert discovery.get_operation("getAllOrders").api == "marketplace:order-management"


def test_a_colliding_bare_id_is_rejected_naming_the_candidates():
    with pytest.raises(SpecError) as excinfo:
        discovery.get_operation("getAnItem")
    message = str(excinfo.value)
    assert "ambiguous" in message
    assert message.count("marketplace:") > 1


def test_a_bare_id_colliding_across_platforms_is_rejected():
    # Sam's Club mirrors Walmart Connect's operation ids, so consolidating the
    # two into one namespace makes these ambiguous where they were not before.
    with pytest.raises(SpecError) as excinfo:
        discovery.get_operation("AdGroupList")
    message = str(excinfo.value)
    assert "connect:search:AdGroupList" in message
    assert "samsclub:sponsored:AdGroupList" in message


def test_qualifying_a_cross_platform_collision_resolves_it():
    assert discovery.get_operation("samsclub:sponsored:AdGroupList").platform == "samsclub"
    assert discovery.get_operation("connect:search:AdGroupList").platform == "connect"


def test_an_unknown_operation_points_at_list_endpoints():
    with pytest.raises(SpecError) as excinfo:
        discovery.get_operation("noSuchOperation")
    assert "list_endpoints" in str(excinfo.value)


def test_an_unknown_operation_within_a_known_api_names_the_api():
    with pytest.raises(SpecError) as excinfo:
        discovery.get_operation("noSuchOperation", api="connect:search")
    assert "connect:search" in str(excinfo.value)


# ── describe ──────────────────────────────────────────────────────────────────


def test_describe_returns_the_operation_and_its_schema_closure():
    described = discovery.describe_endpoint("marketplace:order-management:getAllOrders")
    assert described["method"] == "GET"
    assert described["platform"] == "marketplace"
    assert isinstance(described["components"]["schemas"], dict)


def test_describe_strips_server_managed_headers():
    for operation_id in (
        "marketplace:order-management:getAllOrders",
        "connect:search:AdGroupList",
    ):
        described = discovery.describe_endpoint(operation_id)
        surfaced = [
            str(p.get("name", "")).casefold()
            for p in described["operation"].get("parameters", [])
            if p.get("in") == "header"
        ]
        assert not (set(surfaced) & MANAGED_HEADERS)


def test_describe_keeps_non_header_parameters():
    described = discovery.describe_endpoint("marketplace:order-management:getAllOrders")
    kinds = {p.get("in") for p in described["operation"].get("parameters", [])}
    assert "query" in kinds


def test_describe_does_not_mutate_the_cached_operation():
    first = discovery.describe_endpoint("marketplace:order-management:getAllOrders")
    raw_headers = [
        p
        for p in discovery.get_operation("marketplace:order-management:getAllOrders").raw.get(
            "parameters", []
        )
        if p.get("in") == "header"
    ]
    assert raw_headers, "expected the underlying operation to still declare header params"
    assert first["operation"] is not None


def test_ref_closure_is_transitive():
    described = discovery.describe_endpoint("marketplace:item-management:getAnItem")
    schemas = described["components"]["schemas"]
    referenced = {
        ref.rsplit("/", 1)[1] for ref in discovery._collect_refs(schemas) if "schemas/" in ref
    }
    assert referenced <= set(schemas), "every nested $ref should already be resolved"


def test_describe_of_an_unknown_operation_raises():
    with pytest.raises(SpecError):
        discovery.describe_endpoint("connect:search:nope")


# ── cache invalidation ────────────────────────────────────────────────────────


def test_a_refreshed_spec_is_picked_up_without_a_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    before = len(discovery.list_endpoints(api="connect:search"))
    assert before > 1

    monkeypatch.setattr(specs, "cache_dir", lambda: tmp_path)
    target = tmp_path / "connect" / "search.openapi.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "openapi": "3.0.0",
                "info": {"title": "refreshed"},
                "paths": {"/only": {"get": {"operationId": "OnlyOne"}}},
            }
        )
    )

    rows = discovery.list_endpoints(api="connect:search")
    assert [r["operation_id"] for r in rows] == ["connect:search:OnlyOne"]


# ── Operation helpers ─────────────────────────────────────────────────────────


def _operation(raw: dict[str, object]) -> Operation:
    return Operation(
        operation_id="X", api="marketplace:x", method="get", path="/x", summary="", tags=(), raw=raw
    )


def test_declares_header_is_case_insensitive():
    op = _operation({"parameters": [{"in": "header", "name": "WM_MARKET"}]})
    assert op.declares_header("wm_market")
    assert not op.declares_header("WM_SANDBOX")


def test_header_enum_returns_the_first_declared_value():
    op = _operation(
        {"parameters": [{"in": "header", "name": "WM_MARKET", "schema": {"enum": ["us", "US"]}}]}
    )
    assert op.header_enum("WM_MARKET") == "us"
    assert op.header_enum("WM_SANDBOX") is None


def test_header_enum_ignores_a_non_string_or_absent_enum():
    op = _operation(
        {"parameters": [{"in": "header", "name": "H", "schema": {"enum": [3]}}]},
    )
    assert op.header_enum("H") is None


def test_response_media_types_covers_only_success_responses():
    op = _operation(
        {
            "responses": {
                "200": {"content": {"application/json": {}, "text/csv": {}}},
                "404": {"content": {"application/problem+json": {}}},
            }
        }
    )
    assert op.response_media_types() == ("application/json", "text/csv")


def test_qualified_id_and_platform_derive_from_the_api():
    op = _operation({})
    assert op.qualified_id == "marketplace:x:X"
    assert op.platform == "marketplace"
