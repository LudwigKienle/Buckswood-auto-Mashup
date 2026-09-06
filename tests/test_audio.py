import numpy as np
import pytest
from studio.engine import stretch, snap_start, offset_audio
from studio.upstream import semitones_between_keys
from studio.models import RenderRequest
from studio.analysis import SR

def test_pitch_shift_preserves_requested_duration_and_stereo():
    t=np.arange(2*SR)/SR
    signal=np.stack([.1*np.sin(2*np.pi*440*t), .05*np.sin(2*np.pi*440*t)],axis=1).astype('float32')
    result=stretch(signal,.8,3,True)
    assert abs(len(result)-len(signal)*.8)<100
    center=result[SR//4:-SR//4]
    spectrum=np.abs(np.fft.rfft(center[:,0]))
    frequency=np.fft.rfftfreq(len(center),1/SR)[np.argmax(spectrum)]
    assert abs(frequency-440*2**(3/12))<3
    assert np.isfinite(result).all()
    assert .46 < np.sqrt(np.mean(center[:,1]**2)/np.mean(center[:,0]**2)) < .54

def test_grid_snaps_and_vocal_offset_does_not_wrap():
    assert snap_start(11.3,{'downbeat':.12},120)==pytest.approx(11.12)
    x=np.zeros((SR*2,2),np.float32);x[100]=1
    y=offset_audio(x,1,120)
    assert np.argmax(y[:,0])==100+SR//2
    assert np.count_nonzero(offset_audio(x,-1,120))==0

def test_relative_key_compatibility():
    assert semitones_between_keys('A minor','C major')==0
    assert semitones_between_keys('C# major','D major')==1

def test_invalid_render_values_rejected():
    with pytest.raises(ValueError):
        RenderRequest(track_a='x',track_b='y',target_bpm=float('nan'),sections=[])
