from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.base_wheel import BaseWheel
from dialectical_framework.synthesist.factories.wheel2_base_factory import Wheel2BaseFactory
from dialectical_framework.synthesist.strategies.wheel2_focused_conversation_strategy import \
    Wheel2FocusedConversationStrategy


class Wheel2FocusedConversationFactory(Wheel2BaseFactory[Wheel2FocusedConversationStrategy]):
    async def generate(self, input_text: str) -> BaseWheel:
        t: DialecticalComponent = await self._thesis(input_text)
        wheel = BaseWheel(t=t)
        try:
            alias_to_field = {
                field_info.alias: field_name
                for field_name, field_info in BaseWheel.__pydantic_fields__.items()
            }
            for _ in range(len(alias_to_field)-1):
                dc: DialecticalComponent = await self._find_next(wheel)
                setattr(wheel, alias_to_field.get(dc.alias, dc.alias), dc)
        except StopIteration:
            pass

        return wheel