from tests.fake_diarization import FakeDiarization
import json
import tempfile
import unittest
from aura.session_core import SessionCore


class RecordingProgressTests(unittest.TestCase):
    def test_progress_is_bounded_and_durable_evidence_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=SessionCore(tmp,executor=lambda *args:{}, diarization_factory=FakeDiarization)
            try:
                with core.changed:
                    s=core._new({'title':'test'},'recording');s.update(segments=[{'text':'kept'}],transcript='kept')
                    core._save(s)
                    for i in range(110):s['samples']=i;core._save(s,progress=True)
                    self.assertEqual(core.db.execute('SELECT count(*) FROM events WHERE progress=1').fetchone()[0],100)
                    event=json.loads(core.db.execute('SELECT data FROM events WHERE progress=1 LIMIT 1').fetchone()[0])
                    self.assertNotIn('segments',event['session'])
                    s['state']='ready';core._save(s)
                    self.assertEqual(core.db.execute('SELECT count(*) FROM events WHERE progress=1').fetchone()[0],0)
                    self.assertEqual(core.sessions[s['id']]['transcript'],'kept')
            finally:core.close()
