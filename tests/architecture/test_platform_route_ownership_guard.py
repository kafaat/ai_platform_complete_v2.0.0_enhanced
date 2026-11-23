from scripts.ci.platform_route_ownership_guard import collect_api_routes, validate


def test_platform_extraction_map_matches_full_route_surface():
    result = validate()
    # 625/621 → 627/623 (wave 3 #1587): G14's two governed learning review routes, mapped.
    assert result["surface_routes"] == 627
    assert result["direct_routes"] == 623
    assert result["api_route_declarations"] == 4
    assert result["mapped_routes"] == 627


def test_multi_method_api_routes_are_visible_to_ownership_guard():
    rows = collect_api_routes()
    assert {(r.method, r.path) for r in rows} == {
        ("DELETE,GET,PATCH,POST,PUT", "/api/edge/{path:path}"),
        ("DELETE,GET,PATCH,POST,PUT", "/api/soil/{path:path}"),
        ("DELETE,GET,PATCH,POST,PUT", "/api/segmentation/{path:path}"),
        ("GET,POST", "/api/field-forms/{path:path}"),
    }
