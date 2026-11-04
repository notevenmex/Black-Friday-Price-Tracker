from pathlib import Path

from pricetracker import cli

ROOT = Path(__file__).parent.parent


def test_list(capsys):
    assert cli.main(["-w", str(ROOT / "watchlist.example.toml"), "list"]) == 0
    out = capsys.readouterr().out
    assert "adapter=amazon" in out and "adapter=bestbuy" in out


def test_missing_watchlist(tmp_path, capsys):
    assert cli.main(["-w", str(tmp_path / "nope.toml"), "list"]) == 2
    assert "not found" in capsys.readouterr().err


def test_check_with_csv_and_db(tmp_path, monkeypatch, capsys, fixture_text):
    wl = tmp_path / "w.toml"
    wl.write_text('[[item]]\nname="Mouse"\nurl="https://shop.example/m"\ntarget_price=40\n')
    monkeypatch.setattr("pricetracker.checker.http_fetch", lambda url: fixture_text("generic_meta.html"))

    csv_path, db_path = tmp_path / "h.csv", tmp_path / "p.db"
    args = ["-w", str(wl), "check", "--delay", "0", "--csv", str(csv_path), "--db", str(db_path)]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert "[DEAL ] Mouse: 39.95" in out
    assert "39.95" in csv_path.read_text()
