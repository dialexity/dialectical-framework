from mirascope import Messages, prompt_template

from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class ReasonBlind(PolarityReasoner):
    @prompt_template()
    def prompt_next(self, wu_so_far: WisdomUnit) -> Messages.Type:
        """
        Raises:
            ValueError: If the wisdom unit is incorrect.
            StopIteration: If the wisdom unit is complete already.
        """
        if not wu_so_far.t:
            raise ValueError("T - not present")

        prompt_messages = []

        if not wu_so_far.a:
            prompt_messages.extend(
                self.prompt_antithesis(wu_so_far.t),
            )
            return prompt_messages

        if not wu_so_far.t_minus:
            prompt_messages.extend(
                self.prompt_thesis_negative_side(
                    wu_so_far.t, wu_so_far.a_minus if wu_so_far.a_minus else ""
                )
            )
            return prompt_messages

        if not wu_so_far.a:
            raise ValueError("A - not present")

        if not wu_so_far.a_minus:
            prompt_messages.extend(
                self.prompt_antithesis_negative_side(
                    wu_so_far.a, wu_so_far.t_minus if wu_so_far.t_minus else ""
                )
            )
            return prompt_messages

        if not wu_so_far.a_minus:
            raise ValueError("A- - not present")
        if not wu_so_far.t_plus:
            prompt_messages.extend(
                self.prompt_thesis_positive_side(wu_so_far.t, wu_so_far.a_minus)
            )
            return prompt_messages

        if not wu_so_far.t_minus:
            raise ValueError("T- - not present")
        if not wu_so_far.a_plus:
            prompt_messages.extend(
                self.prompt_antithesis_positive_side(wu_so_far.a, wu_so_far.t_minus)
            )
            return prompt_messages

        raise StopIteration("The wisdom unit is complete, nothing to do.")
