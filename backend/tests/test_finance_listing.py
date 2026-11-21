"""All Finances listing: identity, search, status and agreement filters."""

import pytest

from tests.finance_helpers import auth, create_finance_account


async def _customer(client, headers, name, mobile):
    response = await client.post(
        "/api/v1/customers/",
        json={"full_name": name, "mobile_number": mobile, "address": "Hyderabad"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _list(client, headers, **params):
    response = await client.get("/api/v1/finance/", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_finance_list_search_filters_and_customer_identity(client, test_user):
    headers = auth(test_user)
    primary = await _customer(client, headers, "Listing Primary Customer", "9320000001")
    other = await _customer(client, headers, "Listing Other Customer", "9320000002")

    first, _ = await create_finance_account(client, headers, primary["id"], principal_amount="1000.00")
    second, _ = await create_finance_account(client, headers, primary["id"], principal_amount="2000.00")
    third, _ = await create_finance_account(client, headers, other["id"], principal_amount="3000.00")

    # Multiple accounts for one customer are all listed with a real name.
    all_rows = await _list(client, headers)
    assert all_rows["meta"]["total"] == 3
    assert {row["id"] for row in all_rows["data"]} == {first["id"], second["id"], third["id"]}
    assert all(row["customer_name"] for row in all_rows["data"])

    # Search covers customer name, mobile number and account number.
    for term, expected in (
        ("Listing Primary Customer", 2),
        ("9320000001", 2),
        (first["account_number"], 1),
    ):
        result = await _list(client, headers, search=term)
        assert result["meta"]["total"] == expected
        assert all(row["customer_name"] == "Listing Primary Customer" for row in result["data"])

    by_account = await _list(client, headers, search=first["account_number"])
    assert [row["id"] for row in by_account["data"]] == [first["id"]]

    # Status and agreement-status filters are applied server-side.
    active = await _list(client, headers, status="ACTIVE")
    assert active["meta"]["total"] == 3
    closed = await _list(client, headers, status="CLOSED")
    assert closed["meta"]["total"] == 0

    signed = await _list(client, headers, agreement_status="CONFIRMED")
    assert signed["meta"]["total"] == 3
    assert all(row["agreement_status"] == "CONFIRMED" for row in signed["data"])
    without_agreement = await _list(client, headers, agreement_status="NONE")
    assert without_agreement["meta"]["total"] == 0
