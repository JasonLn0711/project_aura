#!/usr/bin/env python3
"""Linux PTY acceptance check using synthetic audio and ASR; no model inference."""
import os,sys,tempfile,time,multiprocessing,subprocess,select,pty,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tests'))
from test_shared_sessions import test_server,wait_state
from aura.sdk import AuraClient
from aura.metadata import __version__

def main():
 with tempfile.TemporaryDirectory() as root:
  server=multiprocessing.get_context('spawn').Process(target=test_server,args=(root,));server.start()
  proc=None;master=slave=None
  try:
   path=Path(root)/'connection.json'
   for _ in range(100):
    if path.exists():break
    time.sleep(.05)
   connection=json.loads(path.read_text())
   with AuraClient(connection) as client:
    sid=client.request('record',{'capture_location':'client','title':'Synthetic terminal check','options':{'audio_format':'wav'}})['id']
    wait_state(client,sid,'recording');client.open_audio(sid,['mixed'])
    master,slave=pty.openpty()
    proc=subprocess.Popen([sys.executable,'-m','aura.cli'],stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'AURA_DATA_DIR':root,'TERM':'xterm-256color','PROMPT_TOOLKIT_NO_CPR':'1'})
    data=bytearray()
    def read(seconds):
     end=time.monotonic()+seconds
     while time.monotonic()<end:
      if select.select([master],[],[],.05)[0]:
       try:data.extend(os.read(master,65536))
       except OSError:break
    read(.8);os.write(master,f'/attach {sid}\n'.encode());read(.5)
    os.write(master,b'/gra')
    for seq in range(4):client.send_audio(sid,seq,b'\x00\x10'*480)
    client.request('stop',{'session_id':sid});client.request('producer.stopped',{'session_id':sid});wait_state(client,sid,'ready');read(.7)
    os.write(master,b'phs off\n');read(.4);os.write(master,b'/status\n');read(.3);os.write(master,b'/quit\n');proc.wait(timeout=8);read(.1)
    text=data.decode('utf-8',errors='replace')
    assert f'AURA v{__version__}' in text and '測試逐字稿' in text,text[-2000:]
    assert 'unrecognized arguments' not in text and 'Use /graphs' not in text
    assert proc.returncode==0
    Path('/tmp/aura-terminal-pty.txt').write_text(text)
    print('PTY passed: owl/version, live transcript during partial command input, graphs toggle, status and exit; synthetic device/ASR.')
  finally:
   if proc and proc.poll() is None:proc.terminate();proc.wait()
   for fd in (master,slave):
    if fd is not None:os.close(fd)
   server.terminate();server.join(10)
   if server.is_alive():server.kill();server.join()
   server.close()
if __name__=='__main__':main()
