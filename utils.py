def escape_markdown_v2(text: str) -> str:
    """
    Escapes special characters in the given text to prevent them from being interpreted as Markdown formatting.

    Args:
      text (str): The input text to escape.

    Returns:
      str: The escaped text.
    """

    special_chars = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    escaped_text = ""
    for char in text:
        if char in special_chars:
            escaped_text += "\\" + char
        else:
            escaped_text += char
    return escaped_text
