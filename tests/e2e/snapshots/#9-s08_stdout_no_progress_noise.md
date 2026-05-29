# #9-s08 stdout に進捗ログ / 警告が混入しない

検証: `tests/e2e/test_user_facing_output.py::test_library_stdout_noise_is_redirected`

意味: `spec-anchor` コマンド実行中に、外部ライブラリ (HuggingFace Hub の
"Fetching 30 files" / "Loading weights" 進捗バー、"unauthenticated requests"
警告など) が stdout へ書き込んでも、`spec_anchor/cli.py` の `main` が実行中だけ
`sys.stdout` を stderr へ向けるため、stdout には結果 JSON 1 個だけが残る。

テストはコマンド本体が進捗ノイズを stdout へ print するよう差し替えたうえで、
`main` 戻り後の stdout が単一 JSON としてパースでき、"Fetching 30 files" /
"Loading weights" / "unauthenticated requests" のどれも stdout に含まれず、
それらが stderr 側に出ていることを確認する。

補足: env var による進捗バー抑制 (`HF_HUB_DISABLE_PROGRESS_BARS=1` 等) は
`_silence_library_stdout_noise` が CLI 起動時に設定する。リダイレクト機構は
抑制が効かなかった場合の保証 (どのライブラリが stdout に書いても結果 JSON が
汚れない) として併用している。
