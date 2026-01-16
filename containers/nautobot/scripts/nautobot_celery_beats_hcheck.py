import os
from datetime import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from celery import current_app
from celery.beat import Service

os.chdir("/opt/nautobot")

schedule = Service(current_app).get_scheduler().get_schedule()

now = datetime.now(tz=ZoneInfo("UTC"))
for task_name, task in schedule.items():
    # Check if any of the tasks are overdue
    try:
        assert now < task.last_run_at + task.schedule.run_every
    except AttributeError:
        assert timedelta() < task.schedule.remaining_estimate(task.last_run_at)
