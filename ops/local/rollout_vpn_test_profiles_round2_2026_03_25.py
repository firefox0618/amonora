#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


LOCAL_WINDOWS_KEY = Path("/mnt/c/Users/Skyfal/.ssh/id_ed25519")
LOCAL_LINUX_KEY = Path("/tmp/codex_id_ed25519")
DE_HOST = "root@213.108.20.34"
CORE_HOST = "root@46.21.81.186"


def ensure_local_key() -> Path:
    if not LOCAL_WINDOWS_KEY.exists():
        raise FileNotFoundError(f"Missing local key: {LOCAL_WINDOWS_KEY}")
    shutil.copyfile(LOCAL_WINDOWS_KEY, LOCAL_LINUX_KEY)
    os.chmod(LOCAL_LINUX_KEY, 0o600)
    return LOCAL_LINUX_KEY


def run(command: list[str], *, stdin: str | None = None) -> str:
    result = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result.stdout


def ssh(host: str, script: str, *, key: Path) -> str:
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=4",
            "-i",
            str(key),
            host,
            "bash -s",
        ],
        stdin=script,
    )


def rollout_germany(key: Path) -> str:
    script = textwrap.dedent(
        """
        set -euo pipefail
        mkdir -p /opt/3x-ui/backups
        ts=$(date +%Y%m%d-%H%M%S)
        backup="/opt/3x-ui/backups/x-ui.db.${ts}.bak"
        cp /opt/3x-ui/db/x-ui.db "$backup"

        python3 - <<'PY'
        import json
        import sqlite3
        import time

        DB_PATH = "/opt/3x-ui/db/x-ui.db"
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        live = cur.execute(
            "select * from inbounds where protocol='vless' and port=443 order by id limit 1"
        ).fetchone()
        if live is None:
            raise SystemExit("Live Germany VLESS inbound on port 443 not found")

        stream = json.loads(live["stream_settings"])
        reality = stream["realitySettings"]
        private_key = reality["privateKey"]
        public_key = reality["settings"]["publicKey"]
        sniffing = json.loads(live["sniffing"])

        profiles = [
            {
                "remark": "amonora-test-de-android-v2",
                "port": 9443,
                "server_name": "www.microsoft.com",
                "fingerprint": "chrome",
                "short_id": "6f1c2a4e9b8d3c70",
                "tag": "inbound-9443",
                "client_uuid": "5a776b54-9d3e-47be-bf23-f33b4ae16d22",
                "client_email": "test_de_android_v2_9443",
            },
            {
                "remark": "amonora-test-de-iphone-v2",
                "port": 10443,
                "server_name": "www.microsoft.com",
                "fingerprint": "safari",
                "short_id": "8b27d1e4c9036af2",
                "tag": "inbound-10443",
                "client_uuid": "c3b4393d-7bc3-44db-8f9c-d7c137c3c7ba",
                "client_email": "test_de_iphone_v2_10443",
            },
        ]

        now_ms = int(time.time() * 1000)
        summary = []
        for profile in profiles:
            client_payload = {
                "comment": "",
                "created_at": now_ms,
                "email": profile["client_email"],
                "enable": True,
                "expiryTime": 2082758400000,
                "flow": "",
                "id": profile["client_uuid"],
                "limitIp": 1,
                "reset": 0,
                "subId": "",
                "tgId": 0,
                "totalGB": 0,
                "updated_at": now_ms,
            }
            row = cur.execute(
                "select id from inbounds where protocol='vless' and port=? order by id limit 1",
                (profile["port"],),
            ).fetchone()
            payload_stream = {
                "network": "tcp",
                "security": "reality",
                "externalProxy": [],
                "realitySettings": {
                    "show": False,
                    "xver": 0,
                    "target": f'{profile["server_name"]}:443',
                    "serverNames": [profile["server_name"]],
                    "privateKey": private_key,
                    "minClientVer": "",
                    "maxClientVer": "",
                    "maxTimediff": 0,
                    "shortIds": [profile["short_id"]],
                    "settings": {
                        "publicKey": public_key,
                        "fingerprint": profile["fingerprint"],
                        "serverName": profile["server_name"],
                        "spiderX": "/",
                    },
                },
                "tcpSettings": {
                    "acceptProxyProtocol": False,
                    "header": {"type": "none"},
                },
            }
            payload_settings = {"clients": [client_payload], "decryption": "none"}
            if row is None:
                cur.execute(
                    '''
                    insert into inbounds (
                        user_id, up, down, total, all_time, remark, enable, expiry_time,
                        traffic_reset, last_traffic_reset_time, listen, port, protocol,
                        settings, stream_settings, tag, sniffing
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        live["user_id"],
                        0,
                        0,
                        0,
                        0,
                        profile["remark"],
                        1,
                        0,
                        "",
                        0,
                        "",
                        profile["port"],
                        "vless",
                        json.dumps(payload_settings, separators=(",", ":")),
                        json.dumps(payload_stream, separators=(",", ":")),
                        profile["tag"],
                        json.dumps(sniffing, separators=(",", ":")),
                    ),
                )
                summary.append({"port": profile["port"], "status": "created"})
                continue

            cur.execute(
                "update inbounds "
                "set remark=?, enable=1, settings=?, stream_settings=?, tag=?, sniffing=? "
                "where id=?",
                (
                    profile["remark"],
                    json.dumps(payload_settings, separators=(",", ":")),
                    json.dumps(payload_stream, separators=(",", ":")),
                    profile["tag"],
                    json.dumps(sniffing, separators=(",", ":")),
                    row["id"],
                ),
            )
            summary.append({"port": profile["port"], "status": "updated", "id": row["id"]})

        con.commit()
        print(json.dumps(summary, ensure_ascii=False))
        PY

        ufw allow 9443/tcp >/dev/null || true
        ufw allow 10443/tcp >/dev/null || true
        docker restart 3x-ui >/dev/null
        sleep 5
        python3 - <<'PY'
        import sqlite3, json
        con = sqlite3.connect("/opt/3x-ui/db/x-ui.db")
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "select id, port, remark, protocol, enable from inbounds where port in (443,8443,9443,10443) order by port"
        ).fetchall()
        print(json.dumps([dict(row) for row in rows], ensure_ascii=False))
        PY
        ss -ltnp | grep -E '(:443|:8443|:9443|:10443)\\b'
        echo "BACKUP=$backup"
        """
    ).strip()
    return ssh(DE_HOST, script, key=key)


def rollout_denmark(key: Path) -> str:
    script = textwrap.dedent(
        """
        set -euo pipefail
        ssh -o BatchMode=yes -o UserKnownHostsFile=/opt/amonora_bot/.ssh/known_hosts -o StrictHostKeyChecking=yes -i /opt/amonora_bot/.ssh/dashboard_metrics root@81.17.159.58 'bash -s' <<'INNER'
        set -euo pipefail
        ts=$(date +%Y%m%d-%H%M%S)
        cfg_backup="/usr/local/etc/xray/config.json.${ts}.bak"
        meta_backup="/usr/local/etc/xray/amonora_dk_meta.json.${ts}.bak"
        cp /usr/local/etc/xray/config.json "$cfg_backup"
        cp /usr/local/etc/xray/amonora_dk_meta.json "$meta_backup"

        python3 - <<'PY'
        import json
        from pathlib import Path

        config_path = Path("/usr/local/etc/xray/config.json")
        meta_path = Path("/usr/local/etc/xray/amonora_dk_meta.json")
        config = json.loads(config_path.read_text())
        meta = json.loads(meta_path.read_text())

        inbounds = config.setdefault("inbounds", [])

        live_primary_outer = next((inbound for inbound in inbounds if inbound.get("port") == 443), None)
        if live_primary_outer is None:
            raise SystemExit("Live Denmark outer inbound on 443 not found")
        outer_reality = ((live_primary_outer.get("streamSettings") or {}).get("realitySettings") or {})
        outer_private_key = str(outer_reality.get("privateKey") or "").strip()
        if not outer_private_key:
            raise SystemExit("Live Denmark outer privateKey is missing")

        profiles = {
            "android_test": {
                "port": 9443,
                "reality_server_name": "www.apple.com",
                "reality_short_id": "b7f4c1935e2a6d08",
                "reality_public_key": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
                "reality_password": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
                "xhttp_path": "/api/v1/updates",
                "stream_network": "xhttp",
                "transport_label": "XHTTP",
                "stream_path": "/api/v1/updates",
                "stream_host": "",
                "stream_mode": "packet-up",
                "mode_policy": "packet-up",
                "fingerprint": "chrome",
                "alpn": ["h3", "h2", "http/1.1"],
                "h3_preferred": True,
                "h2_fallback": True,
                "client_uuid": "d258cf2a-aed3-4dff-8b74-6db8c1855dc5",
                "client_email": "test_dk_android_v2_9443",
                "inner_tag": "@xhttp-dk-android-test",
                "outer_tag": "dk-android-test-v2-outer",
            },
            "ios_test": {
                "port": 10443,
                "reality_server_name": "www.apple.com",
                "reality_short_id": "d9a2604e7c1b5f83",
                "reality_public_key": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
                "reality_password": "ek2qyhS-WjqRUomJezXVGeI-okhCYrHfN3byAmEwlDQ",
                "xhttp_path": "/graphql",
                "stream_network": "xhttp",
                "transport_label": "XHTTP",
                "stream_path": "/graphql",
                "stream_host": "",
                "stream_mode": "packet-up",
                "mode_policy": "packet-up",
                "fingerprint": "safari",
                "alpn": ["h2", "http/1.1"],
                "h3_preferred": False,
                "h2_fallback": True,
                "client_uuid": "4bf18d5c-3fe8-4ccf-98b7-baa81d02e21d",
                "client_email": "test_dk_iphone_v2_10443",
                "inner_tag": "@xhttp-dk-ios-test",
                "outer_tag": "dk-ios-test-v2-outer",
            },
        }

        meta_profiles = meta.setdefault("profiles", {})
        meta["profiles"] = {
            "primary": meta_profiles["primary"],
            "reserve": meta_profiles["reserve"],
            "android_test": profiles["android_test"],
            "ios_test": profiles["ios_test"],
        }

        additions = []
        for name, profile in profiles.items():
            inner_inbound = next((inbound for inbound in inbounds if inbound.get("listen") == profile["inner_tag"]), None)
            inner_payload = {
                "listen": profile["inner_tag"],
                "tag": profile["inner_tag"],
                "protocol": "vless",
                "settings": {
                    "decryption": "none",
                    "clients": [{"id": profile["client_uuid"], "email": profile["client_email"]}],
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic", "fakedns"],
                    "metadataOnly": False,
                    "routeOnly": False,
                },
                "streamSettings": {
                    "network": "xhttp",
                    "xhttpSettings": {
                        "path": profile["xhttp_path"],
                        "mode": profile["stream_mode"],
                    },
                },
            }
            if inner_inbound is None:
                inbounds.append(inner_payload)
                additions.append({"profile": name, "type": "inner_created"})
            else:
                inner_inbound.clear()
                inner_inbound.update(inner_payload)
                additions.append({"profile": name, "type": "inner_updated"})

            outer_inbound = next((inbound for inbound in inbounds if inbound.get("port") == profile["port"]), None)
            outer_payload = {
                "listen": "0.0.0.0",
                "tag": profile["outer_tag"],
                "port": profile["port"],
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none",
                    "fallbacks": [{"dest": profile["inner_tag"]}],
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "xver": 0,
                        "target": f'{profile["reality_server_name"]}:443',
                        "serverNames": [profile["reality_server_name"]],
                        "privateKey": outer_private_key,
                        "shortIds": [profile["reality_short_id"]],
                    },
                },
            }
            if outer_inbound is None:
                inbounds.append(outer_payload)
                additions.append({"profile": name, "type": "outer_created"})
            else:
                outer_inbound.clear()
                outer_inbound.update(outer_payload)
                additions.append({"profile": name, "type": "outer_updated"})

        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\\n")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\\n")
        print(json.dumps({"updated": additions, "profiles": meta["profiles"]}, ensure_ascii=False))
        PY

        /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json >/dev/null
        ufw allow 9443/tcp >/dev/null || true
        ufw allow 10443/tcp >/dev/null || true
        systemctl restart xray
        sleep 5
        python3 - <<'PY'
        import json
        from pathlib import Path
        meta = json.loads(Path("/usr/local/etc/xray/amonora_dk_meta.json").read_text())
        summary = {name: meta["profiles"][name] for name in ("primary", "reserve", "android_test", "ios_test")}
        print(json.dumps(summary, ensure_ascii=False))
        PY
        systemctl is-active xray
        ss -ltnp | grep -E '(:443|:8443|:9443|:10443)\\b'
        echo "CFG_BACKUP=$cfg_backup"
        echo "META_BACKUP=$meta_backup"
        INNER
        """
    ).strip()
    return ssh(CORE_HOST, script, key=key)


def main() -> int:
    key = ensure_local_key()
    print("== Germany rollout v2 ==")
    print(rollout_germany(key).strip())
    print("== Denmark rollout v2 ==")
    print(rollout_denmark(key).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
