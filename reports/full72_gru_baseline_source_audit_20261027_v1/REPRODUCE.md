# 复核命令

在 PowerShell 7 中从项目根目录执行：

```powershell
Set-Location 'C:\Users\35326\Desktop\postgraduation\0\Mcode\drone_tcn\DL1018\reports\full72_gru_baseline_source_audit_20261027_v1'
python .\verify_baseline_source_audit.py
```

脚本只读 FULL72 paired score、DEV/VAL B 与 C5 的 raw/status、清单、source lock 和既有 parent audit；会重算 144 个 raw 与 144 个 status 文件的 SHA-256，并核对 CSV 的 72 行及 `SUMMARY.json` 中的锁定哈希引用。成功时打印 `PASS`，不写入或覆盖任何文件。不会读取 TEST、启动 MATLAB/Plant 或重跑 B/C5。
