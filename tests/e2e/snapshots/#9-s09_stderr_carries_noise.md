# #9-s09 stderr 側に warning / progress が出る (副作用確認)

検証: `tests/e2e/test_user_facing_output.py::test_library_stdout_noise_is_redirected`

意味: stdout から分離された進捗ログ / 警告は破棄されるのではなく stderr へ
回る。テストは差し替えたコマンド本体が "Fetching 30 files: ..." を stdout へ
print した後、`capsys` の stderr 側にその文字列が現れることを確認する。これに
より「stdout が clean」と「ライブラリ出力が消えていない (stderr で観測可能)」の
両方を同時に保証する。

利用者・Agent への影響: Agent は stdout を `json.loads` で直接読めばよく、
先頭ノイズを読み飛ばす parser を書く必要がない。診断が必要な場合は stderr
(`2>` で取得) を見る。
