# Local weekly profile updates

The profile is refreshed from your own machine. It does not use GitHub Actions
or repository secrets.

## One-time setup

From the profile repository:

```sh
gh auth login
chmod +x update.sh
./update.sh --no-push
```

Review the local commit, then push it manually. After that verification, use
`./update.sh` for the scheduled job. The updater also accepts `GITHUB_TOKEN` or
`GH_TOKEN` at runtime, but `gh auth login` avoids putting a token in scheduler
configuration.

Replace `/absolute/path/to/github-profile` below with the real clone path.

## macOS — launchd

Save this as `~/Library/LaunchAgents/com.macanthonyeke.profile-update.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.macanthonyeke.profile-update</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd /absolute/path/to/github-profile &amp;&amp; ./update.sh &gt;&gt; /tmp/profile-update.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>9</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
</dict>
</plist>
```

Load it with:

```sh
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.macanthonyeke.profile-update.plist
```

This runs every Monday at 09:00 in the machine's local timezone.

## Linux — cron

Open the user crontab:

```sh
crontab -e
```

Add this weekly Monday job:

```cron
0 9 * * 1 cd /absolute/path/to/github-profile && ./update.sh >> /tmp/profile-update.log 2>&1
```

Cron has a minimal environment. If `python3`, `git`, or `gh` are not on its
`PATH`, use their absolute paths or invoke a login shell.

## Windows — Task Scheduler

Install and authenticate GitHub CLI, then create a weekly task with:

- Trigger: Weekly, Monday, 09:00.
- Program: `C:\Program Files\Git\bin\bash.exe`
- Arguments: `-lc "cd /c/absolute/path/to/github-profile && ./update.sh"`
- Start in: the profile repository directory.

Use Git Bash path syntax in the argument. Run the task manually once and check
its history before relying on the weekly trigger.

## Safe manual commands

```sh
./update.sh --no-commit       # refresh and validate files only
./update.sh --no-push         # create the refresh commit but do not push
./update.sh                   # refresh, commit if changed, and push
./update.sh --refresh-portrait --no-push
```

The portrait flag is only needed when the source NFT or approved particle map
must be rebuilt. Normal weekly runs reuse `assets/dots.json`.
