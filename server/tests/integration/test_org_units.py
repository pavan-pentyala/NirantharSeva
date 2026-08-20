"""GET /org_units — P4.2. Unscoped (any authenticated role sees the whole
tree), unlike GET /referrals; org names aren't patient data.
"""


async def test_org_units_returns_the_seeded_tree(client, auth_headers):
    resp = await client.get("/org_units", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    names = {row["name"] for row in body["org_units"]}
    assert names == {"PHC Ramnagar", "Sub-centre Kotwali", "Village A", "Village B"}

    by_name = {row["name"]: row for row in body["org_units"]}
    assert by_name["PHC Ramnagar"]["parent_id"] is None
    assert by_name["Sub-centre Kotwali"]["parent_id"] == by_name["PHC Ramnagar"]["id"]
    assert by_name["Village A"]["parent_id"] == by_name["Sub-centre Kotwali"]["id"]
    assert by_name["Village B"]["parent_id"] == by_name["Sub-centre Kotwali"]["id"]


async def test_org_units_visible_to_every_role_not_just_the_actors_own_subtree(
    client, asha_b_auth_headers
):
    # asha_b's own subtree is just Village B — the whole tree (including
    # PHC Ramnagar and Village A) should still come back, unlike GET
    # /referrals, which would 404 outside the caller's subtree.
    resp = await client.get("/org_units", headers=asha_b_auth_headers)
    assert resp.status_code == 200
    names = {row["name"] for row in resp.json()["org_units"]}
    assert names == {"PHC Ramnagar", "Sub-centre Kotwali", "Village A", "Village B"}


async def test_org_units_requires_authentication(client):
    resp = await client.get("/org_units")
    assert resp.status_code == 401
