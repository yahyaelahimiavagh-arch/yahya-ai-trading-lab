# YATL Smart Money Lab → Hostinger Premium (private phone dashboard)

## Zero-cost design

The running `yatl-sml-paper` observer **is not modified, restarted, or redeployed**.
A separate checkout reads its saved report + credit counter every 30 seconds,
redacts wallet addresses, API tokens, signatures and source data, and
uploads just `index.html` and `status.json` via authenticated SFTP.

Hostinger Premium Web Hosting includes SSH/SFTP support; no plan upgrade,
domain purchase, PHP database, background worker on Hostinger or Tailscale
subscription is required. The static HTML fetches `./status.json`; there is
no public dashboard server on the VPS. Keep the directory password protected.

### A. Prepare the Hostinger website first (important for privacy)

1. In hPanel → Websites → Manage site → File Manager, create a **separate**
   `yatllive` folder under the chosen site's `public_html`. Don't modify
   WordPress' root `.htaccess` or put files over your homepage.
2. In the same site's **Password Protect Directories** menu, protect the
   `yatllive` folder with a strong **unique** username/password *before*
   uploading any dashboard files. Verify that the browser prompts for login.
3. Enable **SSH Access** in hPanel. Note the SSH IP/host, SSH username,
   actual remote directory path, and the ED25519 host key fingerprint.
   The standard Hostinger SFTP/SSH port is 65002, but use hPanel's details
   if they differ. NEVER share passwords, API keys, or private keys in chat.

The planned phone URL becomes `https://YOURDOMAIN/yatllive/`.
Use HTTPS; if your main website is on WordPress this independent folder
does not need a WordPress plugin.

### B. Generate an *upload-only dedicated SSH key* on the Ubuntu VPS

Run from any separate SSH terminal (not the original tmux observer pane):

```bash
mkdir -p ~/.ssh ~/.config
chmod 700 ~/.ssh ~/.config
ssh-keygen -t ed25519 -f ~/.ssh/yatl_hostinger_only -C yatl-hostinger-publisher -N ''
cat ~/.ssh/yatl_hostinger_only.pub
```

Add the **public** key printed by the last command under
hPanel → SSH Access → Add SSH key. The private key stays on VPS.
Do NOT paste it to chat or GitHub.

Validate the remote SSH host key against the fingerprint shown in hPanel.
With the exact SSH host/IP from Hostinger:

```bash
ssh-keyscan -p 65002 -t ed25519 YOUR_HOSTINGER_SSH_IP > /tmp/hostinger-ed25519-key
ssh-keygen -lf /tmp/hostinger-ed25519-key
```

**Manually compare** the fingerprint above with the one Hostinger shows.
Only if they are identical:

```bash
cat /tmp/hostinger-ed25519-key >> ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
rm /tmp/hostinger-ed25519-key
```

### C. Configure the uploader (credentials never inside repository)

In the **second checkout**, `~/yatl-smart-money-monitor`, pull the
latest branch there. Do **not** run `git pull` in the active observer checkout.

```bash
cd ~/yatl-smart-money-monitor
git pull --ff-only
nano ~/.config/yatl-hostinger.env
```

Create these lines, replacing only the three placeholders from hPanel:

```bash
HOSTINGER_SFTP_HOST="YOUR_HOSTINGER_SSH_IP"
HOSTINGER_SFTP_USER="YOUR_HOSTINGER_SSH_USERNAME"
HOSTINGER_SFTP_REMOTE_DIR="domains/YOURDOMAIN/public_html/yatllive"
HOSTINGER_SFTP_KEY="$HOME/.ssh/yatl_hostinger_only"
```

The exact **remote directory path** may differ; confirm it in hPanel
File Manager/SFTP before publishing. The script deliberately refuses any
destination not ending in `/yatllive`.

```bash
chmod 600 ~/.config/yatl-hostinger.env
python3 -m unittest discover -s tests -p 'test_smart_money_hostinger.py' -v
bash ops/publish-sml-hostinger.sh --init
```

Only after the first upload works, launch a **separate** 30-second publisher:

```bash
tmux new-session -d -s yatl-sml-hostinger \
 'cd /home/ubuntu/yatl-smart-money-monitor && exec bash ops/publish-sml-hostinger.sh --loop'
tmux ls
```

The publisher has no Helius key and does not call Helius. It costs zero
additional Helius credits. It only reads existing report and budget.

### D. Open in phone browser

Open `https://YOURDOMAIN/yatllive/`. Enter the folder's password.
The HTML polls the protected `status.json` every 10 seconds, while the
VPS ships a fresh summary around every 30 seconds. The dashboard may
briefly show older data if the SFTP connection is unavailable; check
`last update` rather than assuming the bot stopped.

### Safe diagnostics

```bash
tmux ls
tmux capture-pane -pt yatl-sml-hostinger -S -30
python3 -m research.smart_money_lab.hostinger_export \
 --data-dir /home/ubuntu/yatl-smart-money/data/smart_money \
 --output-dir /home/ubuntu/yatl-smart-money-host-export
```

All output files in `/home/ubuntu/yatl-smart-money-host-export` are
redacted snapshots. The source experiment and its `state.json` are not
written. If Hostinger password protection is disabled, even redacted
strategy statistics could become public; keep it enabled.

**Research boundary:** Wallet cohort may be unvetted, and historical
signals can be counted without paper fills. Don't interpret flat P/L
as profitable trading. The two unrelated processes should be monitored
separately.
