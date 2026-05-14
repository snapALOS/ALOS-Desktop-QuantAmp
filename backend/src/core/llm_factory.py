from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from .config import config, system_logger


def get_llm() -> BaseChatModel:
    """
    Constructs an enterprise-grade LangChain chat model instance based on the
    currently configured provider. Supported providers:

      - nvidia              -> ChatOpenAI pointed at NVIDIA NIM
      - openai              -> ChatOpenAI (default endpoint)
      - anthropic           -> ChatAnthropic
      - ollama              -> ChatOpenAI pointed at local Ollama OpenAI-shim
      - openai_compatible   -> ChatOpenAI pointed at user-supplied base_url
    """
    provider = config.llm_provider
    base_url = config.resolved_base_url()

    system_logger.debug(
        f"Configuring ChatModel instance -> "
        f"Provider: {provider} | Model: {config.model_name} | "
        f"BaseURL: {base_url or '<sdk-default>'} | "
        f"Retries: {config.max_retries} | Timeout: {config.timeout_seconds}s | "
        f"Temperature: {config.temperature} | TopP: {config.top_p} | "
        f"MaxOutput: {config.max_output_tokens}"
    )

    try:
        if not config.is_configured():
            raise RuntimeError(
                "ALOS is not configured. Open System Preferences and complete guided provider setup."
            )

        if provider == "anthropic":
            # Imported lazily so environments that don't need Anthropic don't pay the cost.
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model_name,
                api_key=config.api_key,
                max_retries=config.max_retries,
                timeout=config.timeout_seconds,
                temperature=config.temperature,
                top_p=config.top_p,
                top_k=config.top_k,
                max_tokens=config.max_output_tokens,
            )

        # All other providers are OpenAI-spec compatible.
        # Ollama runs without auth; pass a placeholder key since ChatOpenAI requires one.
        api_key = config.api_key or ("ollama" if provider == "ollama" else "")

        return ChatOpenAI(
            model=config.model_name,
            api_key=api_key,
            base_url=base_url,
            max_retries=config.max_retries,
            timeout=config.timeout_seconds,
            temperature=config.temperature,
            max_tokens=config.max_output_tokens,
            model_kwargs=config.openai_model_kwargs(),
        )
    except Exception as e:
        system_logger.critical(
            f"Fatal anomaly occurred during LLM bindings. Detailed exception: {str(e)}"
        )
        raise
