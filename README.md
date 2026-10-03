# Sidekick

A pre-game scouting report for League of Legends, for whichever role you're playing. While you
draft, Sidekick suggests picks from your own champions. At the loading screen it shows one
short report: how your lane goes at each stage, whether you got counter-picked and how to play
into it, what both junglers mean for you, ults that can join your fights, enemy combos, who
must not get fed, and a game plan.

It only **reads** your League client (it never clicks, picks or changes anything) and it shows
nothing during the game. Windows 10 or 11.

## 1. Download and install (about 2 minutes, no commands)

1. **Download [SidekickSetup.exe](https://github.com/zchristensen01/sidekick/releases/latest/download/SidekickSetup.exe)**
   (about 40 MB). That link is always the newest version.
2. Your browser may say the file **isn't commonly downloaded**. Choose **Keep**. In Edge: click
   the **...** next to the download, then **Keep**, then **Show more**, then **Keep anyway**.
3. Open the downloaded file. Windows may show a blue box, **"Windows protected your PC"**.
   Click **More info**, then **Run anyway**. You only see this the first time.

   Why the warnings: Sidekick is a small free project without a paid code-signing certificate,
   so Windows doesn't know it yet. Every release's fingerprint (SHA-256) is listed on its
   [release page](https://github.com/zchristensen01/sidekick/releases) if you want to check.
4. Click **Install**. No administrator password is needed. Untick **Put Sidekick on the
   Desktop** if you don't want a Desktop shortcut.
5. Leave **Open Sidekick now** ticked and click **Finish**.

Sidekick is now in your Start menu (and on your Desktop). If Windows blocks it with no
**Run anyway** button, see [Troubleshooting](#troubleshooting).

## 2. First start

- Sidekick downloads the champion data first (about a minute, "Getting ready").
- Then it says **Waiting for the League client**. Open League as you normally do. Sidekick
  follows the client by itself; there's nothing to log in to.
- **Leave Sidekick open while you play.** A second monitor works well; it remembers where you
  put it.
- What you'll see in a game:
  - **While you draft:** pick options for your role, from your own champions (step 3).
  - **When picks lock:** "Picks locked. The report comes at the loading screen."
  - **At the loading screen:** your report. Nothing during the game.
  - ARAM and other modes are skipped.

## 3. Set up your champions (do this first, 2 minutes)

Pick options come from your list, so set it up before your first game.

1. Open the League client and log in. Sidekick reads which account is logged in; each account
   has its own list.
2. In Sidekick, click **Champions** (top right).
3. In each lane you play, click **Add a champion...**, type a name and pick it from the list.
4. Give each champion **stars**: 1 = still learning, 5 = your main. Keep them honest: pick
   options rank your champions by them (a more comfortable champion comes first unless
   another is clearly better in that draft).
5. To remove one, click its **×**. Changes save by themselves.

Help filling it in:
- **Suggestions from your games**: champions you've played 4 or more times in a lane recently
  show up with **Add** or **No**.
- **Suggest from my most-played**: your highest-mastery champions, each with its usual lane.
- Several accounts: log in to each one once and set up its list.

## 4. Add your keys (optional)

Sidekick works without any keys: you get the free report (the same facts, as a list). Keys add:

| Key | What it adds | Cost |
|---|---|---|
| **Anthropic API key** | The report at the loading screen, written in plain sentences by Claude (an AI) from the same facts | Pay as you go: about 1 cent a game, at most 40 a day |
| **Riot API key** | Enemy players who queue together and one-tricks at the loading screen, and a check of each report against what happened after the game | Free |

Both are tested when you paste them, and they're stored only on your PC.

### Anthropic key (the AI-written report)
1. Go to [console.anthropic.com](https://console.anthropic.com) and make an account.
2. Under **Billing**, add a little credit (for example $5, which lasts hundreds of games).
3. Under **API Keys**, click **Create Key** and copy it (it starts with `sk-ant-`). It's shown
   only once, so keep a copy somewhere safe, such as a password manager.
4. In Sidekick: **Settings** → **AI report writer** → paste it under **Anthropic API key** →
   **Test and save**. It should say **Saved and working**.

The switch at the top of that page turns the AI writer on or off, and **Today** shows how many
reports it wrote and what they cost.

### Riot key (duos, one-tricks, after-game check)
1. Go to [developer.riotgames.com](https://developer.riotgames.com) and log in with your Riot
   account.
2. On your dashboard, copy the **Development API Key** (it starts with `RGAPI-`).
3. In Sidekick: **Settings** → **Account and Riot key** → paste it under **Riot API key** →
   **Test and save**.

A development key **expires every 24 hours**. When Settings shows it as **Rejected: expired or
wrong**, click **Regenerate API Key** on your Riot dashboard and paste the new one. To stop
renewing it: on the Riot site click **Register Product**, choose **Personal API Key**, and
describe it, for example: *"Sidekick: a personal pre-game scouting report. Reads my own League
client (read-only); uses Match-V5 and Champion-Mastery-V4 at the loading screen and for my own
games afterwards."* Once it's approved, paste that key instead. One key covers all your
accounts.

On the same Settings page, **Players at the loading screen** shows each visible player's OP.GG
record on their champion (rank, games, win rate, average kills/deaths/assists; never names).
Turn it off if you'd rather not see it.

## Updates

Sidekick checks for a new version when it opens and every 6 hours. When there is one,
**Update available** appears at the top: click it, then **Update and restart** (not during a
game). It downloads the new version, checks it's the real file, installs it and reopens in
about half a minute. Your champions, keys and settings stay as they are. The champion data
and win rates also refresh by themselves every 6 hours.

## Your files and privacy

- Everything that's yours (settings, keys, champion lists, reports and downloaded data) is in
  your own Sidekick folder on this PC, `%LOCALAPPDATA%\Sidekick`. **Settings** → **Data and
  updates** → **Open my Sidekick folder** opens it.
- Nothing is sent to GitHub or shared with anyone. Your keys are only used to talk to Riot and
  Anthropic.
- **History** (top right) lists your past games on this PC, with each game's report.
- The program itself is in `%LOCALAPPDATA%\Programs\Sidekick`.

## Uninstall

Windows **Settings** → **Apps** → **Installed apps** → **Sidekick** → **Uninstall**. It asks
whether to also delete your settings and data. The default, **No**, keeps them for a later
install.

## Moving from the old version

If you installed Sidekick before with `git clone` and `install.ps1`:

1. Close the old Sidekick.
2. Want to keep your keys? Open the old Sidekick folder (where you cloned it, for example
   `C:\Users\<you>\Sidekick`), open `.env` with Notepad and copy the keys somewhere safe.
   Or get new ones later (step 4).
3. Install the new version (step 1). Its Start menu and Desktop shortcuts replace the old ones.
4. Delete the old Sidekick folder in File Explorer. It had its own copy of Python; nothing
   else uses it.
5. If you installed Python and Git only for Sidekick, you can uninstall them too (Windows
   **Settings** → **Apps**).
6. In the new Sidekick, set up your champions (step 3) and paste your keys (step 4).

## Troubleshooting

- **"Windows protected your PC":** click **More info**, then **Run anyway**.
- **Blocked by Smart App Control** (Windows 11, no Run anyway button): Smart App Control blocks
  every app without a code-signing certificate. You can turn it off in **Windows Security** →
  **App & browser control** → **Smart App Control settings**. On some versions of Windows it
  can't be turned back on without resetting Windows, so decide for yourself.
- **Your antivirus flags it:** apps packaged this way sometimes trip antivirus programs by
  mistake. You can compare the file's SHA-256 with the one on the release page, then allow it.
- **The window stays blank:** install Microsoft's
  [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (the installer
  normally does this), then open Sidekick again.
- **"Sidekick is already open":** it's in the taskbar, maybe on another monitor.
- **Something else:** **Settings** → **Data and updates** → **Open the log folder**. The file
  `app.log` says what happened.

## For developers

Sidekick is Python. Setup, the `scout` commands, tests and how releases are built:
[`docs/DEVELOPING.md`](docs/DEVELOPING.md). Every design document is indexed in
[`CLAUDE.md`](CLAUDE.md); progress is in [`docs/TASKS.md`](docs/TASKS.md).
