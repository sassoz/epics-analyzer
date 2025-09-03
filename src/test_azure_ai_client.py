
import os
import sys

# Add the parent directory (project root) to the search path...
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from utils.azure_ai_client import AzureAIClient

def main():
    """
    Main function to test the AzureAIClient.
    """
    print("--- Starting AzureAIClient Test ---")
    try:
        # Initialize the client
        client = AzureAIClient()

        # Test a completion
        model_to_test = "gpt-4.1-mini"
        print(f"\n--- Testing model: {model_to_test} ---")
        response = client.completion(
            model_name=model_to_test,
            user_prompt="Hello, this is a test. Are you receiving me?",
            max_tokens=100
        )
        print("Response received:")
        print(response)

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("\n--- Test Finished ---")

if __name__ == "__main__":
    main()
