"""C5 DEV72 posterior path-bound evaluation; not an interval or prior Plant certificate."""
from pathlib import Path
import hashlib
import json
import csv
import math

import h5py
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / "c5_dev72_parent_review/C5_DEV72_RAW_PARENT_REVIEW_v3.json"
OUT = HERE / "BOX_BOUND_DEV72_NUMERIC_INSTANTIATION_v1.json"
CSV = HERE / "BOX_BOUND_DEV72_ALL_SCENES_v1.csv"
SOURCE_SHA = "bb34889559d95a1c995d4d420e3b3d7a702908b58b47cce969dc508a1c697fab"
PINNED = {
    "BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md": "48b63a205f27d4ef595fcf6a25ef1c8b45c8169c11251a77d244bc0c66b85406",
    "BOX_PROJECTION_BOUND_NUMERIC_SCOPE_ADDENDUM_ZH.md": "0acccfb690f4757b90b8aa435f8e03ec31a9fb2fe691df45a7673d162244ef2a",
    "BOX_PROJECTION_BOUND_NONAUTHOR_REVIEW_v1_ZH.md": "df4f7c5cfb6e4864d0fcc05bff31fea6801c3d688fc974d6e8ecbdcda9df7b3d",
}

def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def squared(values):
    return float(np.sum(np.asarray(values)**2))

def evaluate(row, initial_gram):
    metric = row["C5_metrics"]
    path = Path(metric["path"])
    assert digest(path) == metric["sha256"]
    before_stat = path.stat()
    with h5py.File(path, "r") as mat:
        log = mat["log"]
        def read(name):
            a = np.asarray(log[name])
            return a.T if a.ndim == 2 else a
        ids = np.flatnonzero(read("stage1_position_event_inference_valid").ravel())
        assert np.array_equal(ids, np.arange(320,19991,10))
        wb = np.asarray(log["stage1_position_event_weight_before_33x3"]).transpose(0,2,1)
        wa = np.asarray(log["stage1_position_event_weight_after_33x3"]).transpose(0,2,1)
        assert wb.shape == wa.shape == (1968,33,3)
        assert np.array_equal(wb[1:],wa[:-1])
        comparator = read("stage1_position_weight_initial")
        assert np.array_equal(wb[0],comparator) and np.max(np.abs(comparator)) <= 60
        phi = read("stage1_position_event_phi_33")[ids]
        target = read("stage1_position_delayed_prediction_target_mps2")[ids]
        surface = read("stage1_position_pcf_event_s_coord_eff_mps")[ids]
        beta = read("stage1_position_event_beta").ravel()[ids]
        assert np.isnan(target[0]).all() and np.isfinite(target[1:]).all()
        assert np.max(np.linalg.norm(phi,axis=1)) <= 1+1e-9
        assert np.all(np.abs(surface) <= np.array([7,8,10])+1e-12)
        assert np.all((beta >= 0)&(beta <= 1))
        old_phi, weight, label = phi[:-1], wb[1:], target[1:]
        post_prediction = np.einsum("nfi,nf->ni",weight,old_phi)
        post_error = post_prediction-label
        comparator_error = old_phi@comparator-label
        g = old_phi[:,:,None]*post_error[:,None,:]
        b = .12*beta[1:,None,None]*phi[1:,:,None]*surface[1:,None,:]+.00002*weight
        total = .01*g+b
        ideal_candidate = weight-total
        ideal_next = np.clip(ideal_candidate,-60,60)
        delta = wa[1:]-ideal_next
        max_delta = float(np.max(np.abs(delta)))
        assert max_delta <= 1e-10
        # Explicit numerical-envelope assumption, matching the frozen raw audit.
        # This pad is not claimed to be a directed-rounding IEEE certificate.
        eta = math.sqrt(99)*1e-10
        numeric_pad = len(label)*(4*60*math.sqrt(99)*eta+eta*eta)
        difference = weight-comparator
        direction = np.einsum("nfi,nf->ni",difference,old_phi)
        projection_residual = ideal_next-ideal_candidate
        distances_start = squared(wb[1]-comparator)
        distances_end = squared(wa[-1]-comparator)
        loss_p, loss_u = squared(post_error), squared(comparator_error)
        rhs = distances_start-distances_end+squared(total)-2*float(np.sum(b*difference))-squared(projection_residual)+numeric_pad
        p_bound = loss_u+(rhs-.01*squared(direction))/.01
        assert p_bound >= loss_p-1e-9 and p_bound >= 0
        jumps = squared(wb[1:]-wb[:-1])
        raw = np.einsum("nfi,nf->ni",wb,phi)
        historical_energy = squared(raw[:-1]-label)
        historical_bound = 2*(p_bound+(1+1e-9)**2*jumps)
        assert historical_energy <= historical_bound+1e-9

        state, rp, rv, ra = [read(name) for name in ("state","reference/position","reference/velocity","reference/acceleration")]
        req, af, rf, applied = [read(name) for name in ("stage1_position_pcf_a_req_mps2", "stage1_position_pcf_a_f_mps2",
                                 "stage1_position_pcf_r_f_mps2", "position_compensation_applied_acceleration_mps2")]
        d0 = np.diff(state[:,3:6],axis=0)/.001-req
        masked_rf = rf*np.array([1,1,0])
        dm = d0+masked_rf
        interval = slice(320,19990)
        repeated_y = np.repeat(label,10,axis=0)
        repeated_beta = np.repeat(beta[:-1],10)[:,None]
        clip_difference = np.repeat(np.clip(raw[:-1],-3,3)-raw[:-1],10,axis=0)
        terms = [math.sqrt(10*historical_bound),
                 math.sqrt(squared(repeated_beta*repeated_y-dm[interval])),
                 math.sqrt(squared(repeated_beta*clip_difference)),
                 math.sqrt(squared(masked_rf[interval]))]
        observed_forcing = applied-d0
        forcing_bound = math.sqrt(squared(observed_forcing[:320])+math.fsum(terms)**2+squared(observed_forcing[19990:]))
        assert math.sqrt(squared(observed_forcing)) <= forcing_bound+1e-9
        rho_p = np.diff(rp,axis=0)-.001*rv[:-1]-(np.diff(state[:,:3],axis=0)-.001*state[:-1,3:6])
        rho_s = np.diff(rv,axis=0)-.001*ra[:-1]+rho_p
        e0 = rp[0]-state[0,:3]
        sigma0 = rv[0]+e0-state[0,3:6]
        initial_squared = (initial_gram[0]*squared(e0)+initial_gram[1]*squared(sigma0)
                           +2*initial_gram[2]*float(e0@sigma0))
        q_bound = (math.sqrt(max(initial_squared,0))+800*math.sqrt(squared(rho_p))
                   +200*math.sqrt(squared(rho_s))+.2*forcing_bound)/math.sqrt(20000)
        assert metric["Q_0_20_m"] <= q_bound+1e-10
        assert before_stat.st_size == path.stat().st_size and before_stat.st_mtime_ns == path.stat().st_mtime_ns
        return {"scene_id":row["scene_id"], "raw_sha256":metric["sha256"], "Q_m":metric["Q_0_20_m"],
                "posterior_Q_bound_m":q_bound, "bound_over_Q":q_bound/metric["Q_0_20_m"],
                "post_prediction_squared_error":loss_p, "W0_same_path_squared_error":loss_u,
                "post_prediction_energy_bound":p_bound, "weight_motion_J":jumps,
                "historical_prediction_energy":historical_energy, "historical_energy_bound":historical_bound,
                "forcing_energy_norm":math.sqrt(squared(observed_forcing)), "forcing_norm_bound":forcing_bound,
                "max_postprojection_numeric_residual":max_delta, "assumed_component_numeric_envelope":1e-10}

def main():
    assert not OUT.exists() and not CSV.exists()
    assert digest(SOURCE) == SOURCE_SHA
    for name, expected in PINNED.items():
        assert digest(HERE/name) == expected
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert source["status"] == "PASS_C5_DEV72_RAW_ALL_EVENTS_PARENT_AUDIT" and len(source["rows"]) == 72
    a = np.eye(2)
    gram = [0.,0.,0.]
    matrix = np.array([[.999,.001],[-.001,.996]])
    for _ in range(20000):
        gram[0] += a[0,0]**2
        gram[1] += a[0,1]**2
        gram[2] += a[0,0]*a[0,1]
        a = matrix@a
    rows = [evaluate(row,gram) for row in source["rows"]]
    result = {"status":"PASS_NUMERICAL_POSTERIOR_INEQUALITIES_UNDER_DECLARED_ROUNDING_ENVELOPE",
              "scope":"Finite recorded paths; not interval certification, prior bound or closed-loop stability.",
              "comparator":"Fixed trained W0; no fitting or future-label selection.",
              "source_sha256":SOURCE_SHA,"proof_refs_sha256":PINNED,"scene_count":72,
              "assumptions":{"feature_norm_L":1+1e-9,"component_numerical_residual_envelope":1e-10},
              "max_observed_numeric_residual":max(r["max_postprojection_numeric_residual"] for r in rows),
              "Q_bound_over_Q_min":min(r["bound_over_Q"] for r in rows),
              "Q_bound_over_Q_max":max(r["bound_over_Q"] for r in rows),
              "Plant_started":False,"training_started":False,"TEST_accessed":False,"rows":rows,
              "checker_sha256":digest(Path(__file__))}
    with OUT.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write("\n")
    with CSV.open("x",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows","proof_refs_sha256")}))

if __name__ == "__main__":
    main()
