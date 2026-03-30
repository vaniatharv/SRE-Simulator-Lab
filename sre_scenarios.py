"""Scenario definitions for each difficulty tier."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScenarioDefinition(BaseModel):
    """Immutable scenario metadata and starting state."""

    name: str
    difficulty: str
    alert: str
    incident_service_health: dict[str, str]
    dependencies: dict[str, list[str]]
    initial_logs: dict[str, list[str]]
    initial_visible_logs: dict[str, list[str]] = Field(default_factory=dict)
    baseline_metrics: dict[str, dict[str, float]]
    incident_metrics: dict[str, dict[str, float]]
    runbook: list[str]
    root_cause: str
    root_cause_aliases: list[str]
    root_cause_service: str
    valid_fix_actions: list[str]
    invalid_actions: list[str]
    destructive_commands: list[str] = Field(default_factory=list)
    relevant_log_services: set[str] = Field(default_factory=set)
    diagnostic_path: list[str] = Field(default_factory=list)
    escalation_hints: dict[str, str] = Field(default_factory=dict)
    evolution_logs: dict[str, list[str]] = Field(default_factory=dict)
    recovery_logs: dict[str, list[str]] = Field(default_factory=dict)
    impact_weights: dict[str, float] = Field(default_factory=dict)
    step_budget: int


def build_easy_scenario() -> ScenarioDefinition:
    """Return the easy single-service incident."""

    return ScenarioDefinition(
        name="checkout_secret_rotation",
        difficulty="easy",
        alert="P1: checkout-api error rate is above 45% and pods are crashlooping.",
        incident_service_health={
            "checkout-api": "down",
        },
        dependencies={
            "checkout-api": [],
        },
        initial_logs={
            "checkout-api": [
                "INFO payment provider timeout recovered after retry.",
                "ERROR secret loader: DB_PASSWORD missing after config rollout checkout-config-v12.",
                "CRITICAL application bootstrap failed; exiting.",
            ],
        },
        initial_visible_logs={
            "checkout-api": [
                "ALERT CONTEXT: checkout-api started failing immediately after a config rollout.",
            ],
        },
        baseline_metrics={
            "checkout-api": {
                "latency_ms": 85.0,
                "error_rate": 0.01,
                "cpu": 0.55,
                "availability": 99.95,
            },
        },
        incident_metrics={
            "checkout-api": {
                "latency_ms": 1250.0,
                "error_rate": 0.47,
                "cpu": 0.18,
                "availability": 71.0,
            },
        },
        runbook=[
            "Start with the alerted service before touching production.",
            "Inspect recent checkout-api logs and recent rollout/config changes.",
            "Avoid restart loops until a concrete cause is confirmed.",
        ],
        root_cause="checkout-api bad config rollout removed DB_PASSWORD",
        root_cause_aliases=[
            "checkout-api bad config rollout removed db_password",
            "db_password missing after checkout config rollout",
            "missing db_password on checkout-api",
        ],
        root_cause_service="checkout-api",
        valid_fix_actions=[
            "rollback_config:checkout-api",
            "restore_secret:checkout-api",
        ],
        invalid_actions=[
            "restart_service:checkout-api",
            "scale_service:checkout-api",
        ],
        relevant_log_services={"checkout-api"},
        diagnostic_path=["checkout-api"],
        escalation_hints={
            "platform": "Platform confirms checkout-config-v12 removed DB_PASSWORD from the deployment manifest.",
            "release-engineering": "Release engineering confirms the last config rollout removed DB_PASSWORD.",
        },
        evolution_logs={
            "checkout-api": [
                "ERROR checkout-api startup failed again because DB_PASSWORD is unset.",
                "WARN checkout-api remains unavailable until config is rolled back.",
            ],
        },
        recovery_logs={
            "checkout-api": [
                "INFO config rollback completed; DB_PASSWORD restored.",
                "INFO readiness checks passing and traffic restored.",
            ],
        },
        impact_weights={
            "checkout-api": 1.0,
        },
        step_budget=6,
    )


def build_medium_scenario() -> ScenarioDefinition:
    """Return the medium cascading dependency incident."""

    return ScenarioDefinition(
        name="orders_chain_certificate_expiry",
        difficulty="medium",
        alert="P1: api-gateway latency is above 2s and order creation requests are failing.",
        incident_service_health={
            "api-gateway": "degraded",
            "orders-service": "degraded",
            "inventory-db": "down",
        },
        dependencies={
            "api-gateway": ["orders-service"],
            "orders-service": ["inventory-db"],
            "inventory-db": [],
        },
        initial_logs={
            "api-gateway": [
                "WARN upstream request to orders-service exceeded 1500ms.",
                "INFO mobile clients are retrying more aggressively than usual.",
            ],
            "orders-service": [
                "ERROR could not persist reservation: x509 certificate has expired for inventory-db.",
                "WARN retrying inventory write in 100ms.",
            ],
            "inventory-db": [
                "CRITICAL listener rejected TLS handshake: certificate expired at 2026-03-29T11:40:00Z.",
                "INFO disk usage remains stable at 62%.",
            ],
        },
        initial_visible_logs={
            "api-gateway": [
                "ALERT CONTEXT: order creation endpoints are timing out through api-gateway.",
            ],
        },
        baseline_metrics={
            "api-gateway": {
                "latency_ms": 120.0,
                "error_rate": 0.02,
                "cpu": 0.48,
                "availability": 99.95,
            },
            "orders-service": {
                "latency_ms": 140.0,
                "error_rate": 0.02,
                "cpu": 0.52,
                "availability": 99.9,
            },
            "inventory-db": {
                "latency_ms": 18.0,
                "error_rate": 0.0,
                "cpu": 0.4,
                "availability": 99.99,
            },
        },
        incident_metrics={
            "api-gateway": {
                "latency_ms": 2400.0,
                "error_rate": 0.31,
                "cpu": 0.71,
                "availability": 90.0,
            },
            "orders-service": {
                "latency_ms": 1380.0,
                "error_rate": 0.44,
                "cpu": 0.83,
                "availability": 86.0,
            },
            "inventory-db": {
                "latency_ms": 920.0,
                "error_rate": 0.88,
                "cpu": 0.33,
                "availability": 60.0,
            },
        },
        runbook=[
            "Start at the alert source, then walk the dependency chain toward the deepest unhealthy service.",
            "Use dependency checks to separate blast radius from root cause.",
            "A direct restart of the front door service is rarely enough in a cascading failure.",
        ],
        root_cause="inventory-db certificate expired and broke the api-gateway -> orders-service -> inventory-db chain",
        root_cause_aliases=[
            "inventory-db certificate expired",
            "expired tls certificate on inventory-db",
            "inventory-db tls certificate expired",
        ],
        root_cause_service="inventory-db",
        valid_fix_actions=[
            "rotate_certificate:inventory-db",
            "renew_certificate:inventory-db",
        ],
        invalid_actions=[
            "restart_service:api-gateway",
            "restart_service:orders-service",
            "scale_service:api-gateway",
        ],
        relevant_log_services={"api-gateway", "orders-service", "inventory-db"},
        diagnostic_path=["api-gateway", "orders-service", "inventory-db"],
        escalation_hints={
            "database": "Database team confirms the inventory-db TLS certificate expired and needs rotation.",
            "security": "Security confirms the inventory-db certificate expired and was not rotated.",
        },
        evolution_logs={
            "api-gateway": [
                "ERROR upstream dependency orders-service is still timing out.",
                "WARN queueing requests because orders-service remains degraded.",
            ],
            "orders-service": [
                "ERROR dependency call to inventory-db failed TLS validation.",
                "WARN order backlog is growing while inventory-db is unavailable.",
            ],
            "inventory-db": [
                "CRITICAL inventory-db continues rejecting clients with an expired certificate.",
                "ERROR new connections are failing certificate validation.",
            ],
        },
        recovery_logs={
            "api-gateway": [
                "INFO api-gateway latency returned to baseline once upstream recovered.",
            ],
            "orders-service": [
                "INFO orders-service drained its backlog after inventory-db recovered.",
            ],
            "inventory-db": [
                "INFO new TLS certificate loaded successfully.",
                "INFO inventory-db is accepting client connections again.",
            ],
        },
        impact_weights={
            "api-gateway": 0.45,
            "orders-service": 0.75,
            "inventory-db": 1.0,
        },
        step_budget=8,
    )


def build_hard_scenario() -> ScenarioDefinition:
    """Return the hard noisy multi-service incident."""

    return ScenarioDefinition(
        name="recommendations_schema_regression",
        difficulty="hard",
        alert="P1: api-gateway latency is above 4s, recommendation widgets are failing, and SLA burn is accelerating.",
        incident_service_health={
            "web-frontend": "degraded",
            "api-gateway": "degraded",
            "recommendation-service": "degraded",
            "feature-store": "down",
            "session-cache": "degraded",
        },
        dependencies={
            "web-frontend": ["api-gateway"],
            "api-gateway": ["recommendation-service"],
            "recommendation-service": ["feature-store", "session-cache"],
            "feature-store": [],
            "session-cache": [],
        },
        initial_logs={
            "web-frontend": [
                "ERROR recommendation widget request returned 502 from api-gateway.",
                "INFO image sprite CDN latency recovered after brief spike.",
            ],
            "api-gateway": [
                "WARN upstream recommendation-service exceeded 3000ms.",
                "INFO TLS handshake retries to analytics collector recovered.",
            ],
            "recommendation-service": [
                "ERROR feature vector lookup failed: schema version 42 is incompatible with expected 41 in feature-store.",
                "WARN session-cache miss ratio is 78%.",
                "INFO fallback model warmed successfully on one replica.",
            ],
            "feature-store": [
                "CRITICAL feature-store deploy 2026.03.29-rc2 started serving schema v42 before consumers were upgraded.",
                "INFO background compaction completed in 80ms.",
            ],
            "session-cache": [
                "WARN cache eviction burst after traffic spike.",
                "INFO cache hit ratio dipped to 18%.",
            ],
        },
        initial_visible_logs={
            "api-gateway": [
                "ALERT CONTEXT: api-gateway is timing out on recommendation requests.",
            ],
        },
        baseline_metrics={
            "web-frontend": {
                "latency_ms": 70.0,
                "error_rate": 0.01,
                "cpu": 0.44,
                "availability": 99.98,
            },
            "api-gateway": {
                "latency_ms": 105.0,
                "error_rate": 0.02,
                "cpu": 0.51,
                "availability": 99.95,
            },
            "recommendation-service": {
                "latency_ms": 130.0,
                "error_rate": 0.02,
                "cpu": 0.57,
                "availability": 99.9,
            },
            "feature-store": {
                "latency_ms": 45.0,
                "error_rate": 0.01,
                "cpu": 0.36,
                "availability": 99.99,
            },
            "session-cache": {
                "latency_ms": 8.0,
                "error_rate": 0.01,
                "cpu": 0.32,
                "availability": 99.99,
                "cache_hit_rate": 96.0,
            },
        },
        incident_metrics={
            "web-frontend": {
                "latency_ms": 960.0,
                "error_rate": 0.19,
                "cpu": 0.69,
                "availability": 94.0,
            },
            "api-gateway": {
                "latency_ms": 4200.0,
                "error_rate": 0.41,
                "cpu": 0.86,
                "availability": 88.0,
            },
            "recommendation-service": {
                "latency_ms": 2600.0,
                "error_rate": 0.56,
                "cpu": 0.92,
                "availability": 82.0,
            },
            "feature-store": {
                "latency_ms": 1300.0,
                "error_rate": 0.91,
                "cpu": 0.29,
                "availability": 58.0,
            },
            "session-cache": {
                "latency_ms": 40.0,
                "error_rate": 0.13,
                "cpu": 0.61,
                "availability": 93.0,
                "cache_hit_rate": 18.0,
            },
        },
        runbook=[
            "Triage the alert source, then move down the dependency chain until the deepest failing contract is exposed.",
            "Noise is expected in hard incidents; prefer evidence that explains the whole blast radius.",
            "Do not flush or drop caches without evidence. In this scenario cache destruction is penalized.",
        ],
        root_cause="feature-store schema mismatch after bad deploy broke recommendation-service consumers",
        root_cause_aliases=[
            "feature-store schema mismatch after bad deploy",
            "schema version 42 incompatible with expected 41 in feature-store",
            "feature-store bad deploy introduced schema mismatch",
        ],
        root_cause_service="feature-store",
        valid_fix_actions=[
            "rollback_deploy:feature-store",
            "pin_schema_version:feature-store",
        ],
        invalid_actions=[
            "restart_service:api-gateway",
            "scale_service:recommendation-service",
            "flush_cache:session-cache",
        ],
        destructive_commands=[
            "drop_cache",
            "drop_cache session-cache",
            "flush_cache",
        ],
        relevant_log_services={"api-gateway", "recommendation-service", "feature-store"},
        diagnostic_path=["api-gateway", "recommendation-service", "feature-store"],
        escalation_hints={
            "ml-platform": "ML platform confirms feature-store schema v42 rolled out before recommendation-service consumers were upgraded.",
            "data-platform": "Data platform confirms the feature-store contract changed ahead of its consumers.",
        },
        evolution_logs={
            "web-frontend": [
                "ERROR personalized home widgets disabled due to recommendation timeout.",
                "WARN cart conversion is dropping while recommendation panels are unavailable.",
            ],
            "api-gateway": [
                "ERROR /recommendations upstream unavailable after three retries.",
                "WARN api-gateway backlog is growing because recommendation-service remains slow.",
            ],
            "recommendation-service": [
                "ERROR feature-store contract mismatch persists; fallback capacity exhausted.",
                "WARN session-cache retries are increasing but do not explain the primary failure.",
            ],
            "feature-store": [
                "CRITICAL rejecting recommendation-service requests because schema contract mismatch remains.",
                "ERROR feature-store rollback has not yet occurred; incompatible schema still active.",
            ],
            "session-cache": [
                "WARN cache miss storm continues while recommendation-service retries pile up.",
                "INFO local cache warmup completed on one shard but global misses remain high.",
            ],
        },
        recovery_logs={
            "web-frontend": [
                "INFO recommendation widgets restored on the homepage.",
            ],
            "api-gateway": [
                "INFO api-gateway recommendation latency returned to baseline.",
            ],
            "recommendation-service": [
                "INFO recommendation-service consumer contract matches feature-store again.",
            ],
            "feature-store": [
                "INFO feature-store rolled back to compatible schema version.",
                "INFO serving feature vectors normally.",
            ],
            "session-cache": [
                "INFO session-cache stabilized once upstream retries subsided.",
            ],
        },
        impact_weights={
            "web-frontend": 0.3,
            "api-gateway": 0.6,
            "recommendation-service": 0.85,
            "feature-store": 1.0,
            "session-cache": 0.4,
        },
        step_budget=10,
    )


def get_scenario(difficulty: str) -> ScenarioDefinition:
    """Return a fresh scenario object for the requested difficulty."""

    normalized = difficulty.strip().lower()
    builders = {
        "easy": build_easy_scenario,
        "medium": build_medium_scenario,
        "hard": build_hard_scenario,
    }
    try:
        return builders[normalized]()
    except KeyError as exc:
        valid = ", ".join(sorted(builders))
        raise ValueError(f"Unknown difficulty '{difficulty}'. Expected one of: {valid}.") from exc
