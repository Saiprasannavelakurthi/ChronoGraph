import json
import dotenv
from src.pipeline import process_text

# Load environment variables from .env (containing GROQ_API_KEY)
dotenv.load_dotenv()


def main():
    enterprise_text = (
        "Karkuvel committed code changes abc1234 to the ChronoGraph repository. "
        "Aathi reviewed pull request #24 created by Karkuvel and merged it into main."
    )
    metadata = {
        "source": "github",
        "repository": "ChronoGraph",
        "timestamp": "2026-08-10T11:45:10Z"
    }

    print("Executing real Groq (Llama 3.3 70B) extraction pipeline...")
    result = process_text(enterprise_text, metadata=metadata, raise_on_validation_error=False)

    print("\n--- REAL GROQ EXTRACTION OUTPUT ---")
    print(json.dumps(result, indent=2))

    # Basic assertions for verification
    has_entities = len(result.get("entities", [])) > 0
    has_relationships = len(result.get("relationships", [])) > 0
    has_triples = len(result.get("triples", [])) > 0
    is_valid = result.get("is_valid") is True

    print("\n--- REAL EXTRACTION VERIFICATION CHECKS ---")
    print(f"Entities Extracted ({len(result.get('entities', []))}): {has_entities}")
    print(f"Relationships Extracted ({len(result.get('relationships', []))}): {has_relationships}")
    print(f"Triples Extracted ({len(result.get('triples', []))}): {has_triples}")
    print(f"Validation is_valid == True: {is_valid}")


if __name__ == "__main__":
    main()
