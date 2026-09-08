from carpool_domain import Route, Solution, churn, evaluate, route_metrics


def test_route_metrics_counts_both_legs(instance):
    # outbound d -> a -> b -> dest = 120 + 60 + 180
    # inbound  dest -> b -> a -> d = 180 + 60 + 120
    route = Route("d", outbound=("a", "b"), inbound=("b", "a"))
    m = route_metrics(instance, route)

    assert m.outbound_seconds == 360
    assert m.inbound_seconds == 360
    assert m.direct_seconds == 600  # 300 each way if the driver went alone
    assert m.detour_seconds == 120
    assert m.seats_used == 2


def test_passenger_ride_time_is_summed_over_both_legs(instance):
    route = Route("d", outbound=("a", "b"), inbound=("b", "a"))
    m = route_metrics(instance, route)

    # outbound: a rides 360-120=240, b rides 360-180=180
    # inbound:  b rides 180,        a rides 240
    assert m.passenger_ride_seconds == 840


def test_detour_is_zero_when_the_driver_travels_alone(instance):
    m = route_metrics(instance, Route("d"))
    assert m.detour_seconds == 0
    assert m.seats_used == 0


def test_objective_total_combines_weighted_components(instance):
    solution = Solution(routes=(Route("d", outbound=("a", "b"), inbound=("b", "a")),))
    breakdown = evaluate(instance, solution)

    assert breakdown.drive_seconds == 720
    assert breakdown.vehicles == 1
    assert breakdown.passenger_ride_seconds == 840
    assert breakdown.driver_detour_seconds == 120
    assert breakdown.unassigned_weight == 0
    # 1*720 + 600*1 + 0.5*840 + 1*120
    assert breakdown.total == 1860.0


def test_unassigned_cost_scales_with_priority(instance):
    from dataclasses import replace

    prioritized = replace(
        instance,
        participants=(
            instance.participant("d"),
            replace(instance.participant("a"), priority=3),
            instance.participant("b"),
        ),
    )
    solution = Solution(routes=(Route("d", outbound=("b",), inbound=("b",)),), unassigned=("a",))

    # 1 + priority 3
    assert evaluate(prioritized, solution).unassigned_weight == 4


def test_churn_counts_only_people_present_in_both_solutions():
    before = Solution(routes=(Route("d1", outbound=("a", "b")), Route("d2", outbound=("c",))))
    after = Solution(routes=(Route("d1", outbound=("a",)), Route("d2", outbound=("b", "z"))))

    # b moved d1 -> d2; a stayed; c left; z is new
    assert churn(before, after) == 1
