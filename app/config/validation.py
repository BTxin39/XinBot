"""Configuration validation module for checking required settings before startup."""

import os
import sys
from typing import List, Dict
from rich.console import Console
from app.llm.registry import LLMRegistry
from app.config.runtime import RuntimeConfig


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
        
        # Validate provider configuration
        registry = LLMRegistry()
        provider_config = registry.get_provider(config.PROVIDER)
        
        if not provider_config:
            errors.append(f"Invalid provider: {config.PROVIDER}")
            return errors  # Early return since provider doesn't exist
        
        # Check if the required API key is set
        api_key_value = provider_config.api_key
        if not api_key_value:
            errors.append(f"Missing API key: {provider_config.api_key_env}")
        
        # Validate base URL if required by the provider
        if provider_config.provider_type == "openai-compatible":
            base_url_value = provider_config.resolved_base_url
            if not base_url_value:
                # Some providers like OpenAI might not need explicit base_url
                # But DeepSeek requires base_url to be configured
                if "deepseek" in provider_config.name.lower():
                    errors.append(f"Missing base URL for provider {provider_config.name}: {provider_config.base_url_env}")
        
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
            if not api_key_value:
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
        ValueError: If any configuration issues are found
    """
    validator = ConfigValidator()
    errors = validator.validate_startup_config(config)
    
    if errors:
        console = Console()
        console.print("[bold red]Configuration validation failed:[/bold red]")
        for error in errors:
            console.print(f"  - {error}")
        console.print("\n[bold yellow]Please check your environment variables.[/bold yellow]")
        raise ValueError("Configuration validation failed")