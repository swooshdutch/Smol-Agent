# /wisper_project/llm_handler.py (MODIFIED for Google Gemini API)

import logging
from typing import Dict, Any, Optional
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LLMHandler:
    """
    A dedicated handler for interacting with the Google Gemini API.
    This class abstracts the API calls, configuration, and response parsing,
    providing a clean interface for the Chat Manager. It mimics the output
    structure of the previous local model handler to ensure compatibility.
    """
    def __init__(self, api_key: str, model_name: str = 'gemini-1.5-flash-latest'):
        self.model_name = model_name
        self.model: Optional[genai.GenerativeModel] = None
        self.api_key_is_valid = False
        self.update_api_key(api_key)

    def update_api_key(self, api_key: str):
        """
        Configures the Gemini client with a new API key and validates it.
        If the key is invalid, the handler is disabled.
        """
        logger.info("Configuring Google Gemini client with new API key.")
        if not api_key:
            self.model = None
            self.api_key_is_valid = False
            logger.warning("API key is empty. LLM handler is disabled.")
            return

        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(self.model_name)
            # Perform a lightweight test call to validate the key and model access
            self.model.count_tokens("test")
            self.api_key_is_valid = True
            logger.info("Google Gemini client configured and API key validated successfully.")
        except google_exceptions.PermissionDenied as e:
            self.model = None
            self.api_key_is_valid = False
            logger.error(f"Invalid API Key. Gemini API permission denied. Please check your key and API permissions. Details: {e}")
        except Exception as e:
            self.model = None
            self.api_key_is_valid = False
            logger.critical(f"An unexpected error occurred during Gemini client configuration: {e}", exc_info=True)

    def generate_response(self, prompt: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a response from the Gemini API and returns it in a
        structure compatible with the Chat Manager.
        """
        # Default response structure in case of failure
        default_failure_response = {"choices": [{"text": ""}], "usage": None}

        if not self.api_key_is_valid or not self.model:
            error_message = "{Terminal: generation-failed-no-valid-api-key}"
            logger.error("generate_response called but the API key is invalid or the model is not loaded.")
            return {"choices": [{"text": error_message}], "usage": None}

        # Gemini stop sequences
        stop_tokens = [
            "<|eot_id|>",
            "<|start_header_id|>",
            "{end-of-turn}",
            "{user-says"
        ]

        # Configure generation parameters for the API call
        # Note: Gemini doesn't support 'min_p' or 'repeat_penalty'
        generation_config = genai.GenerationConfig(
            temperature=params.get('temperature', 0.7),
            top_p=params.get('top_p', 0.9),
            top_k=params.get('top_k', 30),
            max_output_tokens=2048, # A reasonable limit for a single turn
            stop_sequences=stop_tokens
        )
        
        # Configure safety settings to be less restrictive
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        try:
            logger.info("Sending generation request to Gemini API...")
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # --- Reconstruct the response to match the old local model format ---
            text_response = ""
            # Check if the response was blocked or had no content
            if response.candidates and response.candidates[0].content.parts:
                text_response = response.candidates[0].content.parts[0].text
            elif response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason.name
                 logger.warning(f"Gemini API blocked the prompt. Reason: {block_reason}")
                 text_response = f"{{Terminal: generation-failed-prompt-blocked[Reason: {block_reason}]}}"
            else:
                 logger.warning("Gemini API returned an empty response.")
                 text_response = "{Terminal: generation-failed-empty-response}"

            usage_metadata = response.usage_metadata
            usage_dict = {
                "prompt_tokens": usage_metadata.prompt_token_count,
                "completion_tokens": usage_metadata.candidates_token_count,
                "total_tokens": usage_metadata.total_token_count,
            }

            return {
                "choices": [{"text": text_response}],
                "usage": usage_dict
            }

        except google_exceptions.PermissionDenied as e:
            logger.error(f"API key became invalid during generation. Disabling handler. Details: {e}")
            self.api_key_is_valid = False # Mark the key as bad
            error_message = "{Terminal: generation-failed-invalid-api-key}"
            return {"choices": [{"text": error_message}], "usage": None}
        except Exception as e:
            logger.error(f"An unexpected error occurred during Gemini API generation: {e}", exc_info=True)
            return default_failure_response