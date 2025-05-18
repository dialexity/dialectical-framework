from dialectical_framework.utils.config import Config


class Brain:
    def __init__(self, *,
        ai_model: str = Config.MODEL,
        ai_provider: str | None = Config.PROVIDER):
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
                if derived_ai_provider != ai_provider:
                    raise ValueError(
                        f"ai_provider '{ai_provider}' does not match ai_model '{ai_model}'"
                    )
                self._ai_provider, self._ai_model = (
                    derived_ai_provider,
                    derived_ai_model,
                )

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

        if not ai_model and not ai_provider:
            if Config.PROVIDER or Config.MODEL or current_provider or current_model:
                return self.modified_specification(
                    ai_provider=Config.PROVIDER if not current_provider else current_provider,
                    ai_model=Config.MODEL if not current_model else current_model,
                )
            else:
                raise ValueError(
                    "Cannot fallback to default model as they're not present"
                )

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