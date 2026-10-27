"""Configuration validation module for checking required settings before startup.

本模块属于 `config/` 层，**不得依赖渲染库**（见 docs/DECISIONS/DECISIONS_V0.2.0.md §8 R4）。
原先它在模块导入期 `from rich.console import Console`，导致任何经过
`Agent → validate_config` 的调用链都被迫加载 rich——Web 端复用命令层时即被这一点挡住。
现在校验只返回/抛出错误列表，打印交给各适配器。
"""

import os
from typing import Dict, List

from app.llm.registry import LLMRegistry
from app.config.runtime import RuntimeConfig


class ConfigValidationError(ValueError):
    """配置校验失败。

    继承 `ValueError` 以兼容既有调用方（它们原本 catch ValueError）。
    `errors` 保留全部具体原因，供适配器展示——历史实现把明细 print 到终端后
    只抛一句 "Configuration validation failed"，调用方 catch 后无法得知原因。
    """

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("Configuration validation failed: " + "; ".join(self.errors))


class ConfigValidator:
    """Validates configuration settings before application startup."""
    
    @staticmethod
    def validate_startup_config(config: RuntimeConfig) -> List[str]:
        """
        Validates all required configuration settings before startup.
        
        Args:
            config: RuntimeConfig instance to validate
            
        Returns:
            List of error messages for missing or invalid configurations
        """
        errors = []
        
        # Validate provider exists
        registry = LLMRegistry()
        provider_config = registry.get_provider(config.provider)
        
        if not provider_config:
            errors.append(f"Provider does not exist: {config.provider}")
            return errors  # Early return since provider doesn't exist
        
        # Check if the required API key is set
        api_key_value = provider_config.api_key
        if not api_key_value and provider_config.provider_type != "ollama":
            errors.append(f"Missing API key: {provider_config.api_key_env}")
        
        # Validate base URL if required by the provider
        if provider_config.provider_type == "openai-compatible":
            base_url_value = provider_config.resolved_base_url
            if not base_url_value:
                # Some providers like OpenAI might not need explicit base_url
                # But DeepSeek requires base_url to be configured
                if "deepseek" in provider_config.name.lower():
                    errors.append(f"Missing base URL for provider {provider_config.name}: {provider_config.base_url_env}")
        
        # Validate that the model belongs to the provider
        model_config = registry.get_model(config.model_name)
        if not model_config:
            errors.append(f"Model does not exist: {config.model_name}")
        elif model_config.provider != config.provider:
            errors.append(f"Model '{config.model_name}' does not belong to provider '{config.provider}'. "
                         f"The model belongs to provider '{model_config.provider}'")
        
        return errors
    
    @staticmethod
    def validate_all_providers() -> Dict[str, List[str]]:
        """
        Validates all registered providers in the registry.
        
        Returns:
            Dictionary mapping provider names to lists of validation errors
        """
        registry = LLMRegistry()
        provider_errors = {}
        
        for provider in registry.list_providers():
            errors = []
            
            # Check if API key is set
            api_key_value = provider.api_key
            if not api_key_value and provider.provider_type != "ollama":
                errors.append(f"Missing API key: {provider.api_key_env}")
            
            # Check base URL if applicable
            if provider.provider_type == "openai-compatible":
                base_url_value = provider.resolved_base_url
                if not base_url_value and "deepseek" in provider.name.lower():
                    errors.append(f"Missing base URL: {provider.base_url_env or 'base_url'}")
            
            if errors:
                provider_errors[provider.name] = errors
                
        return provider_errors

    @staticmethod
    def check_environment_variable(var_name: str) -> bool:
        """Check if an environment variable is set and not empty."""
        value = os.getenv(var_name)
        return value is not None and value.strip() != ""


def validate_config(config: RuntimeConfig) -> None:
    """
    Validates the given configuration and raises an exception if any issues are found.

    Args:
        config: RuntimeConfig instance to validate
    Raises:
        ConfigValidationError: 携带全部具体原因（`.errors`）
    """
    errors = ConfigValidator.validate_startup_config(config)
    if errors:
        raise ConfigValidationError(errors)
