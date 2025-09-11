from mirascope import Messages, prompt_template

from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class ReasonConversational(PolarityReasoner):
    @prompt_template()
    def prompt_next(self, wu_so_far: WisdomUnit) -> Messages.Type:
        if not wu_so_far.t:
            raise ValueError("T - not found in the wheel")

        prompt_messages: list = []

        prompt_messages.extend(
            [
                *super().prompt_thesis(None),
                Messages.Assistant(wu_so_far.t.pretty("Thesis (T)")),
            ]
        )

        prompt_messages.extend(
            super().prompt_antithesis(wu_so_far.t),
        )
        if wu_so_far.a:
            prompt_messages.append(
                Messages.Assistant(wu_so_far.a.pretty("Antithesis (A)"))
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().prompt_thesis_negative_side(
                wu_so_far.t, wu_so_far.a_minus if wu_so_far.a_minus else ""
            )
        )
        if wu_so_far.t_minus:
            prompt_messages.append(
                Messages.Assistant(
                    wu_so_far.t_minus.pretty("Negative Side of Thesis (T-)")
                )
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().prompt_antithesis_negative_side(
                wu_so_far.a, wu_so_far.t_minus if wu_so_far.t_minus else ""
            )
        )
        if wu_so_far.a_minus:
            prompt_messages.extend(
                [
                    Messages.Assistant(
                        wu_so_far.a_minus.pretty("Negative Side of Antithesis (A-)")
                    )
                ]
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().prompt_thesis_positive_side(wu_so_far.t, wu_so_far.a_minus)
        )
        if wu_so_far.t_plus:
            prompt_messages.extend(
                [
                    Messages.Assistant(
                        wu_so_far.t_plus.pretty("Positive Side of Thesis (T+)")
                    )
                ]
            )
        else:
            return prompt_messages

        prompt_messages.extend(
            super().prompt_antithesis_positive_side(wu_so_far.a, wu_so_far.t_minus)
        )
        if wu_so_far.a_plus:
            prompt_messages.extend(
                [
                    Messages.Assistant(
                        wu_so_far.a_plus.pretty("Positive Side of Antithesis (A+)")
                    )
                ]
            )
        else:
            return prompt_messages

        raise StopIteration("The wheel is complete, nothing to do.")
