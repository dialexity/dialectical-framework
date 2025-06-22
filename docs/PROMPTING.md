Here is a condensed guide on prompt engineering DOs and DON'Ts, based on https://www.youtube.com/watch?v=CxbHw93oWP0:

**DOs:**

*   **Use API Playground or Workbench Models:** Instead of consumer models like ChatGPT or Claude, use their API playground or workbench versions (e.g., platform.openai.com playground chat). These platforms offer more control over settings like model types, response formats, functions, randomness, and system/user/assistant messages, allowing for true prompt engineering.
*   **Keep Prompts Concise:** Model performance decreases with prompt length, so make your prompts shorter and improve the information density of your instructions. Aim to reduce verbose phrasing and unnecessary fluff, making prompts simpler and more direct to improve output quality and accuracy.
*   **Define Your Model's Identity:** Explicitly define the system prompt to tell the model "who it is" (e.g., "You're a helpful intelligent assistant").
*   **Provide Instructions Clearly:** Use user prompts to give the model specific instructions on what you want it to do.
*   **Leverage Assistant Prompts for Examples:** Use assistant prompts to provide examples or templates, implicitly reinforcing desired output structures and improving future results.
*   **Employ One-Shot or Few-Shot Prompting:** Including just one example in your prompt can lead to a significant, disproportionate improvement in accuracy compared to providing no examples. For mission-critical tasks, always use at least one example.
*   **Be Unambiguous:** Use extremely clear and unambiguous language to constrain the model's possible outputs, bringing them closer to your desired "Goldilocks zone" of responses. Define exactly what you want rather than using vague terms like "produce a report".
*   **Use "Spartan" Tone of Voice:** Incorporate the term "Spartan" in your tone instructions for direct and pragmatic outputs.
*   **Iterate Prompts with Data:** Test your prompts multiple times (e.g., 10-20 runs) using a Monte Carlo approach to assess the consistency and "good enough" rate of outputs. This provides data-driven insights into prompt effectiveness and helps ensure reliable results.
*   **Explicitly Define Output Format:** Clearly state the desired output format, such as bulleted lists, JSON, or CSV, to ensure structured data that can be easily integrated with other tools or applications.
*   **Learn Structured Data Formats:** Understand and utilize JSON (JavaScript Object Notation), XML (Extensible Markup Language), and CSV (Comma Separated Values) to structure data for computer readability and program integration.
*   **Apply the Key Prompt Structure:** Follow a proven structure comprising Context, Instructions, Output Format, Rules, and Examples.
    *   **Context:** Tell the model who you are and what you want.
    *   **Instructions:** Outline the specific task.
    *   **Output Format:** Specify how results should be returned.
    *   **Rules:** Provide a list of "dos and don'ts".
    *   **Examples:** Offer user-assistant prompt pairs to demonstrate the desired input and output.
*   **Use AI to Generate Examples:** Have AI create training examples for other AI models instead of manually finding them.
*   **Choose the Right Model:** Start with smarter, more complex models (e.g., GPT-4o family) as they are typically cost-effective for most use cases and solve many problems automatically. Only consider simpler, cheaper models if you are running millions of operations daily.

**DON'Ts:**

*   **Rely on Consumer Models:** Avoid using consumer models like ChatGPT or Claude for serious prompt engineering, as they hide important functionalities and decisions that affect performance.
*   **Create Overly Long Prompts:** Do not write prompts that are excessively long, as this negatively impacts model performance and accuracy.
*   **Use Verbose or Complicated Language:** Avoid writing prompts in an unnecessarily verbose or complicated manner; simplify your language to improve clarity and efficiency.
*   **Include Fluff or Tangents:** Do not add excessive fluff or irrelevant information that doesn't contribute to the core understanding of the subject matter.
*   **Use LLMs for Exact Facts:** Do not rely on Large Language Models (LLMs) as primary knowledge engines for precise facts, as they are conversational engines and can often be confidently wrong unless hooked up to an external knowledge base.
*   **Use Ambiguous Language:** Avoid vague or ambiguous language in your prompts, as this leads to inconsistent and unpredictable outputs.
*   **Include Conflicting Instructions:** Do not combine conflicting terms in your prompts (e.g., "detailed summary," "comprehensive but simple article") as they cancel each other out, increase token count, and reduce clarity.
*   **Default to the Cheapest Model:** Unless you have extremely high-volume operations (millions of daily executions), do not automatically choose the cheapest or simplest models, as smarter models often provide better results and are more cost-effective in the long run.