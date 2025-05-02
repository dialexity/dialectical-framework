from mirascope import prompt_template, Messages

from dialectical_framework.synthesist.wheel2 import Wheel2
from dialectical_framework.synthesist.strategies.wheel2_base_strategy import Wheel2BaseStrategy


class Wheel2ConversationStrategy(Wheel2BaseStrategy):
    @prompt_template()
    def next_missing_component(self, wheel_so_far: Wheel2) -> Messages.Type:
        if not wheel_so_far.t:
            raise ValueError("T - not found in the wheel")

        prompt_messages: list = []

        prompt_messages.extend([
            *super().thesis(self.text),
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