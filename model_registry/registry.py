# API_Cost_Multiplier/model_registry/registry.py

import os
import yaml

class ModelRegistry:
    _instance = None
    _models_data = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelRegistry, cls).__new__(cls)
            cls._instance._load_models_data()
        return cls._instance

    def _load_models_data(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        models_yaml_path = os.path.join(current_dir, 'models.yaml')
        try:
            with open(models_yaml_path, 'r', encoding='utf-8') as f:
                self.__class__._models_data = yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: models.yaml not found at {models_yaml_path}")
            self.__class__._models_data = {"models": {}}
        except yaml.YAMLError as e:
            print(f"Error parsing models.yaml: {e}")
            self.__class__._models_data = {"models": {}}

    def get_model_info(self, provider: str, model_name: str):
        """
        Retrieves special information for a given model.
        """
        provider_data = self.__class__._models_data.get("models", {}).get(provider)
        if provider_data:
            return provider_data.get(model_name)
        return None

    def get_api_param_mapping(self, provider: str, model_name: str, generic_param: str):
        """
        Retrieves the provider-specific API parameter name for a generic parameter.
        """
        model_info = self.get_model_info(provider, model_name)
        if model_info and "api_params" in model_info:
            return model_info["api_params"].get(generic_param)
        return generic_param # Return generic param if no specific mapping found

# Example usage (for testing/demonstration)
if __name__ == "__main__":
    registry = ModelRegistry()

    # Get info for gpt-5-mini
    gpt_mini_info = registry.get_model_info("openai", "gpt-5-mini")
    if gpt_mini_info:
        print("GPT-5-mini Info:")
        for key, value in gpt_mini_info.items():
            print(f"  {key}: {value}")
        print(f"  Mapped max_tokens: {registry.get_api_param_mapping('openai', 'gpt-5-mini', 'max_tokens')}")
    else:
        print("GPT-5-mini info not found.")

    print("\n---")

    # Get info for gemini-2.5-flash
    gemini_info = registry.get_model_info("google", "gemini-2.5-flash")
    if gemini_info:
        print("Gemini-2.5-flash Info:")
        for key, value in gemini_info.items():
            print(f"  {key}: {value}")
        print(f"  Mapped max_tokens: {registry.get_api_param_mapping('google', 'gemini-2.5-flash', 'max_tokens')}")
    else:
        print("Gemini-2.5-flash info not found.")

    print("\n---")

    # Test a non-existent model
    non_existent_info = registry.get_model_info("openai", "non-existent-model")
    if non_existent_info:
        print("Non-existent model info found (unexpected).")
    else:
        print("Non-existent model info not found (expected).")
