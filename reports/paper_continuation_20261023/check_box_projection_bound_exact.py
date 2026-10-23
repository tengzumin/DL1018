"""Exact rational boundary checks of (B), (H), and (F); synthetic data only."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "BOX_PROJECTION_BOUND_EXACT_CHECK_v1.json"
assert not OUT.exists()
helper = ROOT / "experiments/position_axis_coordinate_c5_20261023/delayed_prediction_step_candidate.m"
helper_sha = hashlib.sha256(helper.read_bytes()).hexdigest()
assert helper_sha == "48feebf934b8eb90b4424f2286aa857c48213d229714f30af99aacf53329549d"
rho, leak, tracking = F(1, 100), F(1, 50000), F(3, 25)

def norm2(values):
    return sum(x*x for x in values)

def dot(left, right):
    return sum(a*b for a, b in zip(left, right))

def predict(weight, feature):
    return [sum(weight[3*i+j]*feature[i] for i in range(33)) for j in range(3)]

def feature(q):
    out = [F(0)]*33
    out[q % 2], out[2] = F(3, 5), F(4, 5)
    assert norm2(out) == 1
    return out

projection_events = 0
step_checks = 0
for initial in (F(0), F(60), F(-60)):
    w = [initial]*99
    u = [F(2) if j % 3 != 2 else F(-2) for j in range(99)]
    sum_lhs = sum_rhs = F(0)
    # q=0 has no old loss/gradient. Apply that actual first-step rule separately.
    first_b = [tracking*F(107, 600)*feature(0)[i]*F(j-1)+leak*w[3*i+j]
               for i in range(33) for j in range(3)]
    first_candidate = [a-b for a,b in zip(w,first_b)]
    previous_w = w
    w = [min(F(60),max(F(-60),x)) for x in first_candidate]
    for q in range(1, 7):
        phi, psi = feature(q), feature(q-1)
        target = [F((-1)**(q+j)*(100000 if q % 2 else 1)) for j in range(3)]
        error = [a-b for a,b in zip(predict(w,psi),target)]
        comparator_error = [a-b for a,b in zip(predict(u,psi),target)]
        beta = min(F(321+10*q,1800),F(1))
        surface = [F(7),F(-8),F(10)]
        b = [tracking*beta*phi[i]*surface[j]+leak*w[3*i+j] for i in range(33) for j in range(3)]
        g = [psi[i]*error[j] for i in range(33) for j in range(3)]
        total = [rho*x+y for x,y in zip(g,b)]
        candidate = [x-y for x,y in zip(w,total)]
        next_w = [min(F(60),max(F(-60),x)) for x in candidate]
        residual = [a-b for a,b in zip(next_w,candidate)]
        difference = [a-b for a,b in zip(w,u)]
        direction = predict(difference,psi)
        lhs = rho*(norm2(error)-norm2(comparator_error)+norm2(direction))
        rhs = norm2(difference)-norm2([a-b for a,b in zip(next_w,u)])+norm2(total)-2*dot(b,difference)-norm2(residual)
        assert lhs <= rhs
        sum_lhs += lhs
        sum_rhs += rhs
        assert sum_lhs <= sum_rhs
        old_error = [a-b for a,b in zip(predict(previous_w,psi),target)]
        jump = [a-b for a,b in zip(w,previous_w)]
        assert norm2(old_error) <= 2*norm2(error)+2*norm2(jump)
        # Exact F decomposition, including nonzero clipping/ramp and mixed M110.
        z = predict(previous_w,psi)
        old_beta = min(F(321+10*(q-1),1800),F(1))
        for j,m in enumerate((1,1,0)):
            d0, rf = F(j-2,7), F(q,11)
            dm = d0+m*rf
            clipped = min(F(3),max(F(-3),z[j]))
            lhs_f = old_beta*clipped-d0
            rhs_f = old_beta*(z[j]-target[j])+(old_beta*target[j]-dm)+old_beta*(clipped-z[j])+m*rf
            assert lhs_f == rhs_f
        projection_events += int(any(residual))
        step_checks += 1
        previous_w, w = w, next_w
assert projection_events > 0
result = {"status":"PASS_EXACT_RATIONAL_B_H_F_SYNTHETIC_BOUNDARIES",
          "joint_projection_step_checks":step_checks,"projection_active_cases":projection_events,
          "dimensions":[33,3],"helper_sha256":helper_sha,
          "proof_sha256":hashlib.sha256((HERE/"BOX_PROJECTION_FINITE_PATH_BOUND_ZH.md").read_bytes()).hexdigest(),
          "checker_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "Plant_started":False,"TEST_accessed":False,"raw_read":False,
          "scope":"Synthetic checks support formulas; no actual path or prior closed-loop guarantee."}
with OUT.open("x",encoding="utf-8") as stream:
    json.dump(result,stream,ensure_ascii=False,indent=2)
    stream.write("\n")
print(json.dumps(result))
