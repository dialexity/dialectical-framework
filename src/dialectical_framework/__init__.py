# -*- coding: utf-8 -*-

# Import all core Pydantic models that participate in potential circular dependencies.
# The order of imports here ensures classes are defined before their `.model_rebuild()`
# methods are called below.
from .analyst.domain.assessable_cycle import AssessableCycle
from .analyst.domain.cycle import Cycle
from .analyst.domain.rationale import Rationale
from .analyst.domain.spiral import Spiral
from .analyst.domain.transformation import Transformation
from .analyst.domain.transition import Transition
from .analyst.domain.transition_cell_to_cell import TransitionCellToCell
from .analyst.domain.transition_segment_to_segment import TransitionSegmentToSegment
from .synthesist.domain.dialectical_component import DialecticalComponent
from .protocols.assessable import Assessable
from .protocols.ratable import Ratable
from .synthesist.domain.synthesis import Synthesis
from .synthesist.domain.wheel import Wheel
from .synthesist.domain.wheel_segment import WheelSegment
from .synthesist.domain.wisdom_unit import WisdomUnit

# Explicitly call `model_rebuild()` on all models that might have forward references
# or be part of circular dependencies. This forces Pydantic to resolve their schemas
# after all classes are defined in the module.
# The order of these rebuild calls is generally from base classes to derived classes,
# or simply ensuring all interdependent models are covered.

Assessable.model_rebuild()
Ratable.model_rebuild()
DialecticalComponent.model_rebuild()
Rationale.model_rebuild()
Synthesis.model_rebuild()
Wheel.model_rebuild()
WheelSegment.model_rebuild()
Transition.model_rebuild()
TransitionCellToCell.model_rebuild()
TransitionSegmentToSegment.model_rebuild()
AssessableCycle.model_rebuild()
Cycle.model_rebuild()
Spiral.model_rebuild()
Transformation.model_rebuild()
WisdomUnit.model_rebuild()
