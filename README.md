# Dialectical Framework
Turn stories, strategies, or systems into insight. Auto-generate Dialectical Wheels (DWs) from any text to reveal blind spots, surface polarities, and trace dynamic paths toward synthesis.
 DWs are semantic maps that expose tension, transformation, and coherence within a system—whether narrative, ethical, organizational, or technological.

## What It Does:
 - Converts natural language into Dialectical Wheels (DWs)
 - Highlights thesis–antithesis tensions and feedback loops
 - Reveals overlooked leverage points and systemic blind-spots
 - Maps decisions, ethics, or mindsets across dialectical structures

## Built for:
 - Systems optimization
 - Wisdom mining & decision diagnostics
 - Augmented intelligence / narrative AI
 - Ethical modeling & polarity navigation

## Useful for:
 - Consultants, coaches, facilitators, and system designers
 - Storytellers, educators, and regenerative thinkers
 - Strategists, SDD/BIMA practitioners, values-driven innovators

## Learn more:
 - [Dialectical Wheels Overview](https://dialexity.com/blog/dialectical-wheels-for-systems-optimization/)
 - [Wisdom Mining & Tokenomics](https://dialexity.com/blog/dialectical-token-dlt/)
 - [Dialectical Ethics](https://dialexity.com/blog/dialectical-ethics/)
 - [Earlier Work](https://dialexity.com/blog/wp-content/uploads/2023/11/Moral-Wisdom-from-Ontology-1.pdf)

# Development

## Contributors Welcome!

We invite developers, philosophers, cognitive scientists, and regenerative ecosystem builders to co-create with us.

## Setup

Behind the scenes we heavily rely on [Mirascope](https://mirascope.com/)

## Environment Variables

| Variable Name                    | Description                          | Example Value |
|----------------------------------|--------------------------------------|---------------|
| DIALEXITY_DEFAULT_MODEL          | Default model name for the framework | gpt-4         |
| DIALEXITY_DEFAULT_MODEL_PROVIDER | Model provider (required)            | openai        |

You can store these in a `.env` file or export them in your environment.

These will specify the default "brain" for your reasoning.

## Architecture

At the core of the dialectical framework is a dialectical wheel. It is a fancy semantic graph where nodes are statements or concepts and edges are relationships such as "opposite of," "complementary to," etc. To make the graph more readable, it's depicted as a 2D wheel.

| Simple                                              | More Complicated                                     |
|-----------------------------------------------------|------------------------------------------------------|
| ![Dialectical Wheel Diagram](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme.png) | ![Dialectical Wheel Diagram](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/wheel-scheme2.png) |

The main architectural parts are:
- Wheel
- Wheel Segment
- Wisdom Unit
- Dialectical Component
- Transition


**Wheel** is composed of segments. Think of a dialectical wheel as a pizza, a segment is a slice of pizza. In the simplest case it represents some thesis (a statement, a concept, an action, a thought, an idea, etc.). A thesis can have positive and negative things related to it. Hence, a segment of a wheel is composed of these dialectical components: a thesis (T), positive side of that thesis (T+) and a negative side of that thesis (T-). In more detailed wheels, a segment could have more than 3 layers.

If we take two opposite segments, we get the basic (and the most important) structure: **Wisdom Unit** (half-wheel, verified by diagonal constraints: control statements). It's composed of:

| Dialectical Component | Description                      |
|-----------------------|----------------------------------|
| T-                    | Negative side of the main thesis |
| T                     | The thesis                       |
| T+                    | Positive side of the main thesis |
| A+                    | Positive side of the antithesis  |
| A                     | The antithesis                   |
| A-                    | Negative side of the antithesis  |

In a Wheel, segments next to each other are related. We wrap that relationship into a **Transition**. Practically, a Transition is a recipe for how to go from one segment to another in a way that we approach synthesis. Essentially, it shows how the negative side of a given thesis (Tn-) converts into the positive side of the following thesis (T(n+1)+). If we were to look at a wheel as a sliced pizza, the lines that separate the slices would be Transitions.

If we derive Transitions in a Wheel with only 2 segments (aka half-wheel), they are symmetrical and represent a special kind of Wisdom Unit, we call it Action (Ac) and Reflection (Re). As any Wisdom Unit, Action and Reflection must be verified by diagonal constraints as well.

## Prototyping & App Ideas

### Simple Win-Win Finder
![Win-Win Finder](https://raw.githubusercontent.com/dialexity/dialectical-framework/main/docs/b2c-mvp.png)

### Eye-Opener
Working beta product [Eye Opener](https://app.dialexity.com/aiapps/eye-opener). It's a tool that analyzes text and generates a visual map of its underlying structure and hidden assumptions. The core feature is a graph-like interface we call the Dialectical Wheel, that shows the delayed dialectical responses ("blind spots").

### Argument Inspector
Working beta product [Argument Inspector](https://dialexity.com/start). Useful for analysts and mediators/facilitators to deeper understand the case.

### Atlas of Feelings
[The Atlas of Feelings](https://dialexity.com/blog/atlas-of-feelings-character-qualities/) is the Plutchik's wheel converted into the „vortex“ model, whereby the most gentle emotions are inside of the wheel, whereas the rudest are outside. As everything is interconnected with dialectical rules, we can understand human nature better.

### "Spiral" Lila game
In [this blog post](https://dialexity.com/blog/spiral-lila-with-character-traits/) we explain how the ancient Lila (Leela) game has been elevated to a new level. 