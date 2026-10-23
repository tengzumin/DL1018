# PS7已解析日期的二次Parse：现场核验与后续修正

主审实际执行于UTC 2026-10-23 11:30：读取v3 DEV72消融合同，`ConvertFrom-Json`已将 `limits.deadline_utc` 解析为 `System.DateTime`，Kind=UTC，值为 `2026-10-24T17:01:00Z`。冻结launcher第53行再次调用 `[DateTime]::Parse(value).ToUniversalTime()`；隐式转为不带时区的字符串后重新解析，实际得到 `2026-10-24T09:01:00Z`，提前8小时。

这是已核实的运行门限实现错误，使PS启动检查更保守；没有改变模型、控制器、物理输入、计分或MATLAB中的实际截止值。FREEZE60自然OS0；NO_PRED60也已在该更早门限允许的余量内启动。不打断、不改冻结源码/锁/历史记录、不重跑航次。执行者另存补充收据，区分真实截止余量与PS实际使用余量。

后续TEST新入口应保留类型，不能直接复制旧写法：

```powershell
$deadlineValue = $contract.limits.deadline_utc
$deadlineUtc = if ($deadlineValue -is [DateTime]) {
    $deadlineValue.ToUniversalTime()
} else {
    [DateTimeOffset]::Parse([string]$deadlineValue).UtcDateTime
}
```

主审放行新入口前，须在本机PS7用实际JSON分别检查DateTime/字符串两路径的UTC结果，必须均为原截止 `2026-10-24T17:01:00Z`，且剩余秒数一致。此修正恢复原定截止，不扩预算、不允许旧实验重试，也不更改原G06/G12门。
