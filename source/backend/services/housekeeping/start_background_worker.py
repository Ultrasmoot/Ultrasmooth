import threading
import time
import services.housekeeping.service as _m

def start_background_worker():
    # starts one daemon thread: auto check-out every JOB_INTERVAL_SECONDS, retention hourly
    def _loop():
        last_purge = 0.0
        while True:
            try:
                due = time.monotonic() - last_purge >= _m.PURGE_EVERY_SECONDS
                closed, deleted = _m.run_once(purge=due)
                if due:
                    last_purge = time.monotonic()
                if closed or any(deleted):
                    _m.logger.info("housekeeping: %s auto check-out(s), deleted %s notification(s) and %s log row(s)",
                                closed, deleted[0], deleted[1])
            except Exception:
                _m.logger.exception("housekeeping run failed")
            time.sleep(_m.Config.JOB_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, name="vase-housekeeping", daemon=True)
    thread.start()
    return thread
