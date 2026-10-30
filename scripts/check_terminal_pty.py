#!/usr/bin/env python3
"""Linux PTY acceptance check using synthetic audio and ASR; no model inference."""
import argparse,os,sys,tempfile,time,multiprocessing,subprocess,select,pty,json,fcntl,termios,struct,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tests'))
from test_shared_sessions import test_server,wait_state
from aura.sdk import AuraClient
from aura.metadata import __version__
from aura.terminal import PALETTES

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--palette',choices=PALETTES,default='slate')
 args=parser.parse_args()
 receipt=Path(f'/tmp/aura-terminal-pty-{args.palette}.txt')
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
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',36,100,0,0))
    proc=subprocess.Popen([sys.executable,'-m','aura.cli','--palette',args.palette,'resume','--all'],stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'AURA_DATA_DIR':root,'TERM':'xterm-256color','PROMPT_TOOLKIT_NO_CPR':'1'})
    data=bytearray()
    def read(seconds):
     end=time.monotonic()+seconds
     while time.monotonic()<end:
      if select.select([master],[],[],.05)[0]:
       try:data.extend(os.read(master,65536))
       except OSError:break
    read(.8);os.write(master,b'Synthetic terminal check\r');read(.5)
    startup=data.decode('utf-8',errors='replace')
    assert startup.count(f'AURA v{__version__}') == 1
    assert ')))' in startup, 'Wide terminal must show the sound garden'
    assert 'Choose an ASR model' in startup and 'ASR: Breeze' in startup
    assert 'default:' not in startup and 'loads on /record' not in startup
    os.write(master,b'/animations of\t');read(.3);os.write(master,b'\n');read(.3)
    os.write(master,b'/animations on\n');read(.3)
    os.write(master,b'/gra')
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',12,40,0,0));proc.send_signal(signal.SIGWINCH);read(.3)
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',36,100,0,0));proc.send_signal(signal.SIGWINCH);read(.3)
    for seq in range(4):client.send_audio(sid,seq,b'\x00\x10'*480)
    client.request('stop',{'session_id':sid});client.request('producer.stopped',{'session_id':sid});wait_state(client,sid,'ready');read(.7)
    client.audio_socket.close()
    os.write(master,b'phs off\n');read(.4)
    os.write(master,b'/resume\n');read(.3);os.write(master,b'\x1b');read(.8)
    os.write(master,b'/status\n');read(.3)
    failed=client.request('record',{'capture_location':'client','title':'Synthetic failure'})['id']
    wait_state(client,failed,'recording')
    client.request('capture.failed',{'session_id':failed,'error':'Synthetic capture device unavailable'})
    os.write(master,f'/resume {failed[:8]}\n'.encode());read(.5)
    os.write(master,b'/inspect\n');read(.4)
    os.write(master,b'/recov\t');read(.3)
    os.write(master,f' {sid[:8]}\n'.encode());read(.4)
    os.write(master,b'/resume --all\n');read(.4)
    os.write(master,b'Synthetic');read(.2);os.write(master,b'\x1b[B');read(.2);os.write(master,b'\r');read(.4)
    os.write(master,b'/help\n');read(.4)
    previous=client.request('model.status')
    os.write(master,b'/mo\t');read(.3)
    os.write(master,b' para\t');read(.3)
    assert client.request('model.status') == previous, 'Tab must not execute the command'
    os.write(master,b'\n');read(1.1)
    assert client.request('model.status')['default']=='parakeet-tdt-0.6b-v2'
    os.write(master,b'/model\n');read(.4)
    os.write(master,b'/model un\t');read(.3)
    os.write(master,b'\n');read(1.1)
    assert client.request('model.status')['state']=='unloaded'
    os.write(master,b'/model\n');read(.4)
    active=client.request('record',{'capture_location':'client','title':'Synthetic continued recording'})['id']
    wait_state(client,active,'recording')
    os.write(master,f'/attach {active}\n'.encode());read(.4)
    os.write(master,b'/detach\n');read(.3)
    assert client.request('get',{'session_id':active})['state']=='recording'
    os.write(master,b'/quit\n');read(2);receipt.write_text(data.decode('utf-8',errors='replace'),encoding='utf-8');proc.wait(timeout=8);read(.1)
    assert client.request('get',{'session_id':active})['state']=='recording', 'CLI exit must preserve recording'
    client.request('stop',{'session_id':active});wait_state(client,active,'ready')
    text=data.decode('utf-8',errors='replace')
    assert f'AURA v{__version__}' in text and '測試逐字稿' in text,text[-2000:]
    assert 'unrecognized arguments' not in text and 'Use /graphs' not in text and 'Use /animations' not in text
    assert text.count(f'AURA v{__version__}') == 1, 'Welcome must stay in scrollback without repetition'
    assert 'Synthetic capture device unavailable' in text and 'Find session>' in text
    assert 'Service version:' in text and 'matched' in text
    assert text.count('測試逐字稿') >= 2, text[-3000:]
    assert 'parakeet-tdt-0.6b-v2' in text and 'ASR:' in text and 'unloaded' in text and 'selects and preloads' in text
    assert proc.returncode==0
    receipt.write_text(text,encoding='utf-8')
    print(f'PTY passed ({args.palette}): one garden welcome, concise ASR status, animation toggle, resize during partial input, searchable resume picker, arrows, cancellation, saved transcript, visible failure, Tab completion without execution, model switching/unload and clean exit; synthetic device/ASR.')
  finally:
   if proc and proc.poll() is None:proc.terminate();proc.wait()
   for fd in (master,slave):
    if fd is not None:os.close(fd)
   server.terminate();server.join(10)
   if server.is_alive():server.kill();server.join()
   server.close()
if __name__=='__main__':main()
