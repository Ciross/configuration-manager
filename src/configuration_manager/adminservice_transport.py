"""AdminService implementation of the provider capability boundary."""

# Internal collaborators deliberately share transport implementation details.
# pyright: reportPrivateUsage=false, reportUnusedClass=false

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import httpx2

from .adminservice import (
    AdminService,
    _AdminServiceHTTPStatusError,
    _AdminServiceResponseError,
)
from .exceptions import MethodInvocationError, QueryError
from .pagination import Page
from .transport import (
    AdminServiceSurface,
    EntityKeyQuery,
    EntityQuery,
    ProviderMethodCall,
    RawMethodResult,
    RawPage,
    RawRecord,
    _Continuation,
)

_WMI_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class _AdminServiceContinuation:
    owner: object
    url: httpx2.URL


class _AdminServiceProviderTransport:
    """Translate provider-shaped WMI collection queries to AdminService HTTP."""

    __slots__ = ("_admin", "_owner")

    def __init__(self, admin: AdminService) -> None:
        self._admin = admin
        self._owner = object()

    def query_entities(self, request: EntityQuery) -> RawPage:
        if request.surface is not AdminServiceSurface.WMI:
            raise QueryError("Only AdminService WMI queries are implemented")
        try:
            if request.continuation is not None:
                state = request.continuation._value
                if (
                    not isinstance(state, _AdminServiceContinuation)
                    or state.owner is not self._owner
                ):
                    raise ValueError("page continuation belongs to another transport")
                payload = self._admin._get_json_url(state.url)
            else:
                if _WMI_CLASS.fullmatch(request.entity) is None:
                    raise ValueError("entity must be a valid WMI class name")
                options = request.options
                params: dict[str, str] = {}
                if options.filter is not None:
                    params["$filter"] = options.filter
                if options.select:
                    params["$select"] = ",".join(options.select)
                if options.expand:
                    params["$expand"] = ",".join(options.expand)
                if options.order_by:
                    params["$orderby"] = ",".join(options.order_by)
                if options.top is not None:
                    params["$top"] = str(options.top)
                payload = self._admin.get_json(
                    request.surface, request.entity, params=params
                )
        except _AdminServiceHTTPStatusError as error:
            if 400 <= error.status_code < 500:
                raise QueryError(
                    f"AdminService WMI query failed with HTTP {error.status_code}"
                ) from error
            raise
        except _AdminServiceResponseError as error:
            raise QueryError(
                "AdminService WMI query returned a malformed response"
            ) from error
        return self._parse_page(payload)

    def _parse_page(self, payload: object) -> RawPage:
        if not isinstance(payload, Mapping) or "value" not in payload:
            raise QueryError("AdminService WMI query returned a malformed collection")
        envelope = cast("Mapping[object, object]", payload)
        values = envelope["value"]
        if not isinstance(values, list):
            raise QueryError("AdminService WMI query returned a malformed collection")
        records: list[RawRecord] = []
        for value in cast("list[object]", values):
            if not isinstance(value, Mapping):
                raise QueryError(
                    "AdminService WMI query returned a malformed collection"
                )
            record = cast("Mapping[object, object]", value)
            if not all(isinstance(key, str) for key in record):
                raise QueryError(
                    "AdminService WMI query returned a malformed collection"
                )
            records.append(cast("RawRecord", record))
        next_link = envelope.get("@odata.nextLink")
        if next_link is None:
            return Page(records)
        if not isinstance(next_link, str) or not next_link:
            raise QueryError("AdminService WMI query returned an invalid continuation")
        url = self._validate_continuation(next_link)
        return Page[RawRecord]._from_transport(
            records, _Continuation(_AdminServiceContinuation(self._owner, url))
        )

    def _validate_continuation(self, link: str) -> httpx2.URL:
        try:
            url = self._admin.url(AdminServiceSurface.WMI).join(link)
        except Exception as error:
            raise QueryError(
                "AdminService WMI query returned an invalid continuation"
            ) from error
        origin = self._admin.url(AdminServiceSurface.WMI)
        if (
            url.scheme != "https"
            or url.origin != origin.origin
            or bool(url.username)
            or bool(url.password)
            or url.fragment
            or not url.path.startswith("/AdminService/wmi/")
        ):
            raise QueryError("AdminService WMI query returned an unsafe continuation")
        return url

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        raise QueryError("AdminService entity lookup is not implemented")

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise MethodInvocationError("AdminService method invocation is not implemented")

    def close(self) -> None:
        self._admin.close()
