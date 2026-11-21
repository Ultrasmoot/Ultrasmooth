import services.events.service as _m

def checkout_auto(conn, booking_id):
    """The booking ended and nobody checked out: the system did it, so the resource is free again."""
    b = _m._booking(conn, booking_id)
    if not b:
        return
    _m.log(conn, b["requester_id"], "checkout.auto",
        f"{b['resource_name']} (booking ended {_m._when(b['end_time'])} without check-out)",
        b["resource_id"], "booking", booking_id)
    _m.notify(conn, [b["requester_id"]], "checkout.auto", "You were checked out automatically",
           f"{b['resource_name']}: your booking ended at {b['end_time']:%H:%M}, so it was checked out for you.",
           "checkin")

# ---------------------- maintenance ----------------------
def maintenance_reported(conn, record_id):
    m = _m._issue(conn, record_id)
    if not m:
        return
    confirmed = m["status"] != "Reported"
    _m.log(conn, m["reported_by"], "maintenance.reported",
        f"{m['resource_name']}: {m['description']}" + (" (confirmed)" if confirmed else ""),
        m["resource_id"], "maintenance", record_id)
    if confirmed:   # an admin's own report puts the resource into Maintenance straight away
        _m._tell_bookers(conn, m, m["reported_by"])
    else:
        reporter = _m._one(conn, "SELECT full_name FROM users WHERE id = %s", (m["reported_by"],))
        _m.notify(conn, _m._user_ids(conn, ["admin"]), "maintenance.reported", "New issue report",
               f"{(reporter or {}).get('full_name') or 'Someone'} reported {m['resource_name']}: {m['description']}",
               "maintenance", exclude_id=m["reported_by"])

def _tell_bookers(conn, m, actor_id):
    _m.notify(conn, _m._people_booked_on(conn, m["resource_id"]), "maintenance.affects_booking",
           "A resource you booked is under maintenance",
           f"{m['resource_name']} is now in Maintenance. Check your booking.", "bookings",
           exclude_id=actor_id)

def maintenance_confirmed(conn, record_id, admin_id):
    m = _m._issue(conn, record_id)
    if not m:
        return
    _m.log(conn, admin_id, "maintenance.confirmed", f"{m['resource_name']}: {m['description']}",
        m["resource_id"], "maintenance", record_id)
    _m.notify(conn, [m["reported_by"]], "maintenance.status", "Issue confirmed",
           f"Your report on {m['resource_name']} was confirmed.", "maintenance", exclude_id=admin_id)
    _m._tell_bookers(conn, m, admin_id)

def maintenance_dismissed(conn, record_id, admin_id):
    m = _m._issue(conn, record_id)
    if not m:
        return
    reason = m.get("dismiss_reason")
    _m.log(conn, admin_id, "maintenance.dismissed",
        f"{m['resource_name']}: {m['description']}" + (f' - "{reason}"' if reason else ""),
        m["resource_id"], "maintenance", record_id)
    _m.notify(conn, [m["reported_by"]], "maintenance.status", "Issue report dismissed",
           f"{m['resource_name']}" + (f': "{reason}"' if reason else ""), "maintenance", exclude_id=admin_id)

def maintenance_updated(conn, record_id, admin_id):
    m = _m._issue(conn, record_id)
    if m:
        _m.log(conn, admin_id, "maintenance.updated", f"{m['resource_name']}: {m['description']} ({m['status']})",
            m["resource_id"], "maintenance", record_id)

def maintenance_resolved(conn, record_id, admin_id):
    m = _m._issue(conn, record_id)
    if not m:
        return
    _m.log(conn, admin_id, "maintenance.resolved", f"{m['resource_name']}: {m['description']}",
        m["resource_id"], "maintenance", record_id)
    _m.notify(conn, [m["reported_by"]], "maintenance.status", "Issue resolved",
           f"{m['resource_name']}: {m['description']}", "maintenance", exclude_id=admin_id)

def maintenance_released(conn, resource_id, admin_id, closed):
    r = _m._one(conn, "SELECT name FROM resources WHERE id = %s", (resource_id,))
    _m.log(conn, admin_id, "maintenance.released",
        f"{(r or {}).get('name', 'Resource')} returned to Available ({closed} open issue{'s' if closed != 1 else ''} closed)",
        resource_id, "resource", resource_id)

# ---------------------- resources / announcements / auth ----------------------
def resource_changed(conn, action, resource_id, actor_id):
    """action: resource.created / updated / archived / unarchived"""
    r = _m._one(conn, "SELECT name, resource_code FROM resources WHERE id = %s", (resource_id,))
    if r:
        _m.log(conn, actor_id, action, f"{r['name']} ({r['resource_code']})", resource_id, "resource", resource_id)
