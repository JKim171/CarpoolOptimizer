"""Why somebody did not get a ride.

Telling an organizer *"three people are unassigned"* is useless; telling them *"three people are
unassigned because every car is full"* is actionable, and *"because the only driver near them caps
their detour at 10 minutes"* is more actionable still. Surfacing the reason is a product requirement
(docs/design.md 5, `unassigned_participants.reason`), which means it has to be derived rather than
guessed at by the storage layer.

The method is relaxation. A rider who fits into no car is offered one again with a single class of
rule switched off; whichever class lets them in is the one actually binding. That is a genuine
diagnosis rather than a heuristic label, and it is stated in terms of `validate.Constraint` -- the
same vocabulary the solvers use -- leaving it to the persistence layer to translate into whatever
strings its columns expect.

Pure, like everything else here: no clock, no database, no provider (docs/design.md 4.1).
"""

from __future__ import annotations

from .models import ProblemInstance, Route, Solution
from .validate import Constraint, route_feasible

#: Tried in this order, so the answer is the most concrete thing the organizer could act on. Seats
#: come first because "the cars are full" is the common case and the easiest to fix; a detour cap is
#: one person's setting; a time window is the most specific of the three.
RELAXATION_ORDER = (Constraint.SEATS, Constraint.DETOUR, Constraint.TIME)


def _insertable(instance: ProblemInstance, route: Route, rider: str, *, relax: Constraint) -> bool:
    """Whether `rider` fits anywhere in `route` once `relax` is ignored.

    Every insertion position is tried, not just the end: a rider who breaks a time window when
    collected last may be perfectly placeable first.
    """
    participant = instance.participant(rider)
    ignore = frozenset({relax})
    outbound_options = (
        [(*route.outbound[:i], rider, *route.outbound[i:]) for i in range(len(route.outbound) + 1)]
        if participant.needs_outbound
        else [route.outbound]
    )
    inbound_options = (
        [(*route.inbound[:i], rider, *route.inbound[i:]) for i in range(len(route.inbound) + 1)]
        if participant.needs_return
        else [route.inbound]
    )
    return any(
        route_feasible(instance, Route(route.driver_id, outbound, inbound), ignore=ignore)
        for outbound in outbound_options
        for inbound in inbound_options
    )


def unassigned_reason(
    instance: ProblemInstance, solution: Solution, participant_id: str
) -> Constraint:
    """The rule that kept `participant_id` out of every car.

    `Constraint.ROLE` is the answer when nobody could have carried them at all -- no participant can
    drive, or they are pinned to someone who cannot. `Constraint.PIN` means the pin itself is what
    excludes them: their nominated driver exists and drives, but has no room for them under any
    relaxation. `SEATS` is the fallback when no single relaxation admits them, since a rider who
    still does not fit with every cap lifted is one there is structurally no room for.
    """
    rider = instance.participant(participant_id)

    pinned_to = rider.pinned_driver_id
    if pinned_to is not None:
        if not instance.has(pinned_to) or not instance.participant(pinned_to).role.can_drive:
            return Constraint.ROLE
        candidates = [route for route in solution.routes if route.driver_id == pinned_to]
        if not candidates:
            # Their driver took nobody and has no route at all, so the pin cannot be honoured.
            candidates = [Route(pinned_to)]
    else:
        if not any(p.role.can_drive for p in instance.participants):
            return Constraint.ROLE
        candidates = list(solution.routes)
        if not candidates:
            return Constraint.ROLE

    for relaxation in RELAXATION_ORDER:
        if any(
            _insertable(instance, route, participant_id, relax=relaxation) for route in candidates
        ):
            return relaxation

    return Constraint.PIN if pinned_to is not None else Constraint.SEATS
