"""CarpoolOptimizer domain: the optimization problem, its objective, and feasibility rules.

This package performs no I/O by design (docs/design.md 4.1) -- it is imported unchanged by the API,
by the worker, and by the benchmark harness.
"""

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
    schedule_backward,
    schedule_forward,
)
from .objective import ObjectiveBreakdown, RouteMetrics, churn, evaluate, route_metrics
from .validate import Violation, validate

__all__ = [
    "DESTINATION",
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
    "haversine_matrix",
    "haversine_meters",
    "route_metrics",
    "schedule_backward",
    "schedule_forward",
    "validate",
]
