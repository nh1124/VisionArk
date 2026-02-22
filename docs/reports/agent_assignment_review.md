現状，エージェントの設定は以下のようになっているかと思います (私がざっと確認した範囲で)．

graph, skill登録 -> server 起動時 (seed, main)
default agent登録 ->user creation時 (auth)
agent変更 -> ユーザーの任意のタイミング (agent.py)
agent使用 -> チャット時  (project_engine_builder.py)

graphやskillはユーザー単位で処理したいと考えているのですが，そのように変更できますか？
また，その場合，graph, skillの登録はdefault agentの登録時でよいかと思います．
