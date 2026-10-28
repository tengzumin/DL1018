from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[4]
TRAIN_RUN = ROOT / 'experiments/dl_attitude_replacement_20261026/gru_stream_c5_teacher_v1/runs/GRU32_STREAM72_S2026102001'
MODEL_PATH = TRAIN_RUN / 'gru_stream_c5_teacher_weights_v1.mat'
PARITY_PATH = TRAIN_RUN / 'stream_parity_vector_v1.mat'
HERE = Path(__file__).resolve().parent
OUT_MAT = HERE / 'trained_gru_parity_v1.mat'
OUT_JSON = HERE / 'TRAINED_MODEL_PYTHON_PARITY_v1.json'

def model_from_mat(raw):
    names = ('input_mean','input_std','target_rms','gru_weight_ih','gru_weight_hh',
             'gru_bias_ih','gru_bias_hh','head_weight','head_bias')
    return {name: np.asarray(raw[name]).reshape(-1) if name in ('input_mean','input_std','target_rms','gru_bias_ih','gru_bias_hh','head_bias') else np.asarray(raw[name]) for name in names}

def forward_one(x,h,m,dtype=np.float64):
    cast=dtype;x=np.asarray(x,dtype=cast).reshape(13);h=np.asarray(h,dtype=cast).reshape(32)
    wih=np.asarray(m['gru_weight_ih'],dtype=cast);whh=np.asarray(m['gru_weight_hh'],dtype=cast)
    bih=np.asarray(m['gru_bias_ih'],dtype=cast);bhh=np.asarray(m['gru_bias_hh'],dtype=cast)
    gi=wih@x+bih;gh=whh@h+bhh
    r=cast(1)/(cast(1)+np.exp(-(gi[:32]+gh[:32])))
    z=cast(1)/(cast(1)+np.exp(-(gi[32:64]+gh[32:64])))
    n=np.tanh(gi[64:96]+r*gh[64:96])
    hn=(cast(1)-z)*n+z*h
    y=(np.asarray(m['head_weight'],dtype=cast)@hn+np.asarray(m['head_bias'],dtype=cast))*np.asarray(m['target_rms'],dtype=cast)
    return y,hn

def stream(raw_x,m,dtype=np.float64):
    cast=dtype;x=np.asarray(raw_x,dtype=cast);mu=np.asarray(m['input_mean'],dtype=cast);sigma=np.asarray(m['input_std'],dtype=cast)
    h=np.zeros(32,dtype=cast);y=np.empty((len(x),3),dtype=cast);states=np.empty((len(x),32),dtype=cast)
    for i,row in enumerate(x):
        y[i],h=forward_one((row-mu)/sigma,h,m,dtype)
        states[i]=h
    return y,states

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert MODEL_PATH.is_file() and PARITY_PATH.is_file(), 'Trainer model/parity output is not available.'
    m=model_from_mat(loadmat(MODEL_PATH));p=loadmat(PARITY_PATH)
    x=np.asarray(p['input_features_raw'],dtype=np.float64)
    assert x.shape==(1999,13),x.shape
    assert np.array_equal(np.asarray(m['input_mean']).reshape(1,-1),np.asarray(p['input_mean']))
    assert np.array_equal(np.asarray(m['input_std']).reshape(1,-1),np.asarray(p['input_std']))
    y64,h64=stream(x,m,np.float64);y32,h32=stream(x,m,np.float32)
    trainer_y=np.asarray(p['expected_output_raw_rad_s2'],dtype=np.float64)
    trainer_h=np.asarray(p['expected_hidden_float32'],dtype=np.float64).reshape(32)
    py32_output_err=float(np.max(np.abs(y32.astype(np.float64)-trainer_y)))
    py32_final_hidden_err=float(np.max(np.abs(h32[-1].astype(np.float64)-trainer_h)))
    double_vs_export_output=float(np.max(np.abs(y64-trainer_y)))
    double_vs_export_final_hidden=float(np.max(np.abs(h64[-1]-trainer_h)))
    assert y64.shape==(1999,3) and h64.shape==(1999,32)
    assert py32_output_err<1e-4 and py32_final_hidden_err<1e-5, (py32_output_err,py32_final_hidden_err)
    # Preserve a compact full-trajectory reference for MATLAB double replay.
    savemat(OUT_MAT,{**m,'input_features_raw':x,'expected_output_double':y64,
        'expected_hidden_double':h64,'trainer_output_float32':trainer_y,
        'trainer_final_hidden_float32':trainer_h.reshape(1,-1),
        'scene_id':str(p['scene_id'][0]),'model_sha256':sha(MODEL_PATH),
        'parity_input_sha256':sha(PARITY_PATH)},do_compression=True,oned_as='row')
    report={
        'status':'PASS_TRAINED_GRU_PYTHON_STREAM_PARITY',
        'Plant_calls':0,'training_started':False,'TEST_read':False,
        'model_path':str(MODEL_PATH),'model_sha256':sha(MODEL_PATH),
        'training_parity_path':str(PARITY_PATH),'training_parity_sha256':sha(PARITY_PATH),
        'event_count':len(x),'feature_dim':13,'hidden_dim':32,
        'double_output_shape':list(y64.shape),'double_hidden_trajectory_shape':list(h64.shape),
        'python_float32_output_max_abs_error_vs_trainer':py32_output_err,
        'python_float32_final_hidden_max_abs_error_vs_trainer':py32_final_hidden_err,
        'python_double_output_max_abs_error_vs_trainer_float32':double_vs_export_output,
        'python_double_final_hidden_max_abs_error_vs_trainer_float32':double_vs_export_final_hidden,
        'full_double_reference_path':str(OUT_MAT),'full_double_reference_sha256':sha(OUT_MAT),
    }
    OUT_JSON.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()