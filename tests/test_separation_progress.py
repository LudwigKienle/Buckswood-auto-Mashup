import threading
import pytest
from studio import separation


def test_demucs_carriage_return_progress_and_warning():
    log='Loading model\r  0%|          | 0.0/234.0 [00:00<?, ?seconds/s]\r 53%|█████ | 124.8/234.0 [02:27<03:55, 2.16s/seconds]\nwarning: finishing block\n'
    fraction, text = separation.worker_progress(log)
    assert fraction == pytest.approx(124.8/234)
    assert text == '53 % der Audiospur verarbeitet'


def test_roformer_progress_and_incomplete_messages():
    assert separation.worker_progress('{"done":3,"total":10}\n') == (.3, '3/10 Audioblöcke')
    for text in ['Downloading weights', '{"done":0,"total":0}', '{"done":NaN,"total":1}', '{"done":1', '[]']:
        assert separation.worker_progress(text) is None


def test_demucs_progress_reaches_job_callback(tmp_path,monkeypatch):
    class Worker:
        count = 0
        returncode = 0
        def poll(self):
            self.count += 1
            return None if self.count == 1 else 0
    def start(command,stdout,**kwargs):
        stdout.write(' 50%|█████ | 117.0/234.0 [02:05<02:36, 1.33s/seconds]\n')
        stdout.flush()
        return Worker()
    class Event:
        def wait(self,_):return False
    monkeypatch.setattr(separation.subprocess,'Popen',start)
    updates=[]
    separation.run_worker(['demucs'],tmp_path/'rhythm.log',Event(),lambda p,m:updates.append((p,m)),67,95,'Instrumente')
    assert updates == [(81,'Instrumente: 50 % der Audiospur verarbeitet'),(95,'Instrumente: Trennung abgeschlossen')]


def test_cancel_still_terminates_worker(tmp_path,monkeypatch):
    from studio.engine import Cancelled
    class Worker:
        stopped=False
        def poll(self):return None
        def terminate(self):self.stopped=True
        def wait(self,timeout):return 0
    worker=Worker()
    monkeypatch.setattr(separation.subprocess,'Popen',lambda *a,**k:worker)
    event=threading.Event();event.set()
    with pytest.raises(Cancelled):
        separation.run_worker([],tmp_path/'log',event,lambda *a:None,0,100,'Instrumente')
    assert worker.stopped
