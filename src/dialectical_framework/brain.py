class Brain:
    def __init__(self, *, ai_model: str, ai_provider: str | None):
        if not ai_provider:
            if not "/" in ai_model:
                raise ValueError(
                    "ai_model must be in the form of 'provider/model' if ai_provider is not specified."
                )
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                self._ai_provider, self._ai_model = (
                    derived_ai_provider,
                    derived_ai_model,
                )
        else:
            if not "/" in ai_model:
                self._ai_provider, self._ai_model = ai_provider, ai_model
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                # Special case for litellm which can handle models with provider/ prefix
                if ai_provider == "litellm":
                    self._ai_provider, self._ai_model = ai_provider, ai_model
                elif derived_ai_provider != ai_provider:
                    raise ValueError(
                        f"ai_provider '{ai_provider}' does not match ai_model '{ai_model}'"
                    )
                else:
                    self._ai_provider, self._ai_model = (
                        derived_ai_provider,
                        derived_ai_model,
                    )

    def __str__(self):
        provider, model = self.specification()
        return f"Brain(provider='{provider}', model='{model}')"

    def specification(self) -> tuple[str, str]:
        return self._ai_provider, self._ai_model

    def modified_specification(
        self, *, ai_provider: str | None = None, ai_model: str | None = None
    ) -> tuple[str, str]:
        """
        This doesn't mutate the current instance.
        """
        current_provider, current_model = self.specification()

        if ai_provider == "litellm":
            if not ai_model:
                if not current_provider and not current_model:
                    raise ValueError("ai_model not provided.")
                else:
                    return ai_provider, f"{current_provider}/{current_model}"
            else:
                if not "/" in ai_model:
                    if not current_provider:
                        raise ValueError(
                            "ai_model must be in the form of 'provider/model' for litellm."
                        )
                    else:
                        return ai_provider, f"{current_provider}/{ai_model}"
                else:
                    return ai_provider, ai_model

        if not ai_provider:
            if not "/" in ai_model:
                raise ValueError(
                    "ai_model must be in the form of 'provider/model' if ai_provider is not specified."
                )
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                return derived_ai_provider, derived_ai_model
        else:
            if not "/" in ai_model:
                return ai_provider, ai_model
            else:
                derived_ai_provider, derived_ai_model = ai_model.split("/", 1)
                if derived_ai_provider != ai_provider:
                    raise ValueError(
                        f"ai_provider '{ai_provider}' does not match ai_model '{ai_model}'"
                    )
                return derived_ai_provider, derived_ai_model
