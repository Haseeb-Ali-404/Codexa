import os
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Gemini client
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

def list_gemini_models():
    print("🔍 Available Gemini Models:\n")

    models = client.models.list()

    for model in models:
        print(f"Model Name: {model.name}")

        # Optional: show supported generation methods
        if hasattr(model, "supported_generation_methods"):
            print("  Supported methods:", model.supported_generation_methods)

        print("-" * 50)


if __name__ == "__main__":
    list_gemini_models()
