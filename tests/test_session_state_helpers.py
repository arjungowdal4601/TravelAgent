from UI import session_state


def test_default_trip_data_has_no_prefilled_origin() -> None:
    trip_data = session_state._default_trip_data()

    assert trip_data["origin_state"] is None
    assert trip_data["origin_city"] is None
    assert trip_data["origin"] is None


def test_origin_selection_requires_real_state_and_city() -> None:
    assert session_state.is_complete_origin_selection("State A", "City A") is True
    assert session_state.is_complete_origin_selection(session_state.ORIGIN_STATE_PLACEHOLDER, "City A") is False
    assert session_state.is_complete_origin_selection("State A", session_state.ORIGIN_CITY_PLACEHOLDER) is False
    assert session_state.is_complete_origin_selection(None, "City A") is False
    assert session_state.is_complete_origin_selection("State A", None) is False
