# reelhouse-local-proxy

Runs on a machine whose outbound IP MovieBox's CDN doesn't block (usually a
home ISP or non-cloud VPS). Railway tunnels every CDN fetch through here by
setting `MOVIEBOX_PROXY_URL` to this server's public URL.

## Setup on the VM

Ubuntu 24.04 assumed. Adjust paths for other distros.

```bash
# 1. install prereqs (once)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# 2. get the code
mkdir -p ~/reelhouse-proxy && cd ~/reelhouse-proxy
# (copy proxy_server.py and requirements.txt into this dir — see below)

# 3. venv + deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. secret — must match Railway's MOVIEBOX_PROXY_SECRET
export PROXY_SECRET='2495580b22cd1897408535a89152c2593d6b44bdc3fd23d611494f22eed7cb74'

# 5. run
python proxy_server.py
```

Listens on `0.0.0.0:8888` by default. Override with `PORT=9000 python proxy_server.py`.

Test locally on the VM:

```bash
curl -s http://localhost:8888/healthz
# → {"status":"ok"}
```

## Expose it publicly via Cloudflare Tunnel

The Railway backend has to reach this box over the internet. Cloudflare
Tunnel is free and doesn't need port-forwarding or a static IP.

### Install cloudflared (once)

```bash
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
```

### Quick tunnel — ephemeral URL, zero config

Best for testing. URL changes every time you restart.

```bash
cloudflared tunnel --url http://localhost:8888
```

It'll print something like:

```
+---------------------------------------------------+
|  Your quick Tunnel has been created! Visit it at: |
|  https://random-words-xyz.trycloudflare.com       |
+---------------------------------------------------+
```

Copy that URL — that's what Railway's `MOVIEBOX_PROXY_URL` needs to point at.

### Named tunnel — stable URL

Needs a domain already on Cloudflare (e.g. `yourname.com`).

```bash
cloudflared tunnel login                                # opens browser once
cloudflared tunnel create reelhouse-proxy
cloudflared tunnel route dns reelhouse-proxy proxy.yourname.com
cloudflared tunnel run reelhouse-proxy
```

`MOVIEBOX_PROXY_URL` = `https://proxy.yourname.com`.

## Keep it running after logout

Both `python proxy_server.py` and `cloudflared tunnel ...` exit when your SSH
session ends. Options:

**tmux (quickest):**

```bash
tmux new -s proxy
# start proxy_server.py inside
# Ctrl+B then D to detach
```

Reattach later with `tmux a -t proxy`.

**systemd (production):** create `/etc/systemd/system/reelhouse-proxy.service`:

```ini
[Unit]
Description=Reelhouse residential proxy
After=network.target

[Service]
Type=simple
User=vicky
WorkingDirectory=/home/vicky/reelhouse-proxy
Environment="PROXY_SECRET=<paste secret>"
ExecStart=/home/vicky/reelhouse-proxy/venv/bin/python /home/vicky/reelhouse-proxy/proxy_server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reelhouse-proxy
sudo journalctl -u reelhouse-proxy -f    # follow logs
```

Same pattern for cloudflared if you use the named-tunnel path.

## Wire it up in Railway

Once the tunnel URL is live, update Railway → your backend service →
Variables:

```
MOVIEBOX_PROXY_URL=<the trycloudflare or your-domain URL>
```

`MOVIEBOX_PROXY_SECRET` stays as-is (must match `PROXY_SECRET` on the VM).

Railway auto-redeploys. All `/api/proxy` fetches now flow:

    Browser → Railway → your VM (via CF Tunnel) → CDN → back

Whoever's IP the VM sends from is what MovieBox sees.
