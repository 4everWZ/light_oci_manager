"""Thin async wrapper around the synchronous oci SDK.

Spec decision (per ``docs/design/architecture.md``): use the official sync
SDK and push every blocking call through ``asyncio.to_thread`` so the
Telegram event loop stays responsive without re-implementing OCI request
signing.

This module owns:
- per-profile SDK client construction (cached at startup)
- the slice of OCI calls the bot commands need
- normalising SDK exceptions into ``OciApiError`` with the request id
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import oci
from oci.exceptions import ConfigFileNotFound, InvalidConfig, ServiceError

from app.config import OciProfile, OciSection
from app.formatters import IpRow

# Per spec §4.4: STOP / REBOOT must go through confirmation. We default to
# the *graceful* OCI actions because the spec uses bare "stop" / "reboot".
# See docs/tradeoffs.md T-001.
INSTANCE_ACTIONS: frozenset[str] = frozenset(
    {"START", "STOP", "SOFTSTOP", "RESET", "SOFTRESET"}
)


class OciApiError(RuntimeError):
    """Raised when an OCI SDK call fails.

    Attributes:
        status: HTTP status code returned by the OCI service, if any.
        code: service-specific error code (e.g. ``NotAuthorizedOrNotFound``).
        request_id: opaque-request-id from the OCI response, surfaced to the
            user per spec §9.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id

    def user_message(self) -> str:
        parts: list[str] = [f"OCI API error: {self.args[0]}"]
        if self.code:
            parts.append(f"code={self.code}")
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " ".join(parts)


@dataclass
class _ProfileBundle:
    profile: OciProfile
    compute: oci.core.ComputeClient
    network: oci.core.VirtualNetworkClient
    block_storage: oci.core.BlockstorageClient
    identity: oci.identity.IdentityClient
    limits: oci.limits.LimitsClient
    ads_cache: list[Any] | None = None  # lazily populated via list_availability_domains


class OciClient:
    """Holds one SDK client bundle per configured OCI profile."""

    def __init__(self, oci_section: OciSection) -> None:
        self._oci_section = oci_section
        self._bundles: dict[str, _ProfileBundle] = {}
        for name, profile in oci_section.profiles.items():
            self._bundles[name] = self._build_bundle(profile)

    @staticmethod
    def _build_bundle(profile: OciProfile) -> _ProfileBundle:
        sdk_config = profile.as_oci_sdk_config()
        try:
            oci.config.validate_config(sdk_config)
        except (InvalidConfig, ConfigFileNotFound) as exc:
            raise OciApiError(
                f"Invalid OCI config for profile {profile.name!r}: {exc}"
            ) from exc
        return _ProfileBundle(
            profile=profile,
            compute=oci.core.ComputeClient(sdk_config),
            network=oci.core.VirtualNetworkClient(sdk_config),
            block_storage=oci.core.BlockstorageClient(sdk_config),
            identity=oci.identity.IdentityClient(sdk_config),
            limits=oci.limits.LimitsClient(sdk_config),
        )

    @property
    def profile_names(self) -> list[str]:
        return list(self._bundles.keys())

    def get_profile(self, profile: str | None = None) -> OciProfile:
        return self._bundle(profile).profile

    def _bundle(self, profile: str | None) -> _ProfileBundle:
        target = profile or self._oci_section.default_profile
        if target not in self._bundles:
            raise OciApiError(f"Unknown OCI profile {target!r}")
        return self._bundles[target]

    # ------------------------------------------------------------------ compute

    async def list_instances(self, profile: str | None = None) -> list[Any]:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._list_instances_sync, bundle)

    @staticmethod
    def _list_instances_sync(bundle: _ProfileBundle) -> list[Any]:
        try:
            response = oci.pagination.list_call_get_all_results(
                bundle.compute.list_instances,
                bundle.profile.compartment_id,
            )
            return list(response.data)
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    async def get_instance(self, instance_id: str, profile: str | None = None) -> Any:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._get_instance_sync, bundle, instance_id)

    @staticmethod
    def _get_instance_sync(bundle: _ProfileBundle, instance_id: str) -> Any:
        try:
            return bundle.compute.get_instance(instance_id).data
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    async def instance_action(
        self, instance_id: str, action: str, profile: str | None = None
    ) -> Any:
        """Issue an OCI instance action (START/STOP/SOFTSTOP/RESET/SOFTRESET).

        Raises ``ValueError`` for unknown actions (defence against callers
        passing user-controlled strings).
        """
        if action not in INSTANCE_ACTIONS:
            raise ValueError(f"Unsupported instance action: {action!r}")
        bundle = self._bundle(profile)
        return await asyncio.to_thread(
            self._instance_action_sync, bundle, instance_id, action
        )

    @staticmethod
    def _instance_action_sync(
        bundle: _ProfileBundle, instance_id: str, action: str
    ) -> Any:
        try:
            return bundle.compute.instance_action(instance_id, action).data
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    # ----------------------------------------------------------------- network

    async def get_ip_info(self, instance: Any, profile: str | None = None) -> IpRow:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._get_ip_info_sync, bundle, instance)

    @staticmethod
    def _get_ip_info_sync(bundle: _ProfileBundle, instance: Any) -> IpRow:
        try:
            attachments = oci.pagination.list_call_get_all_results(
                bundle.compute.list_vnic_attachments,
                bundle.profile.compartment_id,
                instance_id=instance.id,
            ).data
            public_ip: str | None = None
            private_ip: str | None = None
            subnet_id: str | None = None
            vnic_id: str | None = None
            for att in attachments:
                if att.lifecycle_state != "ATTACHED":
                    continue
                vnic = bundle.network.get_vnic(att.vnic_id).data
                if getattr(vnic, "is_primary", False) or vnic_id is None:
                    vnic_id = vnic.id
                    subnet_id = vnic.subnet_id
                    private_ip = vnic.private_ip
                    public_ip = vnic.public_ip
                    if getattr(vnic, "is_primary", False):
                        break
            return IpRow(
                instance_name=instance.display_name,
                instance_id=instance.id,
                public_ip=public_ip,
                private_ip=private_ip,
                subnet_id=subnet_id,
                vnic_id=vnic_id,
                state=instance.lifecycle_state,
            )
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    async def list_security_lists(self, profile: str | None = None) -> list[Any]:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._list_security_lists_sync, bundle)

    @staticmethod
    def _list_security_lists_sync(bundle: _ProfileBundle) -> list[Any]:
        try:
            return list(
                oci.pagination.list_call_get_all_results(
                    bundle.network.list_security_lists,
                    bundle.profile.compartment_id,
                ).data
            )
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    async def get_security_list(
        self, security_list_id: str, profile: str | None = None
    ) -> Any:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(
            self._get_security_list_sync, bundle, security_list_id
        )

    @staticmethod
    def _get_security_list_sync(bundle: _ProfileBundle, sl_id: str) -> Any:
        try:
            return bundle.network.get_security_list(sl_id).data
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    # ------------------------------------------------------------ block storage

    async def list_boot_volumes(self, profile: str | None = None) -> list[Any]:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._list_boot_volumes_sync, bundle)

    @staticmethod
    def _list_boot_volumes_sync(bundle: _ProfileBundle) -> list[Any]:
        try:
            ads = OciClient._availability_domains_locked(bundle)
            volumes: list[Any] = []
            for ad in ads:
                page = oci.pagination.list_call_get_all_results(
                    bundle.block_storage.list_boot_volumes,
                    availability_domain=ad.name,
                    compartment_id=bundle.profile.compartment_id,
                ).data
                volumes.extend(page)
            return volumes
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    # ----------------------------------------------------------------- identity

    async def list_availability_domains(
        self, profile: str | None = None
    ) -> list[Any]:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(self._list_ads_sync, bundle)

    @staticmethod
    def _list_ads_sync(bundle: _ProfileBundle) -> list[Any]:
        try:
            return OciClient._availability_domains_locked(bundle)
        except ServiceError as exc:
            raise _to_api_error(exc) from exc

    @staticmethod
    def _availability_domains_locked(bundle: _ProfileBundle) -> list[Any]:
        # Tiny per-process cache. ADs do not change at runtime.
        if bundle.ads_cache is None:
            bundle.ads_cache = list(
                bundle.identity.list_availability_domains(bundle.profile.tenancy).data
            )
        return bundle.ads_cache

    # ------------------------------------------------------------------- limits

    async def list_limit_values(
        self, service_name: str, profile: str | None = None
    ) -> list[Any]:
        bundle = self._bundle(profile)
        return await asyncio.to_thread(
            self._list_limit_values_sync, bundle, service_name
        )

    @staticmethod
    def _list_limit_values_sync(
        bundle: _ProfileBundle, service_name: str
    ) -> list[Any]:
        try:
            return list(
                oci.pagination.list_call_get_all_results(
                    bundle.limits.list_limit_values,
                    bundle.profile.tenancy,
                    service_name=service_name,
                ).data
            )
        except ServiceError as exc:
            raise _to_api_error(exc) from exc


def _to_api_error(exc: ServiceError) -> OciApiError:
    return OciApiError(
        message=str(getattr(exc, "message", "") or exc),
        status=getattr(exc, "status", None),
        code=getattr(exc, "code", None),
        request_id=getattr(exc, "request_id", None),
    )
