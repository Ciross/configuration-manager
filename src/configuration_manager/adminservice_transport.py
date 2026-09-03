"""AdminService implementation of the provider capability boundary."""

# Internal collaborators deliberately share transport implementation details.
# pyright: reportPrivateUsage=false, reportUnusedClass=false

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import quote

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
    NavigationQuery,
    ODataQueryOptions,
    ProviderMethodCall,
    RawMethodResult,
    RawPage,
    RawRecord,
    _Continuation,
)

_ENTITY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class _AdminServiceContinuation:
    owner: object
    surface: AdminServiceSurface
    url: httpx2.URL


class _AdminServiceProviderTransport:
    """Translate entity collection and keyed requests to AdminService HTTP."""

    __slots__ = ("_admin", "_owner")

    def __init__(self, admin: AdminService) -> None:
        self._admin = admin
        self._owner = object()

    def query_entities(self, request: EntityQuery) -> RawPage:
        description = self._surface_description(request.surface)
        try:
            if request.continuation is not None:
                state = request.continuation._value
                if (
                    not isinstance(state, _AdminServiceContinuation)
                    or state.owner is not self._owner
                ):
                    raise ValueError("page continuation belongs to another transport")
                if state.surface is not request.surface:
                    raise ValueError("page continuation belongs to another surface")
                payload = self._admin._get_json_url(state.url)
            else:
                self._validate_entity_name(request.entity)
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
                    f"AdminService {description} query failed with HTTP "
                    f"{error.status_code}"
                ) from error
            raise
        except _AdminServiceResponseError as error:
            raise QueryError(
                f"AdminService {description} query returned a malformed response"
            ) from error
        return self._parse_page(payload, request.surface)

    def query_navigation(self, request: NavigationQuery) -> RawPage | None:
        """Query one structurally described keyed navigation collection."""
        description = self._surface_description(request.surface)
        is_continuation = request.continuation is not None
        try:
            if request.continuation is not None:
                state = request.continuation._value
                if (
                    not isinstance(state, _AdminServiceContinuation)
                    or state.owner is not self._owner
                ):
                    raise ValueError("page continuation belongs to another transport")
                if state.surface is not request.surface:
                    raise ValueError("page continuation belongs to another surface")
                payload = self._admin._get_json_url(state.url)
            else:
                self._validate_entity_name(request.entity)
                self._validate_navigation_name(request.navigation)
                literal = self._serialize_key(request.key)
                root = quote(f"{request.entity}({literal})", safe="()'_-.")
                path = f"{root}/{request.navigation}"
                payload = self._admin.get_json(
                    request.surface,
                    path,
                    params=self._query_params(request.options),
                )
        except _AdminServiceHTTPStatusError as error:
            if error.status_code == 404 and not is_continuation:
                return None
            if 400 <= error.status_code < 500:
                raise QueryError(
                    f"AdminService {description} navigation query failed with HTTP "
                    f"{error.status_code}"
                ) from error
            raise
        except _AdminServiceResponseError as error:
            raise QueryError(
                f"AdminService {description} navigation query returned a malformed "
                "response"
            ) from error
        return self._parse_page(payload, request.surface)

    @staticmethod
    def _query_params(options: ODataQueryOptions) -> dict[str, str]:
        """Serialize the supported structural OData options deterministically."""
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
        return params

    def _parse_page(self, payload: object, surface: AdminServiceSurface) -> RawPage:
        description = self._surface_description(surface)
        if not isinstance(payload, Mapping) or "value" not in payload:
            raise QueryError(
                f"AdminService {description} query returned a malformed collection"
            )
        envelope = cast("Mapping[object, object]", payload)
        values = envelope["value"]
        if not isinstance(values, list):
            raise QueryError(
                f"AdminService {description} query returned a malformed collection"
            )
        records: list[RawRecord] = []
        for value in cast("list[object]", values):
            if not isinstance(value, Mapping):
                raise QueryError(
                    f"AdminService {description} query returned a malformed collection"
                )
            record = cast("Mapping[object, object]", value)
            if not all(isinstance(key, str) for key in record):
                raise QueryError(
                    f"AdminService {description} query returned a malformed collection"
                )
            records.append(cast("RawRecord", record))
        next_link = envelope.get("@odata.nextLink")
        if next_link is None:
            return Page(records)
        if not isinstance(next_link, str) or not next_link:
            raise QueryError(
                f"AdminService {description} query returned an invalid continuation"
            )
        url = self._validate_continuation(next_link, surface)
        return Page[RawRecord]._from_transport(
            records,
            _Continuation(_AdminServiceContinuation(self._owner, surface, url)),
        )

    def _validate_continuation(
        self, link: str, surface: AdminServiceSurface
    ) -> httpx2.URL:
        description = self._surface_description(surface)
        try:
            url = self._admin.url(surface).join(link)
        except Exception as error:
            raise QueryError(
                f"AdminService {description} query returned an invalid continuation"
            ) from error
        origin = self._admin.url(surface)
        if (
            url.scheme != "https"
            or url.origin != origin.origin
            or bool(url.username)
            or bool(url.password)
            or url.fragment
            or not url.path.startswith(f"/AdminService/{surface.value}/")
        ):
            raise QueryError(
                f"AdminService {description} query returned an unsafe continuation"
            )
        return url

    def get_entity(self, request: EntityKeyQuery) -> RawRecord | None:
        description = self._surface_description(request.surface)
        self._validate_entity_name(request.entity)
        literal = self._serialize_key(request.key)
        # Encode the complete literal before handing it to the URL builder. The
        # structural quotes and parentheses remain readable; key data cannot
        # become a path segment, query, or fragment.
        path = quote(f"{request.entity}({literal})", safe="()'_-.")
        params: dict[str, str] = {}
        if request.options.select:
            params["$select"] = ",".join(request.options.select)
        if request.options.expand:
            params["$expand"] = ",".join(request.options.expand)
        try:
            payload = self._admin.get_json(request.surface, path, params=params)
        except _AdminServiceHTTPStatusError as error:
            if error.status_code == 404:
                return None
            if 400 <= error.status_code < 500:
                raise QueryError(
                    f"AdminService {description} entity request failed with HTTP "
                    f"{error.status_code}"
                ) from error
            raise
        except _AdminServiceResponseError as error:
            raise QueryError(
                f"AdminService {description} entity request returned a malformed "
                "response"
            ) from error
        return self._parse_keyed_entity_response(payload, request.surface)

    @staticmethod
    def _surface_description(surface: AdminServiceSurface) -> str:
        return "WMI" if surface is AdminServiceSurface.WMI else "v1"

    @staticmethod
    def _validate_entity_name(entity: str) -> None:
        if _ENTITY_NAME.fullmatch(entity) is None:
            raise ValueError("entity must be a valid AdminService entity name")

    @staticmethod
    def _validate_navigation_name(navigation: str) -> None:
        if _ENTITY_NAME.fullmatch(navigation) is None:
            raise ValueError(
                "navigation must be a valid AdminService navigation property name"
            )

    @staticmethod
    def _serialize_key(key: bool | int | float | str) -> str:
        if isinstance(key, bool):
            return "true" if key else "false"
        if isinstance(key, int):
            return str(key)
        if isinstance(key, float):
            if not math.isfinite(key):
                raise ValueError("entity key float must be finite")
            return repr(key)
        escaped = key.replace("'", "''")
        return f"'{escaped}'"

    @staticmethod
    def _parse_keyed_entity_response(
        payload: object, surface: AdminServiceSurface = AdminServiceSurface.WMI
    ) -> RawRecord | None:
        description = _AdminServiceProviderTransport._surface_description(surface)
        malformed_envelope = (
            f"AdminService {description} entity request returned a malformed envelope"
        )
        if not isinstance(payload, Mapping):
            raise QueryError(
                f"AdminService {description} entity request returned a malformed object"
            )
        root = cast("Mapping[object, object]", payload)
        if "@odata.context" in root and "value" in root:
            values = root["value"]
            if not isinstance(values, list):
                raise QueryError(malformed_envelope)
            records = cast("list[object]", values)
            if len(records) > 1:
                raise QueryError(malformed_envelope)
            if not records:
                return None
            record_value = records[0]
            if not isinstance(record_value, Mapping):
                raise QueryError(malformed_envelope)
            record = cast("Mapping[object, object]", record_value)
        else:
            record = root
        if not all(isinstance(key, str) for key in record):
            raise QueryError(
                f"AdminService {description} entity request returned a malformed object"
            )
        return cast("RawRecord", record)

    def invoke_method(self, request: ProviderMethodCall) -> RawMethodResult:
        raise MethodInvocationError("AdminService method invocation is not implemented")

    def close(self) -> None:
        self._admin.close()
