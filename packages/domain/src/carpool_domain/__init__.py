"""CarpoolOptimizer domain: the optimization problem, its objective, and feasibility rules.

This package performs no I/O by design (docs/design.md 4.1) -- it is imported unchanged by the API,
by the worker, and by the benchmark harness.
"""

from . import greedy
from .generate import DEFAULT_DESTINATION, Distribution, generate_instance
from .models import (
    DESTINATION,
    Location,
    NodeId,
    ObjectiveWeights,
    Participant,
    ProblemInstance,
    Role,
    Route,
    Solution,
    TravelMatrix,
    haversine_matrix,
    haversine_meters,
    inbound_schedule,
    outbound_schedule,
    schedule_backward,
    schedule_forward,
)
from .objective import ObjectiveBreakdown, RouteMetrics, churn, evaluate, route_metrics
from .sequence import MAX_EXACT_STOPS, resequence, sequence_inbound, sequence_outbound
from .validate import Violation, validate

__all__ = [
    "DEFAULT_DESTINATION",
    "DESTINATION",
    "MAX_EXACT_STOPS",
    "Distribution",
    "Location",
    "NodeId",
    "ObjectiveBreakdown",
    "ObjectiveWeights",
    "Participant",
    "ProblemInstance",
    "Role",
    "Route",
    "RouteMetrics",
    "Solution",
    "TravelMatrix",
    "Violation",
    "churn",
    "evaluate",
    "generate_instance",
    "greedy",
    "haversine_matrix",
    "haversine_meters",
    "inbound_schedule",
    "outbound_schedule",
    "resequence",
    "route_metrics",
    "schedule_backward",
    "schedule_forward",
    "sequence_inbound",
    "sequence_outbound",
    "validate",
]
