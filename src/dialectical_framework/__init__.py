# -*- coding: utf-8 -*-

# Import all core Pydantic models that participate in potential circular dependencies.
# The order of imports here ensures classes are defined before their `.model_rebuild()`
# methods are called below.
from dialectical_framework.domain.assessable_cycle import AssessableCycle
from dialectical_framework.domain.cycle import Cycle
from dialectical_framework.domain.rationale import Rationale
from dialectical_framework.domain.spiral import Spiral
from dialectical_framework.domain.transformation import Transformation
from dialectical_framework.domain.transition import Transition
from dialectical_framework.domain.transition_cell_to_cell import TransitionCellToCell
from dialectical_framework.domain.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.domain.dialectical_component import DialecticalComponent
from dialectical_framework.domain.assessable import Assessable
from dialectical_framework.domain.ratable import Ratable
from dialectical_framework.domain.synthesis import Synthesis
from dialectical_framework.domain.wheel import Wheel
from dialectical_framework.domain.wheel_segment import WheelSegment
from dialectical_framework.domain.wisdom_unit import WisdomUnit

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
