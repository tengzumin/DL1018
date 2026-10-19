from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "experiments" / "position_causal_repair_v1"
LOCAL = OUT / "local_runtime"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def replace_once(text: str, old: str, new: str, name: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"Expected one {name} anchor, got {n}")
    return text.replace(old, new, 1)


def main() -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    src_episode = ROOT / "matlab/runtime/run_episode_dl1018.m"
    src_loop = ROOT / "matlab/runtime/run_dl1018_closed_loop.m"
    src_forward = ROOT / "matlab/models/position_stage1_model_forward_v2.m"
    target_episode = LOCAL / "run_episode_dl1018.m"
    episode = src_episode.read_text(encoding="utf-8")
    episode = replace_once(episode,
        "log=run_dl1018_closed_loop(scene,'B2-RBF-Full-SPLIT',cfg,opts);\n",
        "runtimeDir=fileparts(mfilename('fullpath'));\n"
        "addpath(runtimeDir,'-begin');rehash;clear run_dl1018_closed_loop\n"
        "runtimeHandle=@run_dl1018_closed_loop;runtimeInfo=functions(runtimeHandle);\n"
        "runtimePath=char(java.io.File(runtimeInfo.file).getCanonicalPath());\n"
        "runtimeRoot=char(java.io.File(runtimeDir).getCanonicalPath());\n"
        "assert(startsWith(runtimePath,runtimeRoot,'IgnoreCase',true), ...\n"
        "    'D5:PathIsolation','Episode wrapper resolved %s outside %s.',runtimePath,runtimeRoot);\n"
        "log=runtimeHandle(scene,'B2-RBF-Full-SPLIT',cfg,opts);\n", "isolated runtime handle")
    target_episode.write_text(episode, encoding="utf-8", newline="")
    loop = src_loop.read_text(encoding="utf-8")
    loop = replace_once(loop,
        "    stage1PositionHistory=zeros(14,32);\n",
        "    stage1ModelInputDim=14;\n"
        "    if stage1PositionActive&&isfield(stage1PositionRuntime,'model')&&isfield(stage1PositionRuntime.model,'input_dim')\n"
        "        stage1ModelInputDim=double(stage1PositionRuntime.model.input_dim);\n"
        "    end\n"
        "    assert(ismember(stage1ModelInputDim,[14,20]),'D5:InputDim','Candidate input dimension must be 14 or 20.');\n"
        "    stage1PositionHistory=zeros(stage1ModelInputDim,32);\n", "history dimension")
    loop = replace_once(loop, "    stage1PositionFeature=nan(n,14);\n",
                        "    stage1PositionFeature14=nan(n,14);\n"
                        "    stage1PositionFeatureInput=nan(n,stage1ModelInputDim);\n", "feature log allocation")
    loop = replace_once(loop,
        "                            feature=[stage1Preview.error(:);stage1Preview.surface(:); ...\n"
        "                                x(k,7:9).';previewThrust/P.mass;double(s.arms.command(k,:).')];\n"
        "                            assert(numel(feature)==14&&all(isfinite(feature)), ...\n"
        "                                'POSADV:FeatureInput','The 14-dimensional deployable feature must be finite.');\n",
        "                            feature14=[stage1Preview.error(:);stage1Preview.surface(:); ...\n"
        "                                x(k,7:9).';previewThrust/P.mass;double(s.arms.command(k,:).')];\n"
        "                            assert(numel(feature14)==14&&all(isfinite(feature14)), ...\n"
        "                                'D5:Feature14','The original causal X14 feature must be finite.');\n"
        "                            if stage1ModelInputDim==20\n"
        "                                feature=[feature14;x(k,4:6).';stage1Preview.nominal_acceleration(:)];\n"
        "                            else\n"
        "                                feature=feature14;\n"
        "                            end\n"
        "                            assert(numel(feature)==stage1ModelInputDim&&all(isfinite(feature)), ...\n"
        "                                'D5:FeatureInput','Candidate runtime feature must be finite and match its model.');\n",
        "runtime feature construction")
    loop = replace_once(loop, "                            stage1PositionFeature(k,:)=feature.';\n",
                        "                            stage1PositionFeature14(k,:)=feature14.';\n"
                        "                            stage1PositionFeatureInput(k,:)=feature.';\n", "feature logging")
    loop = replace_once(loop,
        "            'stage1_position_event',stage1PositionEvent(q),'stage1_position_feature_14',stage1PositionFeature(q,:), ...\n",
        "            'stage1_position_event',stage1PositionEvent(q),'stage1_position_feature_14',stage1PositionFeature14(q,:), ...\n"
        "            'stage1_position_feature_input',stage1PositionFeatureInput(q,:), ...\n", "raw log feature fields")
    target_loop = LOCAL / "run_dl1018_closed_loop.m"
    target_loop.write_text(loop, encoding="utf-8", newline="")

    forward = src_forward.read_text(encoding="utf-8")
    forward = replace_once(forward,
        "mu=double(model.input_mu(:));sigma=max(double(model.input_sigma(:)),1e-4);\n"
        "x=(double(window)-mu)./sigma;\n"
        "assert(isequal(size(x),[14,32])&&all(isfinite(x),'all'), ...\n"
        "    'POSADV:ModelInput','Expected a finite normalized 14-by-32 input window.');\n",
        "inputDim=double(model.input_dim);\n"
        "assert(ismember(inputDim,[14,20]),'D5:ModelInputDim','Expected a 14- or 20-input position model.');\n"
        "mu=double(model.input_mu(:));sigma=max(double(model.input_sigma(:)),1e-4);\n"
        "x=(double(window)-mu)./sigma;\n"
        "assert(isequal(size(x),[inputDim,32])&&all(isfinite(x),'all'), ...\n"
        "    'D5:ModelInput','Expected a finite normalized candidate window.');\n", "dynamic forward input")
    forward = replace_once(forward, "        for i=1:14\n", "        for i=1:inputDim\n", "KAN input loop")
    target_forward = LOCAL / "position_stage1_model_forward_v2.m"
    target_forward.write_text(forward, encoding="utf-8", newline="")

    manifest = {
        "status": "PREPARED_ISOLATED_COPY",
        "source_files": {
            str(src_episode.relative_to(ROOT).as_posix()): {"sha256": sha256(src_episode)},
            str(src_loop.relative_to(ROOT).as_posix()): {"sha256": sha256(src_loop)},
            str(src_forward.relative_to(ROOT).as_posix()): {"sha256": sha256(src_forward)},
        },
        "local_files": {
            str(target_episode.relative_to(ROOT).as_posix()): {"sha256": sha256(target_episode)},
            str(target_loop.relative_to(ROOT).as_posix()): {"sha256": sha256(target_loop)},
            str(target_forward.relative_to(ROOT).as_posix()): {"sha256": sha256(target_forward)},
        },
        "changes": [
            "Candidate model input dimension selects an isolated 14- or 20-row history.",
            "The isolated run_episode wrapper re-adds its folder, clears cached controller code, and calls a checked local handle.",
            "X20 appends current inertial velocity x(4:6) and zero-compensation nominal acceleration from the current backstepping preview.",
            "The original X14 feature remains logged separately; the candidate input is logged with its actual dimension.",
            "MATLAB KAN forward accepts 14/20 dimensions and loops over exactly the declared input count.",
            "Model W0 remains 33x3 and the original online PCF Head update, beta, clip, attitude RBF, Plant, and safety rules are retained.",
            "The original source files are not written by this preparation script.",
        ],
        "zero_plant": True,
    }
    p = OUT / "reports/D5_RUNTIME_PATCH.json"
    p.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
