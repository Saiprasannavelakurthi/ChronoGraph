from neo4j_connection import driver, DATABASE


# --------------------------------------------------
# 1. Get all temporal events
# --------------------------------------------------
def get_all_events():

    query = """
    MATCH (a)-[r]->(b)
    WHERE r.timestamp IS NOT NULL
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        r.timestamp AS timestamp
    ORDER BY r.timestamp
    """

    with driver.session(database=DATABASE) as session:
        result = session.run(query)
        return [record.data() for record in result]


# --------------------------------------------------
# 2. Get events after a particular date
# --------------------------------------------------
def get_events_after(date):

    query = """
    MATCH (a)-[r]->(b)
    WHERE r.timestamp >= datetime($date)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        r.timestamp AS timestamp
    ORDER BY r.timestamp
    """

    with driver.session(database=DATABASE) as session:
        result = session.run(query, date=date)
        return [record.data() for record in result]


# --------------------------------------------------
# 3. Get a person's complete history (chronological order)
# --------------------------------------------------
def get_person_history(person_name):

    query = """
    MATCH (a)-[r]->(b)
    WHERE a.name = $person_name AND r.timestamp IS NOT NULL
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        r.timestamp AS timestamp
    ORDER BY r.timestamp ASC
    """

    with driver.session(database=DATABASE) as session:
        result = session.run(
            query,
            person_name=person_name
        )

        return [record.data() for record in result]


# --------------------------------------------------
# 4. Get events between two dates
# --------------------------------------------------
def get_events_between(start_date, end_date):

    query = """
    MATCH (a)-[r]->(b)
    WHERE r.timestamp >= datetime($start_date)
      AND r.timestamp <= datetime($end_date)
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        r.timestamp AS timestamp
    ORDER BY r.timestamp
    """

    with driver.session(database=DATABASE) as session:
        result = session.run(
            query,
            start_date=start_date,
            end_date=end_date
        )

        return [record.data() for record in result]


# --------------------------------------------------
# 5. Get technology history
# --------------------------------------------------
def get_technology_history(technology):

    query = """
    MATCH (a)-[r]->(b)
    WHERE b.name = $technology AND r.timestamp IS NOT NULL
    RETURN
        a.name AS subject,
        type(r) AS relationship,
        b.name AS object,
        r.timestamp AS timestamp
    ORDER BY r.timestamp
    """

    with driver.session(database=DATABASE) as session:
        result = session.run(
            query,
            technology=technology
        )

        return [record.data() for record in result]


# --------------------------------------------------
# MAIN PROGRAM
# --------------------------------------------------
if __name__ == "__main__":

    # 1. All events
    print("\n===== ALL TEMPORAL EVENTS =====")
    for event in get_all_events():
        print(event)

    # 2. Events after August 10
    print("\n===== EVENTS AFTER AUGUST 10 =====")
    for event in get_events_after("2026-08-10T00:00:00"):
        print(event)

    # 3. Rahul's chronological history
    print("\n===== RAHUL HISTORY (CHRONOLOGICAL) =====")
    for event in get_person_history("Rahul"):
        print(event)

    # 4. Events between August 10 and August 11
    print("\n===== EVENTS BETWEEN AUGUST 10 AND AUGUST 11 =====")
    for event in get_events_between(
        "2026-08-10T00:00:00",
        "2026-08-11T23:59:59"
    ):
        print(event)

    # 5. GCP history
    print("\n===== GCP HISTORY =====")
    for event in get_technology_history("GCP"):
        print(event)

    # Close connection
    driver.close()
