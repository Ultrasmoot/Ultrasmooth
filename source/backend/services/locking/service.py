BOOKING_FOR_UPDATE = "SELECT * FROM bookings WHERE id = %s FOR UPDATE"


def lock_resource(cur, resource_id, columns="id, status"):
    cur.execute(f"SELECT {columns} FROM resources WHERE id = %s FOR UPDATE", (resource_id,))
    return cur.fetchone()


def lock_resource_then_booking(cur, resource_id, booking_id, resource_columns="id, status",
                               booking_sql=BOOKING_FOR_UPDATE):
    resource = lock_resource(cur, resource_id, resource_columns)
    cur.execute(booking_sql, (booking_id,))
    return resource, cur.fetchone()
