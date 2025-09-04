
from mirascope import Messages


def extend_tpl(tpl: Messages.Type, prompt: Messages.Type) -> Messages.Type:
    if isinstance(prompt, list):
        tpl.extend(prompt)
    elif hasattr(prompt, "messages"):
        tpl.extend(prompt.messages)
    else:
        tpl.append(prompt)
    return tpl
