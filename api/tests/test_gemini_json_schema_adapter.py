from unittest.mock import patch

from google.genai.types import GenerateContentConfig, LiveConnectConfig
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.adapters.services.gemini_live_adapter import GeminiLiveLLMAdapter

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.gemini_json_schema_adapter import (
    SocialCangarooGeminiJSONSchemaAdapter,
    SocialCangarooGeminiLiveJSONSchemaAdapter,
)
from api.services.pipecat.realtime.gemini_live import SocialCangarooGeminiLiveLLMService
from api.services.pipecat.realtime.gemini_live_vertex import (
    SocialCangarooGeminiLiveVertexLLMService,
)
from api.services.pipecat.service_factory import (
    SocialCangarooGoogleLLMService,
    SocialCangarooGoogleVertexLLMService,
    create_llm_service_from_provider,
)


def test_gemini_tools_use_json_schema_parameters_for_external_schemas():
    function_schema = FunctionSchema(
        name="customer_lookup",
        description="Look up a customer by email.",
        properties={
            "customerEmail": {
                "description": "Customer email address",
                "anyOf": [
                    {"anyOf": [{"not": {}}]},
                    {"const": ""},
                ],
            },
            "metadata": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
        required=["customerEmail"],
    )

    tools = SocialCangarooGeminiJSONSchemaAdapter().to_provider_tools_format(
        ToolsSchema(standard_tools=[function_schema])
    )

    declaration = tools[0]["function_declarations"][0]
    assert "parameters" not in declaration
    assert (
        declaration["parameters_json_schema"]["properties"]["customerEmail"]["anyOf"][
            0
        ]["anyOf"][0]["not"]
        == {}
    )
    assert (
        declaration["parameters_json_schema"]["properties"]["customerEmail"]["anyOf"][
            1
        ]["const"]
        == ""
    )
    assert declaration["parameters_json_schema"]["properties"]["metadata"][
        "additionalProperties"
    ] == {"type": "string"}

    GenerateContentConfig(tools=tools)


def test_gemini_tools_use_json_schema_parameters_for_no_argument_tools():
    function_schema = FunctionSchema(
        name="refresh_context",
        description="Refresh the current context.",
        properties={},
        required=[],
    )

    tools = SocialCangarooGeminiJSONSchemaAdapter().to_provider_tools_format(
        ToolsSchema(standard_tools=[function_schema])
    )

    declaration = tools[0]["function_declarations"][0]
    assert "parameters" not in declaration
    assert declaration["parameters_json_schema"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }

    GenerateContentConfig(tools=tools)


def test_google_service_classes_use_social_cangaroo_gemini_adapter_class():
    assert SocialCangarooGoogleLLMService.adapter_class is SocialCangarooGeminiJSONSchemaAdapter
    assert SocialCangarooGoogleVertexLLMService.adapter_class is SocialCangarooGeminiJSONSchemaAdapter


def test_google_llm_service_factory_uses_social_cangaroo_service_class():
    with patch(
        "api.services.pipecat.service_factory.SocialCangarooGoogleLLMService",
    ) as mock_service:
        result = create_llm_service_from_provider(
            provider=ServiceProviders.GOOGLE.value,
            model="gemini-3.5-flash",
            api_key="test-api-key",
        )

    assert result is mock_service.return_value
    assert mock_service.call_args.kwargs["api_key"] == "test-api-key"
    assert mock_service.call_args.kwargs["settings"].model == "gemini-3.5-flash"


def test_google_vertex_llm_service_factory_uses_social_cangaroo_service_class():
    with patch(
        "api.services.pipecat.service_factory.SocialCangarooGoogleVertexLLMService",
    ) as mock_service:
        result = create_llm_service_from_provider(
            provider=ServiceProviders.GOOGLE_VERTEX.value,
            model="gemini-2.5-pro",
            api_key=None,
            project_id="demo-project",
            location="us-central1",
            credentials='{"type":"service_account"}',
        )

    assert result is mock_service.return_value
    assert mock_service.call_args.kwargs["project_id"] == "demo-project"
    assert mock_service.call_args.kwargs["location"] == "us-central1"
    assert mock_service.call_args.kwargs["settings"].model == "gemini-2.5-pro"


def test_gemini_live_service_classes_use_social_cangaroo_gemini_adapter_class():
    assert SocialCangarooGeminiLiveLLMService.adapter_class is SocialCangarooGeminiLiveJSONSchemaAdapter
    # Vertex Live inherits adapter_class from SocialCangarooGeminiLiveLLMService via MRO.
    assert (
        SocialCangarooGeminiLiveVertexLLMService.adapter_class
        is SocialCangarooGeminiLiveJSONSchemaAdapter
    )
    # The Live adapter must keep upstream's tool-call-to-text conversion for
    # seeded contexts (GeminiLiveLLMAdapter) alongside the JSON Schema fix.
    assert issubclass(SocialCangarooGeminiLiveJSONSchemaAdapter, GeminiLiveLLMAdapter)
    assert issubclass(SocialCangarooGeminiLiveJSONSchemaAdapter, SocialCangarooGeminiJSONSchemaAdapter)
    assert (
        SocialCangarooGeminiLiveJSONSchemaAdapter.to_provider_tools_format
        is SocialCangarooGeminiJSONSchemaAdapter.to_provider_tools_format
    )


def test_vertex_live_inherits_social_cangaroo_node_transition_lifecycle():
    assert (
        SocialCangarooGeminiLiveVertexLLMService._requires_node_transition_context_aggregation
        is SocialCangarooGeminiLiveLLMService._requires_node_transition_context_aggregation
    )
    assert (
        SocialCangarooGeminiLiveVertexLLMService._run_or_defer_function_calls
        is SocialCangarooGeminiLiveLLMService._run_or_defer_function_calls
    )
    assert (
        SocialCangarooGeminiLiveVertexLLMService._reconnect_for_node_transition
        is SocialCangarooGeminiLiveLLMService._reconnect_for_node_transition
    )


def test_gemini_live_config_accepts_json_schema_tools():
    function_schema = FunctionSchema(
        name="customer_lookup",
        description="Look up a customer by email.",
        properties={
            "customerEmail": {
                "description": "Customer email address",
                "anyOf": [{"not": {}}, {"const": ""}],
            },
        },
        required=["customerEmail"],
    )

    tools = SocialCangarooGeminiJSONSchemaAdapter().to_provider_tools_format(
        ToolsSchema(standard_tools=[function_schema])
    )

    declaration = tools[0]["function_declarations"][0]
    assert "parameters" not in declaration
    assert "parameters_json_schema" in declaration

    # Gemini Live validates tools through LiveConnectConfig rather than
    # GenerateContentConfig; it must also accept the raw JSON Schema payload.
    LiveConnectConfig(tools=tools)
