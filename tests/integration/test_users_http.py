"""Controlled HTTP coverage for the high-level User boundary."""

# pyright: reportPrivateUsage=false

import httpx2
import pytest

from configuration_manager import ConfigManager, NotFoundError, QueryError, User
from configuration_manager.adminservice import AdminService
from configuration_manager.adminservice_transport import _AdminServiceProviderTransport


def client_with(handler: httpx2.MockTransport) -> ConfigManager:
    return ConfigManager(
        transport=_AdminServiceProviderTransport(
            AdminService("cm01.contoso.com", transport=handler)
        ),
        own_transport=True,
    )


RECORD = {
    "ResourceId": 2063597568,
    "Name": r"CONTOSO\alice (Alice Example)",
    "UniqueUserName": r"CONTOSO\alice",
    "UserName": "alice",
    "FullUserName": "Alice Example",
    "Mail": "alice@example.com",
    "WindowsNTDomain": "CONTOSO",
    "SID": "S-1-5-21-example",
    "DistinguishedName": "CN=Alice Example,OU=Users,DC=contoso,DC=com",
    "IgnoredFutureProperty": "future",
}


@pytest.mark.integration
def test_list_and_get_use_wmi_user_routes_and_return_typed_values() -> None:
    requests: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200, json=RECORD if "(" in request.url.path else {"value": [RECORD]}
        )

    with client_with(httpx2.MockTransport(respond)) as client:
        page = client.users.list(limit=1)
        fetched = client.users.get(2063597568)
    expected = User(
        2063597568,
        r"CONTOSO\alice (Alice Example)",
        r"CONTOSO\alice",
        "alice",
        "Alice Example",
        "alice@example.com",
        "CONTOSO",
        "S-1-5-21-example",
        "CN=Alice Example,OU=Users,DC=contoso,DC=com",
    )
    assert page.items == (expected,)
    assert fetched == expected
    assert requests[0].url.path == "/AdminService/wmi/SMS_R_User"
    assert dict(requests[0].url.params) == {"$top": "1"}
    assert requests[1].url.path == "/AdminService/wmi/SMS_R_User(2063597568)"


@pytest.mark.integration
def test_not_found_and_malformed_user_are_typed_errors() -> None:
    missing = client_with(httpx2.MockTransport(lambda _request: httpx2.Response(404)))
    with pytest.raises(NotFoundError, match="not visible"):
        missing.users.get(1)
    malformed = client_with(
        httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200, json={"value": [{"ResourceId": 1, "Mail": 2}]}
            )
        )
    )
    with pytest.raises(QueryError, match="Mail"):
        malformed.users.list()


@pytest.mark.integration
def test_continuation_is_replayed_exactly_without_reconstructing_top() -> None:
    urls: list[str] = []
    next_url = (
        "https://cm01.contoso.com/AdminService/wmi/SMS_R_User?$skiptoken=opaque%2Bvalue"
    )

    def respond(request: httpx2.Request) -> httpx2.Response:
        urls.append(str(request.url))
        if len(urls) == 1:
            return httpx2.Response(
                200, json={"value": [RECORD], "@odata.nextLink": next_url}
            )
        return httpx2.Response(200, json={"value": []})

    with client_with(httpx2.MockTransport(respond)) as client:
        first = client.users.list(limit=1)
        assert first.has_next
        client.users.next_page(first)
    assert urls[1] == next_url
