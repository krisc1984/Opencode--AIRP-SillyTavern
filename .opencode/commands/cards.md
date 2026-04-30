# /cards

列出 `角色卡/` 下所有可用角色卡。

执行：
`python -c "import sys; sys.path.insert(0,'web-frontend'); import card_store, json; print(json.dumps(card_store.list_cards(), ensure_ascii=False, indent=2))"`

输出卡名、当前激活状态和消息数。
