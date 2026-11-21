import datetime
import os
import sys

import support 

from support.sqlite_db import DbTestCase  

H = datetime.timedelta(hours=1)


def day_at(first_day, day, hour):
    return datetime.datetime.combine(first_day.replace(day=day), datetime.time(hour))
