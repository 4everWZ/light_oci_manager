"""Fake OCI resource objects and client used by the test suite.

These intentionally implement only the attributes the ``formatters`` and
``oci_client`` consumers actually read. No subclassing of real ``oci.*``
classes — the goal is to keep tests independent of the SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.formatters import IpRow


@dataclass
class FakeShapeConfig:
    ocpus: float = 1.0
    memory_in_gbs: float = 6.0


@dataclass
class FakeInstance:
    id: str
    display_name: str
    lifecycle_state: str = "RUNNING"
    shape: str = "VM.Standard.A1.Flex"
    availability_domain: str = "AD-1"
    shape_config: FakeShapeConfig | None = field(default_factory=FakeShapeConfig)


@dataclass
class FakeVnic:
    id: str
    subnet_id: str = "ocid1.subnet.oc1..fakesubnetid12345678"
    private_ip: str = "10.0.0.10"
    public_ip: str | None = "192.0.2.10"
    is_primary: bool = True


@dataclass
class FakeLimitValue:
    name: str
    value: int
    availability_domain: str | None = None
    scope_type: str = "REGION"


@dataclass
class FakePortRange:
    min: int
    max: int


@dataclass
class FakePortOptions:
    destination_port_range: FakePortRange | None = None


@dataclass
class FakeIngressRule:
    protocol: str  # "1" ICMP, "6" TCP, "17" UDP, "all"
    source: str = "0.0.0.0/0"
    source_type: str = "CIDR_BLOCK"
    tcp_options: FakePortOptions | None = None
    udp_options: FakePortOptions | None = None
    is_stateless: bool = False
    description: str | None = None


@dataclass
class FakeSecurityList:
    id: str
    display_name: str
    ingress_security_rules: list[FakeIngressRule] = field(default_factory=list)


class FakeOciClient:
    """In-memory stand-in for ``app.oci_client.OciClient``.

    Tests construct one with a per-profile instance list and (optionally) a
    VNIC map keyed by instance id.
    """

    def __init__(
        self,
        instances_by_profile: dict[str, list[FakeInstance]],
        vnic_by_instance: dict[str, FakeVnic] | None = None,
        default_profile: str = "default",
        limits_by_profile: dict[str, dict[str, list[FakeLimitValue]]] | None = None,
        security_lists_by_profile: dict[str, list[FakeSecurityList]] | None = None,
    ) -> None:
        self._instances = instances_by_profile
        self._vnics = vnic_by_instance or {}
        self._default = default_profile
        self._limits = limits_by_profile or {}
        self._security_lists = security_lists_by_profile or {}
        self.list_instances_calls: list[str | None] = []
        self.get_ip_info_calls: list[str] = []
        self.instance_action_calls: list[tuple[str, str, str | None]] = []
        self.list_limit_values_calls: list[tuple[str, str | None]] = []
        self.list_security_lists_calls: list[str | None] = []
        self.get_security_list_calls: list[tuple[str, str | None]] = []
        # Tests can preload failures: instance_action_failures[instance_id] = OciApiError
        self.instance_action_failures: dict[str, Exception] = {}

    @property
    def profile_names(self) -> list[str]:
        return list(self._instances.keys())

    async def list_instances(self, profile: str | None = None) -> list[FakeInstance]:
        self.list_instances_calls.append(profile)
        target = profile or self._default
        if target not in self._instances:
            from app.oci_client import OciApiError

            raise OciApiError(f"Unknown profile {target!r}")
        return list(self._instances[target])

    async def get_ip_info(
        self, instance: FakeInstance, profile: str | None = None
    ) -> IpRow:
        self.get_ip_info_calls.append(instance.id)
        vnic = self._vnics.get(instance.id)
        return IpRow(
            instance_name=instance.display_name,
            instance_id=instance.id,
            public_ip=vnic.public_ip if vnic else None,
            private_ip=vnic.private_ip if vnic else None,
            subnet_id=vnic.subnet_id if vnic else None,
            vnic_id=vnic.id if vnic else None,
            state=instance.lifecycle_state,
        )

    async def instance_action(
        self, instance_id: str, action: str, profile: str | None = None
    ) -> FakeInstance:
        """Record the call and mutate the instance's lifecycle_state.

        Mirrors OCI's accepted state transitions enough for tests:
        START → RUNNING, STOP/SOFTSTOP → STOPPED, RESET/SOFTRESET → RUNNING.
        """
        self.instance_action_calls.append((instance_id, action, profile))
        if instance_id in self.instance_action_failures:
            raise self.instance_action_failures[instance_id]
        target_profile = profile or self._default
        for inst in self._instances.get(target_profile, []):
            if inst.id == instance_id:
                if action == "START":
                    inst.lifecycle_state = "RUNNING"
                elif action in ("STOP", "SOFTSTOP"):
                    inst.lifecycle_state = "STOPPED"
                elif action in ("RESET", "SOFTRESET"):
                    inst.lifecycle_state = "RUNNING"
                return inst
        from app.oci_client import OciApiError

        raise OciApiError(f"Instance {instance_id} not found in profile {target_profile!r}")

    async def list_limit_values(
        self, service_name: str, profile: str | None = None
    ) -> list[FakeLimitValue]:
        self.list_limit_values_calls.append((service_name, profile))
        target = profile or self._default
        return list(self._limits.get(target, {}).get(service_name, []))

    async def list_security_lists(
        self, profile: str | None = None
    ) -> list[FakeSecurityList]:
        self.list_security_lists_calls.append(profile)
        target = profile or self._default
        return list(self._security_lists.get(target, []))

    async def get_security_list(
        self, security_list_id: str, profile: str | None = None
    ) -> FakeSecurityList:
        self.get_security_list_calls.append((security_list_id, profile))
        target = profile or self._default
        for sl in self._security_lists.get(target, []):
            if sl.id == security_list_id:
                return sl
        from app.oci_client import OciApiError

        raise OciApiError(
            f"SecurityList {security_list_id} not found in profile {target!r}"
        )
