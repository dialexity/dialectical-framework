import asyncio
from datetime import datetime

from langfuse.decorators import langfuse_context
from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.reasoner_blind import ReasonerBlind
from dialectical_framework.synthesist.reasoner_conversational import ReasonerConversational
from dialectical_framework.wisdom_unit import WisdomUnit

user_message = "There she goes, just walking down the street, singing doo-wah-diddy-diddy-dum-diddy-do."

def test_wu_generator_with_validation():
    reasoner = ReasonerBlind(user_message)
    wu: WisdomUnit = asyncio.run(reasoner.generate())
    assert all(v is not None for v in wu.model_dump(exclude_none=False).values())
    print("\n")
    print(wu)
    print("\n")
    # Redefine everything is a hacky way to validate everything
    redefined_wu = asyncio.run(reasoner.redefine(
        t_minus=wu.t_minus.statement,
        t=wu.t.statement,
        t_plus=wu.t_plus.statement,
        a_minus=wu.a_minus.statement,
        a=wu.a.statement,
        a_plus=wu.a_plus.statement
    ))
    assert all(v is not None for v in wu.model_dump(exclude_none=False).values())
    print("\n")
    print(redefined_wu)

def test_wu_generator():
    langfuse_context.update_current_trace(
        session_id=f"test {datetime.now()}",
        user_id="test",
    )
    reasoner = ReasonerBlind(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert all(v is not None for v in wu.model_dump(exclude_none=False).values())
    print("\n")
    print(wu)

def test_wu_generator_conv_strategy():
    langfuse_context.update_current_trace(
        session_id=f"test {datetime.now()}",
        user_id="test",
    )
    reasoner = ReasonerConversational(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert all(v is not None for v in wu.model_dump(exclude_none=False).values())
    print("\n")
    print(wu)

def test_wu_redefine():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent.from_str('T-', 'Mental Preoccupation'),
        t=DialecticalComponent.from_str('T', 'Love'),
        t_plus=DialecticalComponent.from_str('T+', 'Compassionate Connection'),
        a_minus=DialecticalComponent.from_str('A-', 'Nihilistic Detachment'),
        a=DialecticalComponent.from_str('A', 'Indifference'),
        a_plus=DialecticalComponent.from_str('A+', 'Mindful Detachment')
    )

    # Redefine every component of the wisdom unit to make it an extreme test
    reasoner = ReasonerBlind(user_message)
    redefined_wu = asyncio.run(reasoner.redefine(
        original=wu,
        t_minus='Mental Preoccupation',
        t='Love',
        t_plus='Compassionate Connection',
        a_minus='Nihilistic Detachment',
        a='Indifference',
        a_plus='Mindful Detachment'
    ))
    assert all(v is not None for v in wu.model_dump(exclude_none=False).values())
    print("\n")
    print(redefined_wu)