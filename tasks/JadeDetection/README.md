# 勾协探测

任务从 `global_game.account_settings.account_file` 读取账号集合，保持文件中的顺序，逐个完成账号切换和登录处理；每个账号登录成功后执行一次悬赏任务，悬赏正常结束后继续处理下一个账号。

悬赏行为使用全局 `WantedQuests` 配置。悬赏结束不会单独安排 `WantedQuests` 的下一次运行时间，由 `JadeDetection` 统一调度；登录或悬赏过程中出现的非正常异常会交给上层任务调度器处理。

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
