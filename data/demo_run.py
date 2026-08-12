import json
from unittest.mock import MagicMock
from src.pipeline import process_text
from src.extractor import GraphExtractor
from src.validator import validate_extraction, ExtractionValidationError


def run_demo():
    print("=" * 60)
    print("DEMO: ENTERPRISE GRAPH EXTRACTION (SLACK, GITHUB, JIRA)")
    print("=" * 60)

    # 1. Sample Enterprise Inputs (Slack, GitHub, Jira)
    slack_input = {
        "text": "Aathi asked Karkuvel about the ChronoGraph ingestion pipeline.",
        "metadata": {
            "source": "slack",
            "channel": "#dev-chat",
            "timestamp": "2026-08-10T10:15:30Z"
        }
    }

    github_input = {
        "text": "Karkuvel committed changes abc1234 to the data-ingestion branch and opened pull request #24.",
        "metadata": {
            "source": "github",
            "repository": "ChronoGraph",
            "timestamp": "2026-08-10T11:45:10Z"
        }
    }

    jira_input = {
        "text": "Aathi was assigned the graph extraction task CG-102 for the ChronoGraph project.",
        "metadata": {
            "source": "jira",
            "project": "CG",
            "timestamp": "2026-08-10T14:20:00Z"
        }
    }

    # Setup mock extractor to simulate LLM responses for demo
    def create_mock_extractor(mock_json):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = MagicMock(text=json.dumps(mock_json))
        return GraphExtractor(llm=mock_llm)

    # Execution 1: Slack Data
    slack_json = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "MENTIONED", "target": "Karkuvel"},
            {"source": "Karkuvel", "relation": "WORKED_ON", "target": "ChronoGraph"}
        ],
        "triples": []
    }
    extractor_slack = create_mock_extractor(slack_json)
    res_slack = process_text(slack_input["text"], metadata=slack_input["metadata"], extractor=extractor_slack)
    print("\n--- 1. SLACK EXTRACTION RESULT ---")
    print(json.dumps(res_slack, indent=2))

    # Execution 2: GitHub Data
    github_json = {
        "entities": [
            {"id": "person_karkuvel", "name": "Karkuvel", "type": "PERSON"},
            {"id": "commit_abc1234", "name": "abc1234", "type": "COMMIT"},
            {"id": "pull_request_24", "name": "#24", "type": "PULL_REQUEST"}
        ],
        "relationships": [
            {"source": "Karkuvel", "relation": "COMMITTED", "target": "abc1234"},
            {"source": "Karkuvel", "relation": "OPENED", "target": "#24"}
        ],
        "triples": []
    }
    extractor_github = create_mock_extractor(github_json)
    res_github = process_text(github_input["text"], metadata=github_input["metadata"], extractor=extractor_github)
    print("\n--- 2. GITHUB EXTRACTION RESULT ---")
    print(json.dumps(res_github, indent=2))

    # Execution 3: Jira Data
    jira_json = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"},
            {"id": "issue_cg_102", "name": "CG-102", "type": "ISSUE"},
            {"id": "project_chronograph", "name": "ChronoGraph", "type": "PROJECT"}
        ],
        "relationships": [
            {"source": "Aathi", "relation": "ASSIGNED_TO", "target": "CG-102"},
            {"source": "CG-102", "relation": "PART_OF", "target": "ChronoGraph"}
        ],
        "triples": []
    }
    extractor_jira = create_mock_extractor(jira_json)
    res_jira = process_text(jira_input["text"], metadata=jira_input["metadata"], extractor=extractor_jira)
    print("\n--- 3. JIRA EXTRACTION RESULT ---")
    print(json.dumps(res_jira, indent=2))

    # 4. Check Invalid/Dangling Reference Rejection
    print("\n--- 4. DANGLING REFERENCE VALIDATION CHECK ---")
    invalid_json = {
        "entities": [
            {"id": "person_aathi", "name": "Aathi", "type": "PERSON"}
        ],
        "relationships": [
            # 'NonExistentSystem' is NOT in entities -> DANGLING REFERENCE!
            {"source": "Aathi", "relation": "COMMITTED", "target": "NonExistentSystem"}
        ],
        "triples": []
    }
    extractor_invalid = create_mock_extractor(invalid_json)
    try:
        process_text("Aathi committed to NonExistentSystem", extractor=extractor_invalid, raise_on_validation_error=True)
        print("FAIL: Expected ExtractionValidationError was not raised.")
    except ExtractionValidationError as err:
        print("SUCCESS: Dangling reference correctly rejected with ExtractionValidationError!")
        print(f"Validation Error Message: {err}")
        print(f"Detailed Validation Errors: {err.errors}")

    # 5. Check Payload without raising exception
    res_invalid_payload = process_text("Aathi committed to NonExistentSystem", extractor=extractor_invalid, raise_on_validation_error=False)
    print("\nPayload when raise_on_validation_error=False:")
    print(f"is_valid: {res_invalid_payload.get('is_valid')}")
    print(f"validation_errors: {res_invalid_payload.get('validation_errors')}")


if __name__ == "__main__":
    run_demo()
