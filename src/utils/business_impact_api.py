"""
Business Impact API Module (Pydantic Version)
==============================================

This module provides an AI-powered capability to analyze a given text description,
separate the core narrative from business value information, and structure that
business value data into a predefined schema.

AI-powered Separation with Pydantic
-----------------------------------
The module defines a strict data model using Pydantic classes. This model is
passed directly to the AI using the 'instructor' library, which forces the AI's
JSON output to conform to the required schema. This proactive approach minimizes
validation errors, reduces hallucinations, and ensures type safety.

Key Components
--------------
- **Pydantic Models**: `BusinessImpact`, `StrategicEnablement`, `TimeCriticality`,
  and `BusinessValue` define the nested structure for the extracted data. `AIResponse`
  is the top-level model the AI is instructed to populate.
- **process_description()**: The primary function that takes raw text, communicates
  with the AI, and returns the separated, structured data.
- **get_empty_business_value_dict()**: A helper function to generate a default
  empty result, used when input is empty or in case of an error.

The data model is defined by the following Pydantic classes:
- AIResponse
  - cleaned_description: str
  - business_value: BusinessValue
    - business_impact: BusinessImpact
    - strategic_enablement: StrategicEnablement
    - time_criticality: TimeCriticality
"""

import os
import json
from pydantic import BaseModel, Field
from typing import Optional

from utils.azure_ai_client import AzureAIClient
from utils.prompt_loader import load_prompt_template
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv())

class BusinessImpact(BaseModel):
    """Data model for the financial and operational impact of a task."""
    scale: int = Field(..., description="The overall impact scale (0-5).")
    revenue: Optional[str] = Field("", description="Details on revenue generation.")
    cost_saving: Optional[str] = Field("", description="Details on cost savings.")
    risk_loss: Optional[str] = Field("", description="Details on mitigating financial risks or losses.")
    justification: Optional[str] = Field("", description="A narrative explaining the business impact.")

class StrategicEnablement(BaseModel):
    """Data model for the strategic value and alignment of a task."""
    scale: int = Field(..., description="The overall strategic importance scale (0-5).")
    risk_minimization: Optional[str] = Field("", description="Details on minimizing non-financial risks.")
    strat_enablement: Optional[str] = Field("", description="Details on how this enables strategic initiatives.")
    justification: Optional[str] = Field("", description="A narrative explaining the strategic value.")

class TimeCriticality(BaseModel):
    """Data model for the urgency and time-based factors of a task."""
    scale: int = Field(..., description="The overall time criticality scale (0-5).")
    time: Optional[str] = Field("", description="The frequency or time horizon (e.g., 'Daily', 'Q3 2025').")
    justification: Optional[str] = Field("", description="A narrative explaining why this is time-critical.")

class BusinessValue(BaseModel):
    """A container for all business value dimensions."""
    business_impact: BusinessImpact
    strategic_enablement: StrategicEnablement
    time_criticality: TimeCriticality

class AIResponse(BaseModel):
    """The top-level Pydantic model that the AI is instructed to populate."""
    cleaned_description: str = Field(..., description="The description text, cleaned of any business value information.")
    business_value: BusinessValue


def get_empty_business_value_dict() -> dict:
    """
    Returns a default empty business value structure as a dictionary.

    This is used as a fallback for empty inputs or processing errors.

    Returns:
        dict: A dictionary representing an empty BusinessValue object.
    """
    # Erstellt eine leere Instanz des Pydantic-Modells und wandelt sie in ein dict um
    # (Creates an empty instance of the Pydantic model and converts it to a dict)
    empty_bv = BusinessValue(
        business_impact=BusinessImpact(scale=0),
        strategic_enablement=StrategicEnablement(scale=0),
        time_criticality=TimeCriticality(scale=0)
    )
    return empty_bv.model_dump()

def process_description(description_text: str, model: str, token_tracker, azure_client: AzureAIClient) -> dict:
    """
    Analyzes a description using the native Azure OpenAI structured output (Pydantic).
    """
    if not description_text:
        return {"description": "", "business_value": get_empty_business_value_dict()}

    prompt_template = load_prompt_template("business_impact_prompt.yaml", "user_prompt_template")
    prompt = prompt_template.format(description_text=description_text)

    try:
        # NEUER, NATIVER AUFRUF mit .parse()
        completion = azure_client.openai_client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": "Extract the event information from the user's description and separate it from the core text."},
                {"role": "user", "content": prompt}
            ],
            response_format=AIResponse, # Direkt die Pydantic-Klasse übergeben
        )

        # Das Ergebnis ist bereits ein Pydantic-Objekt
        ai_response_object = completion.choices[0].message.parsed

        # Token-Erfassung funktioniert weiterhin
        if token_tracker and hasattr(completion, 'usage') and completion.usage:
             usage = completion.usage
             token_tracker.log_usage(
                model=model,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                task_name="business_impact",
            )

        return {
            "description": ai_response_object.cleaned_description.strip(),
            "business_value": ai_response_object.business_value.model_dump(),
        }

    except Exception as e:
        # Das Error-Handling bleibt identisch
        print(f"Error creating Pydantic object from AI response: {e}. Returning original description and empty business value.")
        return {
            "description": description_text.strip(),
            "business_value": get_empty_business_value_dict(),
        }
