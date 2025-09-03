# Import the necessary Pydantic models
# These imports will trigger the loading of their respective modules
# and their definitions will become available for model_rebuild()
from dialectical_framework.wisdom_unit import WisdomUnit
from dialectical_framework.analyst.domain.transformation import Transformation

# Call model_rebuild() for models that might have forward references
# and are part of circular dependencies.
# This ensures Pydantic can fully resolve their schemas.
WisdomUnit.model_rebuild()
Transformation.model_rebuild()

# You can add a print statement here for debugging if needed,
# to confirm it's being executed on import.
# print("Pydantic models rebuilt for dialectical_framework package.")
