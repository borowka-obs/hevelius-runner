import textwrap

from config_manager import ConfigManager


def test_write_api_scope_id_updates_file(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        textwrap.dedent(
            """
            api:
              base_url: https://x/api/
              timeout: 5
            paths:
              out: o
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    cm = ConfigManager(str(p))
    assert cm.loaded
    cm.write_api_scope_id(99)
    cm2 = ConfigManager(str(p))
    assert cm2.get_api_config().get("scope_id") == 99
