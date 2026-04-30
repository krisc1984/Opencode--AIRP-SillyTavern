# 退出RP

停止 Web 桥接服务器。

执行步骤：
1. 读取 `web-frontend/server.pid`。
2. 如果 PID 存在，运行 `Stop-Process -Id <pid> -Force`。
3. 删除 `web-frontend/server.pid` 与 `web-frontend/server-port.txt`。
4. 告知用户 RP Web 服务已停止。
