# check in check out history
import datetime
import os
import sys

import support  # noqa: F401,E402  
from support.sqlite_db import DbTestCase  # noqa: E402

H = datetime.timedelta(hours=1)


def ago(hours):
    return (datetime.datetime.now() - hours * H).replace(microsecond=0)
