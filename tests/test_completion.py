import shlex
import tempfile
import unittest
from pathlib import Path

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.buffer import Buffer

from aura.cli import parser
from aura.completion import WorkspaceCompleter


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.completer = WorkspaceCompleter(parser(), ["/model", "/record", "/transcribe", "/graphs", "/help"])

    def complete(self, text, cursor=None):
        doc = Document(text, cursor_position=len(text) if cursor is None else cursor)
        results = []
        for item in self.completer.get_completions(doc, CompleteEvent(completion_requested=True)):
            buffer = Buffer(document=doc)
            buffer.apply_completion(item)
            results.append(buffer.text)
        return results

    def test_commands_choices_and_options_follow_parser(self):
        cases = {
            "/mo": "/model", "mo": "model",
            "/model para": "/model parakeet-tdt-0.6b-v2",
            "/model un": "/model unload",
            "/record --mo": "/record --model",
            "/record --model para": "/record --model parakeet-tdt-0.6b-v2",
            "/record --model=para": "/record --model=parakeet-tdt-0.6b-v2",
            "/record --source mic": "/record --source microphone",
            "/record --language e": "/record --language en",
            "/graphs of": "/graphs off",
            "/animations of": "/animations off",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(self.complete(source), [expected])
        self.assertEqual(self.complete("/record --title par"), [])
        for source in ('/model "para"', '/model "para', "/model 'para'"):
            self.assertEqual(shlex.split(self.complete(source)[0]), ["/model", "parakeet-tdt-0.6b-v2"])
        self.assertNotIn("/record --consent", self.complete("/record --"))

    def test_existing_suffix_and_following_arguments_are_preserved(self):
        # The production workspace includes /pause; its description comes from argparse.
        completer = WorkspaceCompleter(parser(), ['/pause'])
        choice = list(completer.get_completions(Document('/pa'), CompleteEvent(completion_requested=True)))
        self.assertEqual(choice[0].display_meta_text, 'Pause recording')
        self.assertEqual(self.complete("/model", 3), ["/model"])
        self.assertEqual(self.complete("/rec --language en", 4), ["/record --language en"])

    def test_paths_with_spaces_quotes_and_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meeting notes.wav"
            path.touch()
            for opening in ("", "'", '"'):
                source = f"/transcribe {opening}{tmp}/meeting"
                result = self.complete(source)
                self.assertEqual(len(result), 1)
                self.assertEqual(shlex.split(result[0]), ["/transcribe", str(path)])
            file = Path(tmp) / "Bob's notes.wav"
            file.touch()
            result = self.complete(f"/transcribe '{tmp}/Bob")
            self.assertEqual(shlex.split(result[0]), ["/transcribe", str(file)])
            folder = Path(tmp) / "audio folder"
            folder.mkdir()
            result = self.complete(f"/transcribe {tmp}/audio")
            self.assertEqual(shlex.split(result[0]), ["/transcribe", str(folder) + "/"])
            result = self.complete(f"/record --hotwords-file {tmp}/meeting")
            self.assertEqual(shlex.split(result[0])[-1], str(path))

    def test_quoted_path_preserves_existing_closing_quote_and_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meeting notes.wav"
            path.touch()
            prefix = f'/transcribe "{tmp}/meeting'
            result = self.complete(prefix + '" --language en', len(prefix))
            self.assertEqual(shlex.split(result[0]), ["/transcribe", str(path), "--language", "en"])


if __name__ == "__main__":
    unittest.main()
