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
# MAIN PROGRAM & DEMONSTRATION
# --------------------------------------------------
def run_dataset_temporal_demo():
    """
    Executes temporal query suite against the loaded ChronoGraph dataset.
    Uses dynamic entities (arun_sharma, priya_nair, GCP, AWS) and actual 2023 date ranges.
    """
    print("\n===== 1. ALL TEMPORAL EVENTS (SAMPLE 10) =====")
    all_events = get_all_events()
    print(f"Total temporal events found: {len(all_events)}")
    for event in all_events[:10]:
        print(f"  {event.get('timestamp')} | {event.get('subject')} -[{event.get('relationship')}]-> {event.get('object')}")

    print("\n===== 2. EVENTS AFTER APRIL 1, 2023 =====")
    after_events = get_events_after("2023-04-01T00:00:00")
    print(f"Events after 2023-04-01: {len(after_events)}")
    for event in after_events[:5]:
        print(f"  {event.get('timestamp')} | {event.get('subject')} -[{event.get('relationship')}]-> {event.get('object')}")

    print("\n===== 3. ARUN SHARMA / PERSON CHRONOLOGICAL HISTORY =====")
    person_history = get_person_history("arun_sharma") or get_person_history("Arun Sharma")
    print(f"History events for Arun Sharma: {len(person_history)}")
    for event in person_history[:5]:
        print(f"  {event.get('timestamp')} | {event.get('subject')} -[{event.get('relationship')}]-> {event.get('object')}")

    print("\n===== 4. EVENTS BETWEEN MARCH 15 AND APRIL 15, 2023 =====")
    between_events = get_events_between("2023-03-15T00:00:00", "2023-04-15T23:59:59")
    print(f"Events in range: {len(between_events)}")
    for event in between_events[:5]:
        print(f"  {event.get('timestamp')} | {event.get('subject')} -[{event.get('relationship')}]-> {event.get('object')}")

    print("\n===== 5. GCP / TECHNOLOGY EVOLUTION HISTORY =====")
    tech_history = get_technology_history("gcp") or get_technology_history("GCP")
    print(f"History events for GCP: {len(tech_history)}")
    for event in tech_history[:5]:
        print(f"  {event.get('timestamp')} | {event.get('subject')} -[{event.get('relationship')}]-> {event.get('object')}")


if __name__ == "__main__":
    try:
        run_dataset_temporal_demo()
    except Exception as exc:
        print(f"Temporal queries demo skipped (Neo4j unreachable): {exc}")
    finally:
        try:
            driver.close()
        except Exception:
            pass

