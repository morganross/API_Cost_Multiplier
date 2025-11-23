import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables from the FPF .env file
env_path = os.path.join(os.path.dirname(__file__), 'FilePromptForge', '.env')
load_dotenv(env_path)

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("Error: GOOGLE_API_KEY not found in environment variables.")
    print(f"Checked path: {env_path}")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

try:
    response = requests.get(url)
    response.raise_for_status()
    
    data = response.json()
    models = data.get('models', [])
    
    print(f"Found {len(models)} models available to your API key:\n")
    
    # Sort models by name for easier reading
    models.sort(key=lambda x: x.get('name', ''))
    
    for model in models:
        name = model.get('name', '').replace('models/', '')
        display_name = model.get('displayName', 'N/A')
        version = model.get('version', 'N/A')
        print(f"- {name} ({display_name})")
        
except requests.exceptions.RequestException as e:
    print(f"Error fetching models: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response status: {e.response.status_code}")
        print(f"Response text: {e.response.text}")
