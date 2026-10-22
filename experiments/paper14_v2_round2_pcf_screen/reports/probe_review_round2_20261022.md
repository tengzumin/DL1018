# Round 2 首场 PROBE 审核与 CONTINUE 决定

- 审核时间：2026-10-21 22:12:57 UTC
- 首场：`DL1018_VAL_T2_C00_W10`（W09–W11 高频组）；TEST 未访问。
- 决定：**批准 CONTINUE 固定清单余下 11 场；不允许重跑首场、重试或扩展场景。**

## 实际核验

- `run_status.json=STABLE`、`last_transition=20000`；独立 `raw_scan.score` 得 `finite=true`、`complete=true`、20,000 个 `[0,20)` 计分样本，终点 `19.999 s`。
- 在线更新事件 1,968 次，最大 unitless ΔW=`0.00912653687111714`（门槛 `1e-12`）；eta before/after 均 0 m/s；现有限幅复核误差 0 m/s；motor saturation 和 generalized clipping 比例均为 0。
- HEAD=`FEATURE`、update=true、PCF=false。模型 SHA、binding、normalizer 文件/报告/数组、W0 及 22 个 Plant、9 个 runtime 文件身份逐项与冻结锁相同。
- raw SHA 与 status 中记录相同：`6c7fd7e53220b5ef907091bb2b4a0e323a6dda2e88f88dc17d7db62b24324eb9`；run_start SHA 匹配：`6de781b57c7d128840c3aa1db027beb7a834056b3c77408bf9683cea99ee0b6f`。run_start 仅含 `sceneId` 与 `inputIdentity`。raw 为 45,195,514 bytes；整个 attempt 为 45,285,950 bytes（55 MB 上界内）。
- 对 ON、B、OFF 三个 raw 的 `log/reference/position` 直接按数组比较：形状均为 `(3, 20001)`，ON=B=OFF 逐元素完全相同；读前后 SHA/size/mtime 不变。

## 预登记指标的单场观察

| 方法 | 三维 Q (mm) | Z RMSE (mm) |
|---|---:|---:|
| PCF-on | 8.693982 | 4.148664 |
| B | 8.516659 | 2.494377 |
| PCF-off PROBE | 9.832278 | 2.828816 |
本场 OFF 的 Q 比 ON 高 1.138296 mm、比 B 高 1.315619 mm；Z 比 ON 低 1.319849 mm、比 B 高 0.334439 mm。单场表现混合，不能据此判定六场高频组门槛。冻结任务书没有单场 efficacy futility/early-stop 规则，故按固定 12 场清单继续可避免选择性停止；全部 12 场仍须通过预登记联合门槛，失败即保留数据、不调参、不读 TEST。

## CONTINUE 资源与授权

CONTINUE 无标记资源预检 v13 的唯一阻断项是缺少主审核标记；GPU 审计 PASS、活动 Compute=0、81/81 哈希通过、VAL verifier exit=0、MATLAB=0、C: 余量约 156.1 GiB。预估余下 11 场为 413 s、约 756.25 MB；距硬截止仍有充分余量。Launcher 将在运行前再执行 ParentReviewed CONTINUE preflight，并要求其新报告 PASS；若资源、身份、磁盘、截止或 PROBE 状态检查任一失败，就不得启动 MATLAB。

获批命令：

```powershell
pwsh -NoProfile -File "C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\experiments\paper14_v2_round2_pcf_screen\launch_round2.ps1" -Mode CONTINUE -ParentReviewed
```

当前证据绑定：PROBE summary SHA `8763072806fca3478d5a9cfd770a0f87467d7b0e095ac9bdb611900e5bbe68c0`；CONTINUE no-marker preflight v13 SHA `b759cdcd2b47d2a3ac75788fd807111f1eb4ddccd922bd687dfbe56e0384c0e9`。
