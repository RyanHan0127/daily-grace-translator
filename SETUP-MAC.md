# Setting up Daily Grace on a Mac

Start to finish this takes about ten minutes, most of it waiting on Google.
You only do it once.

You'll need: the `daily-grace.zip` file, and the Gmail account that receives the
Daily Grace Inspiration emails.

---

## 1. Unzip it somewhere permanent

Double-click `daily-grace.zip`. A `daily-grace` folder appears.

Drag that folder to your **Documents**. Don't leave it in Downloads — if you
clear that folder later, the app goes with it.

## 2. Open Terminal in that folder

Press `Cmd + Space`, type `Terminal`, press Return.

Type this (including the space at the end), then **drag the `daily-grace` folder
from Finder onto the Terminal window** — it fills in the path for you — then press
Return:

```
cd 
```

Your prompt should now show `daily-grace`.

## 3. Check you have Python

```
python3 --version
```

- Prints something like `Python 3.12.4` → you're set, go to step 4.
- A window offers to install "command line developer tools" → click **Install**,
  wait for it to finish, then run the command again.
- `command not found` → install from <https://www.python.org/downloads/>, then
  run it again.

Nothing else ever needs installing. No packages, no libraries.

## 4. Turn on 2-Step Verification

<https://myaccount.google.com/signinoptions/two-step-verification>

Skip this if it's already on. Google will not let you create an App Password
without it.

## 5. Create an App Password

<https://myaccount.google.com/apppasswords>

Name it `daily-grace` and click Create. Google shows **16 letters in four
groups**. Copy them.

This is not your Google password. It's a single-purpose key that only allows
reading mail, works for nothing else, and can be deleted from that same page at
any time without affecting your account.

Leave the page open until step 6 is done — Google won't show it again.

## 6. Put it in the settings file

In Terminal:

```
cp .env.example .env
```

```
open -e .env
```

TextEdit opens. Fill in both lines:

```
GMAIL_ADDRESS=your.address@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

Use the address that *receives the devotional*. The spaces in the password don't
matter — paste it however Google showed it.

Save with `Cmd + S` and close TextEdit.

## 7. Start it

In the same Terminal window, in the same folder:

```
python3 app.py
```

Your browser opens with the app in it. That's it — this is the normal way to run
it, every day.

**Leave the Terminal window open while you use the app.** Closing it stops the
app.

> **Why not double-click something?** There is a `start.command` launcher in the
> folder, but macOS blocks scripts that arrive from the internet, and on a
> Standard (non-admin) account you cannot approve them yourself — the override
> lives in System Settings → Privacy & Security and asks for an administrator
> password. The command above sidesteps all of that: you are running `python3`,
> which macOS already trusts, and handing it a file. Nothing to approve.
>
> If you *are* an admin and want the double-click launcher, run `xattr -cr .`
> once in this folder, then `start.command` will open normally.

## 8. Use it

Pick a language, then click **Retrieve the last seven days**.

The first time takes about half a minute — it's translating a week's worth. After
that it's a second or two, because finished translations are kept on your Mac and
only genuinely new days get translated.

The most recent devotional appears in the middle. Down the left is the past week,
each with its date and title; click any one to read it. **Copy text** copies
whichever day you're currently reading.

Picking **English — original** in the language menu gives you the emails as
written, just cleaned up — no translation, and much faster.

Every devotional you read is saved as a plain text file in the `translations`
folder, sorted by language and date, so you can open or keep them without the
app. They're also what makes it fast: a day already saved is never translated
twice.

When you're done for the day, close the Terminal window.

---

## Every day after this

Only two things, and setup never happens again:

1. Open Terminal, `cd ` (with a space), drag the `daily-grace` folder on, Return.
2. `python3 app.py`

Tip: press the **up arrow** in Terminal to bring back a command you ran before,
so you can just hit Return twice.

---

## If something goes wrong

The app shows the actual error on screen. The usual ones:

| What it says | What it means |
|---|---|
| Missing credentials | Step 6 didn't save, or a line is blank. Run `open -e .env` and check. |
| Gmail rejected the login | You used your account password instead of the App Password, or 2-Step Verification isn't on. Redo steps 4–5. |
| No email found | That Gmail account has never received a "Daily Grace Inspiration" email from `no-reply@josephprince.org`. Check you used the right address. |
| Translation failed | Usually no internet. If it persists, Google is throttling the free translation endpoint — wait a bit and retry. |

**Anything at all about `start.command`** — "damaged and can't be opened", "you
are not an administrator", "permission denied" — → ignore that file and use
`python3 app.py` instead (step 7). The launcher is optional; nothing depends on
it. If you moved it to the Bin, that is fine, the app still works.

**"command not found: python3"** → step 3 didn't complete. Run
`python3 --version` and follow what it says.

**"can't open file 'app.py'"** → Terminal isn't in the right folder. Type `cd `
(with a space), drag the `daily-grace` folder onto the Terminal window, press
Return, and try again.

Browser didn't open → go to <http://localhost:8765> manually while the Terminal
window is running. If the Terminal printed a different port number, use that one.

**`daily-grace.localhost:8765` doesn't load** → you're in Safari. That shortcut
only works in Chrome, Edge, Opera, Brave and Firefox; Safari can't resolve it.
Use <http://localhost:8765> instead — it works in every browser, including Safari.

## Notes

- Your mailbox is opened **read-only**. Nothing is marked as read, moved, or
  deleted, no matter how often you run it.
- The app only listens on your own machine. Nobody else on your wifi can reach it.
- Your App Password sits in the `.env` file on your Mac and is sent to Gmail and
  nowhere else.
- To revoke access, delete the App Password at
  <https://myaccount.google.com/apppasswords>. It stops working immediately and
  affects nothing else.
