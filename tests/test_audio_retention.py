import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from aura.audio.retention import retain_mixed_m4a, validate_m4a
from aura.session_core import SessionCore

class RetentionTests(unittest.TestCase):
    def test_decode_reference_commit_before_removal_and_invalid_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sid=str(uuid.uuid4());d=root/'sessions'/sid;d.mkdir(parents=True)
            wav=d/'mixed.wav';m4a=d/'mixed.m4a'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=1',str(wav)],check=True)
            subprocess.run(['ffmpeg','-v','error','-i',str(wav),'-c:a','aac',str(m4a)],check=True)
            s={'id':sid,'artifacts':{'wav':str(wav),'m4a':str(m4a)}}
            (d/'session.json').write_text(json.dumps({'audio_tracks':{'mixed':'mixed.wav'}}))
            called=[]
            def persist(session):
                self.assertTrue(wav.exists());self.assertNotIn('wav',session['artifacts']);called.append(True)
            retain_mixed_m4a(root,s,persist)
            self.assertTrue(called);self.assertFalse(wav.exists());self.assertTrue(m4a.exists())
            core=SessionCore(root,executor=lambda *args:{})
            try:
                with core.changed:
                    saved=core._new({'title':'export'},'ready')
                    retained=core.directory(saved['id'])/'mixed.m4a'
                    retained.write_bytes(m4a.read_bytes())
                    saved['artifacts']['m4a']=str(retained)
                    result=core.request('export',{'session_id':saved['id'],'format':'wav'})
                    self.assertTrue(result['temporary']);self.assertTrue(Path(result['path']).is_file())
                    self.assertNotIn('wav',saved['artifacts']);Path(result['path']).unlink()
                    saved['state']='recoverable'
                    core.request('recover',{'session_id':saved['id']})
                    self.assertNotIn('wav',saved['artifacts'])
            finally:core.close()
            m4a.write_bytes(b'broken')
            with self.assertRaises(subprocess.CalledProcessError):validate_m4a(m4a)

    def test_progress_is_bounded_and_durable_evidence_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            core=SessionCore(tmp,executor=lambda *args:{})
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
