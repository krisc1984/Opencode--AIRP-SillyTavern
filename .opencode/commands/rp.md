# /rp

启动 OpenCode AIRP SillyTavern Web 服务。

## 使用位置

`/rp` 应该在“编辑/控制 OpenCode”中执行。

回复引擎 OpenCode 需要提前在另一个终端中固定端口启动：

```powershell
cd "C:\Users\hu\Desktop\RP\opencode-AIRP-SillyTavern - 副本"
opencode --port 4096
```

然后在第二个终端打开普通 OpenCode：

```powershell
cd "C:\Users\hu\Desktop\RP\opencode-AIRP-SillyTavern - 副本"
opencode
```

在普通 OpenCode 中输入：

```text
/rp
```

## 执行步骤

1. 检查 `web-frontend/server.pid`。
2. 如果 Web 服务仍在运行，读取 `web-frontend/server-port.txt`。
3. 如果没有运行，启动：

```powershell
Start-Process -WindowStyle Hidden python -ArgumentList "web-frontend/server.py" -WorkingDirectory "."
```

4. 等待 1-2 秒，读取 `web-frontend/server-port.txt`。
5. 告知用户打开：

```text
http://127.0.0.1:{port}/index.html
```

## 运行约定

浏览器提交消息后：

```text
web-frontend/server.py
  -> http://127.0.0.1:4096 OpenCode TUI API
  -> 回复引擎 OpenCode
  -> web-frontend/web-response.txt
```

回复引擎 OpenCode 必须按 `AGENTS.md` 生成回复，并把最终内容写入：

```text
web-frontend/web-response.txt
```

Web 服务随后会写入当前角色卡的 `chat_log.json`、更新变量、刷新 memory，并推送到浏览器。
