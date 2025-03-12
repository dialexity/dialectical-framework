from mirascope import prompt_template, Messages

from dialectical_framework.synthesist.base_wheel import BaseWheel
from dialectical_framework.synthesist.strategies.wheel2_base_strategy import Wheel2BaseStrategy


class Wheel2FocusedConversationStrategy(Wheel2BaseStrategy):
    def __init__(self):
        self._text = ""

    @prompt_template()
    def thesis(self, text: str) -> Messages.Type:
        self._text = text
        return super().thesis(text)

    @prompt_template()
    def find_next(self, wheel_so_far: BaseWheel) -> Messages.Type:
        if not wheel_so_far.t:
            raise ValueError("T - not found in the wheel")

        prompt_messages: list = []

        prompt_messages.extend([
            *super().thesis(self._text),
            Messages.Assistant(wheel_so_far.t.to_formatted_message("Thesis (T)"))
        ])

        prompt_messages.extend(
            super().antithesis(wheel_so_far.t),
        )
        if wheel_so_far.a:
            prompt_messages.append(
                Messages.Assistant(wheel_so_far.a.to_formatted_message("Antithesis (A)"))
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().thesis_negative_side(
                wheel_so_far.t,
                wheel_so_far.a_minus if wheel_so_far.a_minus else ""
            )
        )
        if wheel_so_far.t_minus:
            prompt_messages.append(
                Messages.Assistant(wheel_so_far.t_minus.to_formatted_message("Negative Side of Thesis (T-)"))
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().antithesis_negative_side(
                wheel_so_far.a,
                wheel_so_far.t_minus if wheel_so_far.t_minus else ""
            )
        )
        if wheel_so_far.a_minus:
            prompt_messages.extend([
                Messages.Assistant(wheel_so_far.a_minus.to_formatted_message("Negative Side of Antithesis (A-)"))
            ])
        else:
            return prompt_messages

        prompt_messages.extend(
            super().thesis_positive_side(
                wheel_so_far.t,
                wheel_so_far.a_minus
            )
        )
        if wheel_so_far.t_plus:
            prompt_messages.extend([
                Messages.Assistant(wheel_so_far.t_plus.to_formatted_message("Positive Side of Thesis (T+)"))
            ])
        else:
            return prompt_messages

        prompt_messages.extend(
            super().antithesis_positive_side(
                wheel_so_far.a,
                wheel_so_far.t_minus
            )
        )
        if wheel_so_far.a_plus:
            prompt_messages.extend([
                Messages.Assistant(wheel_so_far.a_plus.to_formatted_message("Positive Side of Antithesis (A+)"))
            ])
        else:
            return prompt_messages

        raise StopIteration("The wheel is complete, nothing to do.")