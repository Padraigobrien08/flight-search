from datetime import date

from app.models import TripRequest


def lima_trip(flex_days: int = 1) -> TripRequest:
    """Edinburgh -> Lima, home from La Paz, with a small window so exhaustive search stays cheap."""
    return TripRequest(
        origin="EDI",
        destination="LIM",
        return_from="LPB",
        depart_earliest=date(2027, 5, 22),
        depart_latest=date(2027, 5, 22 + flex_days - 1),
        return_earliest=date(2027, 6, 6),
        return_latest=date(2027, 6, 6 + flex_days - 1),
    )
