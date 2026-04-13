#!/usr/bin/env python3
from __future__ import annotations

import json
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
                "remark": "amonora-test-android-tcp",
                "port": 9443,
                "server_name": "2gis.ru",
                "fingerprint": "chrome",
                "short_id": "5e6c2a91f4d8b3c1",
                "tag": "inbound-9443",
                "client_uuid": "9d75f8df-66e3-490b-aece-5a6d1ac1ed0a",
                "client_email": "test_android_9443",
            },
            {
                "remark": "amonora-test-iphone-tcp",
                "port": 10443,
                "server_name": "vk.com",
                "fingerprint": "safari",
                "short_id": "09a73c4d1e8b2065",
                "tag": "inbound-10443",
                "client_uuid": "23e52c57-d0cf-4991-9e0a-c265a39c07c8",
                "client_email": "test_iphone_10443",
            },
        ]

        created = []
        existing = []
        updated = []
        now_ms = int(time.time() * 1000)
        for profile in profiles:
            row = cur.execute(
                "select id, settings from inbounds where protocol='vless' and port=?",
                (profile["port"],),
            ).fetchone()
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
            if row is not None:
                settings = json.loads(row["settings"] or "{}")
                clients = settings.setdefault("clients", [])
                if not any(
                    client.get("id") == profile["client_uuid"] or client.get("email") == profile["client_email"]
                    for client in clients
                ):
                    clients.append(client_payload)
                    cur.execute(
                        "update inbounds set settings=? where id=?",
                        (json.dumps(settings, separators=(",", ":")), row["id"]),
                    )
                    updated.append({"port": profile["port"], "id": row["id"], "client_added": True})
                existing.append({"port": profile["port"], "id": row["id"]})
                continue

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
            created.append(
                {
                    "id": cur.lastrowid,
                    "port": profile["port"],
                    "remark": profile["remark"],
                    "server_name": profile["server_name"],
                    "fingerprint": profile["fingerprint"],
                    "short_id": profile["short_id"],
                    "public_key": public_key,
                }
            )

        con.commit()
        print(json.dumps({"created": created, "existing": existing, "updated": updated}, ensure_ascii=False))
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

        reality_public = meta["profiles"]["primary"]["reality_public_key"]
        reality_password = meta["profiles"]["primary"]["reality_password"]
        reality_server_name = "www.apple.com"

        profiles = {
            "android_test": {
                "port": 9443,
                "reality_server_name": reality_server_name,
                "reality_short_id": "6c4e1a29d8f3b507",
                "reality_public_key": reality_public,
                "reality_password": reality_password,
                "xhttp_path": "/api/v2/android-sync",
                "stream_network": "xhttp",
                "transport_label": "XHTTP",
                "stream_path": "/api/v2/android-sync",
                "stream_host": "",
                "stream_mode": "packet-up",
                "mode_policy": "packet-up",
                "fingerprint": "chrome",
                "alpn": ["h3", "h2", "http/1.1"],
                "h3_preferred": True,
                "h2_fallback": True,
                "client_uuid": "abc64735-5f69-45d9-b14f-353f0b134da4",
                "client_email": "test_android_9443",
            },
            "ios_test": {
                "port": 10443,
                "reality_server_name": reality_server_name,
                "reality_short_id": "8f27c5a1d49e306b",
                "reality_public_key": reality_public,
                "reality_password": reality_password,
                "xhttp_path": "/api/v2/ios-sync",
                "stream_network": "xhttp",
                "transport_label": "XHTTP",
                "stream_path": "/api/v2/ios-sync",
                "stream_host": "",
                "stream_mode": "packet-up",
                "mode_policy": "packet-up",
                "fingerprint": "safari",
                "alpn": ["h2", "http/1.1"],
                "h3_preferred": False,
                "h2_fallback": True,
                "client_uuid": "f3426388-e8d6-4cb0-883b-425b5a68b30d",
                "client_email": "test_iphone_10443",
            },
        }

        for name, profile in profiles.items():
            meta.setdefault("profiles", {})[name] = profile

        inbounds = config.setdefault("inbounds", [])
        existing_ports = {inbound.get("port") for inbound in inbounds if inbound.get("port") is not None}
        additions = []
        for name, profile in profiles.items():
            inner_tag = f"@xhttp-dk-{name.replace('_', '-')}"
            inner_inbound = None
            for inbound in inbounds:
                if inbound.get("listen") == inner_tag:
                    inner_inbound = inbound
                    break
            if inner_inbound is None:
                inner_inbound = {
                    "listen": inner_tag,
                    "tag": inner_tag,
                    "protocol": "vless",
                    "settings": {"decryption": "none", "clients": []},
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
                inbounds.append(inner_inbound)
                additions.append({"profile": name, "type": "inner", "tag": inner_tag})
            clients = inner_inbound.setdefault("settings", {}).setdefault("clients", [])
            if not any(
                client.get("id") == profile["client_uuid"] or client.get("email") == profile["client_email"]
                for client in clients
            ):
                clients.append({"id": profile["client_uuid"], "email": profile["client_email"]})
                additions.append({"profile": name, "type": "inner-client", "tag": inner_tag})
            if profile["port"] not in existing_ports:
                inbounds.append(
                    {
                        "listen": "0.0.0.0",
                        "tag": f"dk-{name}-outer",
                        "port": profile["port"],
                        "protocol": "vless",
                        "settings": {
                            "clients": [],
                            "decryption": "none",
                            "fallbacks": [{"dest": inner_tag}],
                        },
                        "streamSettings": {
                            "network": "tcp",
                            "security": "reality",
                            "realitySettings": {
                                "show": False,
                                "xver": 0,
                                "target": f'{profile["reality_server_name"]}:443',
                                "serverNames": [profile["reality_server_name"]],
                                "privateKey": reality_password,
                                "shortIds": [profile["reality_short_id"]],
                            },
                        },
                    }
                )
                additions.append({"profile": name, "type": "outer", "port": profile["port"]})
                existing_ports.add(profile["port"])

        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\\n")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\\n")
        print(json.dumps({"added": additions, "profiles": profiles}, ensure_ascii=False))
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
    print("== Germany rollout ==")
    germany_output = rollout_germany(key)
    print(germany_output.strip())
    print("== Denmark rollout ==")
    denmark_output = rollout_denmark(key)
    print(denmark_output.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
