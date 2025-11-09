from datetime import datetime, timedelta

from adoif.services.schedule import NewScheduleItem, ScheduleService
from adoif.settings import Settings


def test_schedule_service_adds_and_queries(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    service = ScheduleService(settings)

    today = datetime.utcnow()
    items = [
        NewScheduleItem(title="Week 1", due_date=today, doi="10.1/foo"),
        NewScheduleItem(title="Week 2", due_date=today + timedelta(days=3)),
    ]
    count = service.add_items("PSY305", items)
    assert count == 2

    upcoming = service.due_between(today.date(), (today + timedelta(days=5)).date())
    assert len(upcoming) == 2
    assert upcoming[0].course == "PSY305"
