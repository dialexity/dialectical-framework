from typing import List

from pydantic import BaseModel, ConfigDict

from dialectical_framework.wisdom_unit import WisdomUnit


class DialecticalAnalysis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    # TODO: This should rather be documents, references, images, texts...
    corpus: str = None
    perspectives: List[WisdomUnit] = []
