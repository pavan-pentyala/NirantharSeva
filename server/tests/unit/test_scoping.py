"""app/api/scoping.py's recursive CTE, at each of the three tree levels in
the D4 fixture (server/app/seed.py). docs/decisions/ADR-005.md.
"""

from sqlalchemy import text

from app.api.scoping import SUBTREE_CTE, subtree_params
from app.db import async_session_factory


async def _org_id(name: str):
    async with async_session_factory() as session:
        return (
            await session.execute(
                text("SELECT id FROM org_unit WHERE name = :name"), {"name": name}
            )
        ).scalar_one()


async def _subtree_names(root_id) -> set[str]:
    query = f"{SUBTREE_CTE}\nSELECT o.name FROM org_unit o WHERE o.id IN (SELECT id FROM subtree)"
    async with async_session_factory() as session:
        rows = (await session.execute(text(query), subtree_params(root_id))).scalars().all()
    return set(rows)


async def test_village_subtree_is_just_itself():
    village_a = await _org_id("Village A")
    assert await _subtree_names(village_a) == {"Village A"}


async def test_sub_centre_subtree_includes_both_villages():
    sub_centre = await _org_id("Sub-centre Kotwali")
    assert await _subtree_names(sub_centre) == {"Sub-centre Kotwali", "Village A", "Village B"}


async def test_phc_subtree_includes_everything_below():
    phc = await _org_id("PHC Ramnagar")
    assert await _subtree_names(phc) == {
        "PHC Ramnagar",
        "Sub-centre Kotwali",
        "Village A",
        "Village B",
    }
