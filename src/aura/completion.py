"""Contextual Tab completion for the interactive workspace's existing parser."""
import argparse
import re
import shlex

from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.document import Document


class WorkspaceCompleter(Completer):
    def __init__(self, parser, commands):
        self.commands = commands
        self.parsers = next(a.choices for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        self.paths = PathCompleter(expanduser=True)

    def get_completions(self, document, complete_event):
        before = document.text_before_cursor
        quote = ""
        try:
            words = shlex.split(before)
        except ValueError:
            for quote in ('"', "'"):
                try:
                    words = shlex.split(before + quote)
                    break
                except ValueError:
                    continue
            else:
                return
        current = words.pop() if words and (quote or not before[-1:].isspace()) else ""
        prefix = current
        action = None
        if not words:
            choices = self.commands if not current or current.startswith("/") else [c.lstrip("/") for c in self.commands]
        elif words[0].lstrip("/") == "graphs":
            choices = ["on", "off"] if len(words) == 1 else []
        else:
            parser = self.parsers.get(words[0].lstrip("/"))
            if parser is None:
                return
            options = {flag: a for a in parser._actions if a.help != argparse.SUPPRESS for flag in a.option_strings}
            positionals = [a for a in parser._actions if not a.option_strings]
            position = 0
            pending = None
            for word in words[1:]:
                if pending is not None:
                    pending = None
                elif word.split("=", 1)[0] in options:
                    option = options[word.split("=", 1)[0]]
                    if option.nargs != 0 and "=" not in word:
                        pending = option
                else:
                    position += 1
            if pending is not None:
                action = pending
            elif current.startswith("--") and "=" in current:
                flag, prefix = current.split("=", 1)
                action = options.get(flag)
            elif not current.startswith("-") and position < len(positionals):
                action = positionals[position]
            choices = list(action.choices) if action is not None and action.choices is not None else []
            if action is not None and action.dest in ("path", "output", "hotwords_file"):
                for item in self.paths.get_completions(Document(prefix), complete_event):
                    suffix = item.text
                    directory = item.display_text.endswith("/")
                    if directory:
                        suffix += "/"
                    if quote:
                        suffix = suffix.replace("'", "'\"'\"'") if quote == "'" else suffix.replace("\\", "\\\\").replace('"', '\\"')
                        if not directory and not document.text_after_cursor.startswith(quote):
                            suffix += quote
                    else:
                        suffix = shlex.quote(suffix) if suffix else ""
                    # ponytail: paths complete at token end; add middle-token matching if needed.
                    if document.text_after_cursor and not document.text_after_cursor[0].isspace() and not document.text_after_cursor.startswith(quote or "\0"):
                        continue
                    yield Completion(suffix, display=item.display)
                return
            if action is None or (not prefix and not choices and pending is None):
                choices = list(options)
        tail = re.match(r"[^\s'\"]*", document.text_after_cursor).group()
        for choice in choices:
            choice = str(choice)
            if not choice.startswith(prefix) or (tail and not choice.endswith(tail)):
                continue
            replacement = choice[len(prefix):len(choice) - len(tail) if tail else None]
            if quote and not document.text_after_cursor.startswith(quote):
                replacement += quote
            yield Completion(replacement, display=choice)
