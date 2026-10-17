# 勾协探测

任务从 `global_game.account_settings.account_file` 读取账号集合，保持文件中的顺序，逐个完成账号切换和登录处理。

`jade_detection.jade_detection_config.jade_detection_enable` 控制勾协探测。探测使用全局 `WantedQuests` 的协作类型筛选配置；发现符合条件的勾协后，只识别普通勾协或现世勾协并写入共享文件 `account/jade_detection.json`，不邀请好友、不开始战斗。记录按 OAS 配置名分区，每次运行只替换当前实例上次的账号结果，保留其他实例数据。

多个 OAS 实例同时运行时，通过文件锁合并记录并原子替换共享文件，避免 `oas1` 与 `oas2` 的更新相互覆盖。

`jade_detection.jade_detection_config.guild_30_enable` 控制寮30。启用后，每个已登录账号都会运行现有觉醒副本任务，层数、队长/队员身份、邀请人数、等待时间和战斗等设置沿用全局 `EvoZone` 配置。寮30的 `guild_30_friend_1`、`guild_30_friend_2` 独立指定邀请名称；名称支持 `*` 通配任意字符，无 `*` 时使用包含匹配。多名匹配时按好友列表显示顺序选择第一位；没有候选时走原邀请失败流程。原 `EvoZone` 仍使用原有精确匹配。两项开关互相独立。

登录、页面识别或战斗过程中无法恢复的异常仍交由上层任务调度器处理。

账号文件示例：

```json
{
  "accounts": [
    {"account": "mail@example.com", "account_type": "email", "platform": "Android"},
    {"account": "15355554444", "account_type": "phone", "platform": "IOS"}
  ]
}
```

手机号支持客户端脱敏显示（例如 `153****4444`）的匹配；邮箱账号会兼容 OCR 丢失 `@` 后缀的情况。
