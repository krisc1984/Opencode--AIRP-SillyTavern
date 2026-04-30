# /play <card>

切换当前角色卡。

执行步骤：
1. 读取用户给出的 `<card>`。
2. 确认 `角色卡/<card>/` 存在。
3. 写入 `current-card.txt`。
4. 运行：
   `python airp-sillytavern/runtime/import_card.py "角色卡/<card>" "."`
5. 读取 `角色卡/<card>/session-state.md` 和最近聊天记录，简短告知已切换。
