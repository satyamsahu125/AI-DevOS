from enum import Enum


class ProviderType(str, Enum):
    OpenAI = "OpenAI"
    AzureOpenAI = "AzureOpenAI"
    Anthropic = "Anthropic"
